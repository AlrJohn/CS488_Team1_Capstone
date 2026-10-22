"""Exercise the Pi pipeline with synthetic masks, without Hailo hardware."""
from pathlib import Path
import sys
import unittest

import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
sys.path.insert(0, str(VISION / 'pi'))
from common.geometry import Boxes
from yardspi.pipeline import Pipeline


class SyntheticBackend:
    def predict(self, frame):
        h, w = frame.shape[:2]
        x0, x1 = w // 2, 3 * w // 4
        y0, y1 = h // 4, 3 * h // 4
        masks = np.zeros((1, h, w), dtype=np.uint8)
        masks[0, y0:y1, x0:x1] = 1
        boxes = Boxes([[x0, y0, x1, y1, .95, 0]], (h, w))
        return masks, boxes, {'inference_ms': 0.0}


class PiPipelineTests(unittest.TestCase):
    def test_two_frames_count_once_and_new_box_resets_confirmation(self):
        pipeline = Pipeline(VISION, SyntheticBackend())
        frame = np.full((720, 1280, 3), (0, 0, 240), dtype=np.uint8)
        for index in range(1, 5):
            row, masks = pipeline.process(frame, index / 30)
            self.assertEqual(row['pack']['counts']['red'], 0 if index == 1 else 1)
            self.assertEqual(masks.shape[0], 1)
            if index == 2:
                self.assertEqual(next(iter(row['confirmed'].values()))['color'], 'red')
                self.assertEqual(len(row['transfer_events']), 1)
        pipeline.new_box(5 / 30)
        for index in range(6, 8):
            row, _ = pipeline.process(frame, index / 30)
            self.assertEqual(row['pack']['counts']['red'], 0 if index == 6 else 1)


if __name__ == '__main__':
    unittest.main()
