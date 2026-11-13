"""Check raw-head layouts and mask reconstruction without Hailo hardware.

CS488 Capstone, Team 1.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(VISION), str(VISION / "pi")]
from common.geometry import Transform
from yardspi.decoding import decode, native_masks, nms, output_heads


class PiDecodingTests(unittest.TestCase):
    """Exercise the same tensor contract used by ONNX and Hailo adapters."""

    def setUp(self):
        """Build a small one-class network contract with distinct tensor shapes."""
        self.config = dict(
            height=32,
            width=64,
            strides=[8, 16, 32],
            reg_max=16,
            classes=1,
            mask_channels=32,
            conf=0.5,
            iou=0.7,
            max_det=20,
        )
        self.heads = {}
        for stride in self.config["strides"]:
            for kind, channels in (("box", 64), ("score", 1), ("coeff", 32)):
                self.heads[f"{kind}_s{stride}"] = np.zeros(
                    (1, channels, 32 // stride, 64 // stride), np.float32
                )
        self.heads["proto"] = np.ones((1, 32, 8, 16), np.float32)

    def test_layout_conversion_and_missing_or_duplicate_heads(self):
        """Accept equivalent host layouts while rejecting incomplete tensor sets."""
        nhwc = {name: tensor.transpose(0, 2, 3, 1) for name, tensor in self.heads.items()}
        first = output_heads(self.heads, self.config, "NCHW")
        second = output_heads(nhwc, self.config, "NHWC")
        for name in first:
            np.testing.assert_array_equal(first[name], second[name])
        missing = dict(self.heads)
        missing.pop("proto")
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            output_heads(missing, self.config, "NCHW")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            output_heads({**self.heads, "extra": self.heads["proto"]}, self.config, "NCHW")

    def test_nms_keeps_separate_cans_and_prefers_confident_overlap(self):
        """Remove a repeated box without collapsing a nearby separate can."""
        boxes = np.array([[0, 0, 20, 40], [1, 1, 21, 41], [22, 0, 42, 40]], np.float32)
        np.testing.assert_array_equal(nms(boxes, np.array([0.8, 0.9, 0.85]), 0.7, 10), [1, 2])

    def test_native_mask_stays_inside_its_detection_box(self):
        """Keep colored background outside the can box out of its binary mask."""
        masks = native_masks(
            np.ones((32, 8, 16), np.float32),
            np.ones((1, 32), np.float32),
            np.array([[10, 5, 30, 25]], np.float32),
            (32, 64),
        )
        self.assertEqual(int(masks.sum()), 20 * 20)
        self.assertEqual(int(masks[:, :, :10].sum()), 0)

    def test_empty_and_one_can_predictions_match_across_layouts(self):
        """Return aligned masks and boxes for both no detections and a strong can."""
        transform = Transform((32, 64), (32, 64), 1.0, (0, 0))
        masks, boxes = decode(self.heads, transform, self.config)
        self.assertEqual(masks.shape, (0, 32, 64))
        self.assertEqual(len(boxes), 0)
        self.heads["score_s8"][0, 0, 1, 2] = 10
        self.heads["coeff_s8"][0, :, 1, 2] = 1
        first_masks, first_boxes = decode(self.heads, transform, self.config)
        nhwc = {name: tensor.transpose(0, 2, 3, 1) for name, tensor in self.heads.items()}
        second_masks, second_boxes = decode(nhwc, transform, self.config, layout="NHWC")
        self.assertEqual(len(first_boxes), 1)
        self.assertTrue(first_masks.any())
        np.testing.assert_array_equal(first_masks, second_masks)
        np.testing.assert_allclose(first_boxes.data, second_boxes.data)


if __name__ == "__main__":
    unittest.main()
