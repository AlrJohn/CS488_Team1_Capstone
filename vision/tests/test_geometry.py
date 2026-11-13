"""Check camera-to-model coordinates and normalized station geometry.

CS488 Capstone, Team 1.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
from common.geometry import Boxes, letterbox, restore_view


class GeometryTests(unittest.TestCase):
    """Keep model coordinates and count-area coordinates aligned."""

    def test_letterbox_preserves_color_order_and_asymmetric_padding(self):
        """Check RGB conversion and the recorded transform for a non-square source."""
        image = np.full((100, 200, 3), (10, 20, 30), np.uint8)
        rgb, transform = letterbox(image, (320, 640))
        self.assertEqual(rgb.shape, (320, 640, 3))
        self.assertEqual(transform.original, (100, 200))
        self.assertEqual(transform.padding, (0, 0))
        np.testing.assert_array_equal(rgb[100, 100], [30, 20, 10])
        portrait = np.full((101, 80, 3), 200, np.uint8)
        padded, transform = letterbox(portrait)
        self.assertEqual(padded.shape, (320, 640, 3))
        self.assertGreater(transform.padding[0], 0)
        np.testing.assert_array_equal(padded[0, 0], [114, 114, 114])

    def test_box_selection_retains_shape_and_detection_fields(self):
        """Check corner-to-center conversion without losing confidence or class."""
        boxes = Boxes([[10, 20, 30, 60, 0.9, 0], [40, 10, 80, 50, 0.8, 0]], (100, 100))
        self.assertEqual(len(boxes[0]), 1)
        np.testing.assert_allclose(boxes.xywh, [[20, 40, 20, 40], [60, 30, 40, 40]])
        np.testing.assert_allclose(boxes.conf, [0.9, 0.8])
        np.testing.assert_array_equal(boxes.cls, [0, 0])
        self.assertEqual(boxes[1].orig_shape, (100, 100))

    def test_normalized_roi_rejects_offscreen_and_tiny_regions(self):
        """Reject unusable geometry before it reaches mask cropping or counting."""
        self.assertEqual(
            restore_view({"normalized_xywh": [0.1, 0.2, 0.5, 0.5]}, (200, 400)), [40, 40, 200, 100]
        )
        for bounds in ([0.9, 0, 0.5, 1], [0, 0, 0.01, 1], [float("nan"), 0, 1, 1]):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                restore_view({"normalized_xywh": bounds}, (200, 400))


if __name__ == "__main__":
    unittest.main()
