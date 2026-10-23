"""Exercise the Pi pipeline with synthetic masks, without Hailo hardware."""
from pathlib import Path
import json
import sys
import tempfile
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
    def test_ordinary_color_limits_from_json_take_effect_in_pi_pipeline(self):
        frame = np.full((140, 200, 3), (0, 0, 240), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as folder:
            view = Path(folder)/'view.json'
            view.write_text(json.dumps(dict(normalized_xywh=[0, 0, 1, 1], defect_exit_x=.1)))
            color_path = Path(folder)/'colors.json'
            colors = json.loads((VISION/'configs/colors.json').read_text())
            colors['side_sampling']['enabled'] = False
            for min_pixels, expected in [(25, 1), (5000, 0)]:
                with self.subTest(min_pixels=min_pixels):
                    colors['interior_sampling'] = dict(min_pixels=min_pixels, min_coverage=.15, min_dominance=.8)
                    color_path.write_text(json.dumps(colors))
                    pipeline = Pipeline(VISION, SyntheticBackend(), view=view, colors=color_path)
                    pipeline.process(frame, 1/30)
                    row, _ = pipeline.process(frame, 2/30)
                    self.assertEqual(row['pack']['counts']['red'], expected)
                    self.assertEqual(vars(pipeline.settings.interior_sampling), colors['interior_sampling'])

    def test_white_label_side_color_counts_with_the_same_confirmation_rule(self):
        frame = np.full((140, 200, 3), 220, dtype=np.uint8)
        # The fake backend finds a can at x=100:150, y=35:105. Its front is
        # white, with a two-pixel-wide red strip down the left of the body.
        frame[35:105, 101:103] = (0, 0, 240)
        with tempfile.TemporaryDirectory() as folder:
            view = Path(folder)/'view.json'
            view.write_text(json.dumps(dict(normalized_xywh=[0, 0, 1, 1], defect_exit_x=.1)))
            color_path = Path(folder)/'colors.json'
            colors = json.loads((VISION/'configs/colors.json').read_text())
            for enabled in (True, False):
                with self.subTest(side_fallback=enabled):
                    colors['side_sampling']['enabled'] = enabled
                    color_path.write_text(json.dumps(colors))
                    pipeline = Pipeline(VISION, SyntheticBackend(), view=view, colors=color_path)
                    first, _ = pipeline.process(frame, 1/30)
                    second, _ = pipeline.process(frame, 2/30)
                    self.assertEqual(first['pack']['counts']['red'], 0)
                    self.assertEqual(second['pack']['counts']['red'], 1 if enabled else 0)
                    if enabled:
                        self.assertEqual(first['observations'][0]['color_analysis']['sampling_method'], 'side_bands')

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
