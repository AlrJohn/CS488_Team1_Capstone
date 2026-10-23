"""Check cropped color equivalence and recovery of colored can side strips."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
from common.color_analysis import COLORS, sample_colors
from common.settings import InteriorSampling, Settings, SideSampling


def full_image_reference(frame, masks, settings, interior):
    """Preserve the original calculation as an independent regression oracle."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16)
    selected = {}
    for name in COLORS:
        limits = settings.colors[name]
        delta = np.abs(hue-limits.hue)
        selected[name] = (np.minimum(delta, 180-delta) <= limits.tolerance) & (
            hsv[:, :, 1] >= limits.saturation_min) & (hsv[:, :, 2] >= limits.value_min)
    labels, diagnostics = [], []
    for raw in masks:
        mask = raw.astype(np.uint8)
        sample = mask > 0
        used_core = False
        if interior and sample.any():
            yy, xx = np.where(sample)
            x0, x1, y0, y1 = int(xx.min()), int(xx.max())+1, int(yy.min()), int(yy.max())+1
            eroded = cv2.erode(mask, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)>0
            core = np.zeros_like(sample)
            core[y0+round((y1-y0)*.12):y1-round((y1-y0)*.10),
                 x0+round((x1-x0)*.04):x1-round((x1-x0)*.04)] = True
            core &= eroded
            if int(core.sum()) >= max(100, int(sample.sum())*.25):
                sample, used_core = core, True
        count = int(sample.sum())
        votes = {name: int((sample & pixels).sum()) for name, pixels in selected.items()}
        winner = max(votes, key=votes.get)
        coverage = votes[winner]/max(1, count)
        dominance = votes[winner]/max(1, sum(votes.values()))
        enough = votes[winner]>=25 and coverage>=.10 and dominance>=.60
        color = winner if enough else 'unknown'
        reason = 'confirmed label pixels' if enough else 'too few colored pixels' if votes[winner]<25 else 'too little label coverage' if coverage<.10 else 'mixed color votes'
        labels.append(color)
        diagnostics.append(dict(color=color, reason=reason, sample_pixels=count, interior_sample=used_core,
                                votes=votes, coverage=coverage, dominance=dominance))
    return labels, diagnostics


class ColorSamplingTests(unittest.TestCase):
    def assert_original_evidence(self, actual, expected):
        """Compare the original fields while allowing new sampling diagnostics."""
        self.assertEqual(actual[0], expected[0])
        for observed, reference in zip(actual[1], expected[1]):
            self.assertEqual({key: observed[key] for key in reference}, reference)

    def test_cropped_calculation_preserves_all_pixel_evidence(self):
        settings = Settings.load(VISION/'configs/colors.json')
        settings.side_sampling.enabled = False
        rng = np.random.default_rng(488)
        for iteration in range(12):
            frame = rng.integers(0, 256, (120, 180, 3), dtype=np.uint8)
            masks = np.zeros((7, 120, 180), np.uint8)
            masks[0, :40, :50] = 1  # Top/left image edge.
            masks[1, 70:, 125:] = 1  # Bottom/right image edge.
            masks[2, 15:100, 35:75] = 1
            masks[2, 35:65, 45:60] = 0  # A hand-shaped hole.
            masks[3, 50, 90] = 1  # Too small for interior sampling.
            masks[4, 20:110, 90] = 1
            masks[5, 50:90, 130:170] = rng.integers(0, 2, (40, 40), dtype=np.uint8)
            # Last mask remains empty. Exercise 0/255 masks as well as 0/1.
            if iteration % 2:
                masks *= 255
            for interior in (False, True):
                self.assert_original_evidence(sample_colors(frame, masks, settings, interior),
                                              full_image_reference(frame, masks, settings, interior))

    def test_hue_wrap_and_lighting_limits_match_previous_behavior(self):
        settings = Settings.load(VISION/'configs/colors.json')
        hsv = np.zeros((60, 90, 3), np.uint8)
        hsv[:, :30] = (0, 220, 220)
        hsv[:, 30:60] = (179, 220, 220)
        hsv[:, 60:] = (176, 120, 220)  # Below the current red saturation limit.
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        masks = np.zeros((3, 60, 90), np.uint8)
        for i in range(3):
            masks[i, :, i*30:(i+1)*30] = 1
        actual = sample_colors(frame, masks, settings)
        self.assert_original_evidence(actual, full_image_reference(frame, masks, settings, True))
        self.assertEqual(actual[0], ['red', 'red', 'unknown'])

    def test_mixed_and_insufficient_label_pixels_keep_their_reasons(self):
        settings = Settings.load(VISION/'configs/colors.json')
        hsv = np.full((40, 80, 3), (0, 0, 180), np.uint8)
        hsv[:20, :40] = (176, 220, 220)
        hsv[20:, :40] = (116, 220, 220)
        hsv[:4, 40:44] = (176, 220, 220)
        masks = np.zeros((2, 40, 80), np.uint8)
        masks[0, :, :40] = 1
        masks[1, :, 40:] = 1
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        actual = sample_colors(frame, masks, settings, interior=False)
        self.assert_original_evidence(actual, full_image_reference(frame, masks, settings, False))
        self.assertEqual([r['reason'] for r in actual[1]], ['mixed color votes', 'too few colored pixels'])

    def test_no_detections_do_not_convert_the_image(self):
        with patch('common.color_analysis.cv2.cvtColor') as convert:
            self.assertEqual(sample_colors(np.zeros((720, 1280, 3), np.uint8), [], SimpleNamespace()), ([], []))
            convert.assert_not_called()


class InteriorSamplingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'colors.json'
        self.data = json.loads((VISION/'configs/colors.json').read_text())
        # Isolate the ordinary check so a side result cannot hide its behavior.
        self.data['side_sampling']['enabled'] = False
        self.hsv = np.full((10, 20, 3), (0, 0, 220), np.uint8)
        self.masks = np.ones((1, 10, 20), np.uint8)

    def analyze(self, **limits):
        """Load edited JSON and classify a fixed, independently defined image."""
        self.data['interior_sampling'].update(limits)
        self.path.write_text(json.dumps(self.data))
        settings = Settings.load(self.path)
        return sample_colors(cv2.cvtColor(self.hsv, cv2.COLOR_HSV2BGR), self.masks,
                             settings, interior=False)[0]

    def test_json_min_pixels_controls_ordinary_acceptance(self):
        self.hsv.reshape(-1, 3)[:20] = (176, 220, 200)
        self.assertEqual(self.analyze(), ['unknown'])
        self.assertEqual(self.analyze(min_pixels=20), ['red'])

    def test_json_min_coverage_controls_ordinary_acceptance(self):
        self.hsv.reshape(-1, 3)[:30] = (176, 220, 200)
        self.assertEqual(self.analyze(), ['red'])
        self.assertEqual(self.analyze(min_coverage=.20), ['unknown'])

    def test_json_min_dominance_controls_ordinary_acceptance(self):
        self.hsv.reshape(-1, 3)[:50] = (176, 220, 200)
        self.hsv.reshape(-1, 3)[50:90] = (116, 220, 200)
        self.assertEqual(self.analyze(), ['unknown'])
        self.assertEqual(self.analyze(min_dominance=.55), ['red'])

    def test_older_color_files_keep_the_previous_ordinary_limits(self):
        self.data.pop('interior_sampling')
        self.path.write_text(json.dumps(self.data))
        settings = Settings.load(self.path)
        self.assertEqual(vars(settings.interior_sampling),
                         dict(min_pixels=25, min_coverage=.10, min_dominance=.60))

    def test_invalid_ordinary_limits_are_rejected_when_loading_json(self):
        for control in [dict(min_pixels=0), dict(min_pixels=True), dict(min_pixels=2.5),
                        dict(min_coverage=0), dict(min_coverage=float('nan')),
                        dict(min_dominance=.5), dict(min_dominance=1.1)]:
            with self.subTest(control=control):
                self.data['interior_sampling'] = {**vars(InteriorSampling()), **control}
                self.path.write_text(json.dumps(self.data))
                with self.assertRaises(ValueError):
                    Settings.load(self.path)


class SideSamplingTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.load(VISION/'configs/colors.json')
        self.hsv = np.full((140, 200, 3), (0, 0, 220), np.uint8)
        self.masks = np.zeros((1, 140, 200), np.uint8)
        self.masks[0, 20:120, 20:180] = 1

    def paint_side(self, name, side, start=20, stop=120):
        """Paint a narrow label strip that the normal horizontal trim removes."""
        hue = self.settings.colors[name].hue
        columns = slice(21, 25) if side == 'left' else slice(175, 179)
        self.hsv[start:stop, columns] = (hue, 220, 200)

    def analyze(self):
        return sample_colors(cv2.cvtColor(self.hsv, cv2.COLOR_HSV2BGR), self.masks, self.settings)

    def test_white_center_with_two_narrow_sides_recovers_each_color(self):
        for name in COLORS:
            with self.subTest(color=name):
                self.hsv[:] = (0, 0, 220)
                for side in ('left', 'right'):
                    self.paint_side(name, side)
                frame = cv2.cvtColor(self.hsv, cv2.COLOR_HSV2BGR)
                self.assertEqual(full_image_reference(frame, self.masks, self.settings, True)[0], ['unknown'])
                labels, details = self.analyze()
                self.assertEqual(labels, [name])
                self.assertEqual(details[0]['sampling_method'], 'side_bands')
                self.assertEqual(details[0]['primary_analysis']['color'], 'unknown')
                self.assertGreaterEqual(details[0]['supported_row_fraction'], .35)
                json.dumps(details)  # Evidence must remain usable by the recording log.

    def test_one_visible_colored_side_is_enough_with_a_white_opposite_side(self):
        for side in ('left', 'right'):
            with self.subTest(side=side):
                self.hsv[:] = (0, 0, 220)
                self.paint_side('red', side)
                labels, details = self.analyze()
                self.assertEqual(labels, ['red'])
                self.assertEqual(details[0]['side_analysis']['bands'][side]['color'], 'red')

    def test_conflicting_sides_stay_unknown(self):
        self.paint_side('red', 'left')
        self.paint_side('blue', 'right')
        labels, details = self.analyze()
        self.assertEqual(labels, ['unknown'])
        self.assertEqual(details[0]['side_analysis']['result']['reason'], 'conflicting side colors')

    def test_small_colored_patch_does_not_pass_as_a_side_strip(self):
        self.hsv[45:60, 21:50] = (176, 220, 200)
        labels, details = self.analyze()
        self.assertEqual(labels, ['unknown'])
        left = details[0]['side_analysis']['bands']['left']
        self.assertEqual(left['reason'], 'color limited to a small patch')

    def test_white_can_and_colored_background_remain_unknown(self):
        self.hsv[:] = (116, 220, 200)
        self.masks[:] = 0
        cv2.ellipse(self.masks[0], (100, 70), (70, 45), 0, 0, 360, 255, -1)
        self.hsv[self.masks[0] > 0] = (0, 0, 220)
        self.assertEqual(self.analyze()[0], ['unknown'])

    def test_glare_and_color_below_hsv_limits_are_not_forced_to_a_color(self):
        self.paint_side('red', 'left')
        self.hsv[:, 21:25, 1] = 100
        self.assertEqual(self.analyze()[0], ['unknown'])

    def test_silver_rim_color_is_excluded_from_the_fallback(self):
        self.paint_side('blue', 'left', start=20, stop=30)
        self.assertEqual(self.analyze()[0], ['unknown'])

    def test_confirmed_interior_is_not_overridden(self):
        self.hsv[20:120, 20:180] = (116, 220, 200)
        self.paint_side('green', 'left')
        labels, details = self.analyze()
        self.assertEqual(labels, ['blue'])
        self.assertEqual(details[0]['sampling_method'], 'interior')
        self.assertNotIn('side_analysis', details[0])

    def test_mixed_interior_cannot_be_rescued_by_one_colored_side(self):
        self.hsv[20:120, 20:100] = (176, 220, 200)
        self.hsv[20:120, 100:180] = (116, 220, 200)
        labels, details = self.analyze()
        self.assertEqual(labels, ['unknown'])
        self.assertEqual(details[0]['reason'], 'mixed color votes')
        self.assertNotIn('side_analysis', details[0])

    def test_side_fallback_can_be_disabled(self):
        self.paint_side('red', 'left')
        self.settings.side_sampling.enabled = False
        labels, details = self.analyze()
        self.assertEqual(labels, ['unknown'])
        self.assertNotIn('side_analysis', details[0])

    def test_settings_accept_older_files_and_reject_invalid_side_controls(self):
        data = json.loads((VISION/'configs/colors.json').read_text())
        data.pop('side_sampling')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'colors.json'
            path.write_text(json.dumps(data))
            self.assertTrue(Settings.load(path).side_sampling.enabled)
        for control in [dict(enabled='yes'), dict(band_fraction=.6), dict(min_pixels=0),
                        dict(min_coverage=float('nan')), dict(min_dominance=.5), dict(min_row_fraction=0)]:
            with self.subTest(control=control), self.assertRaises(ValueError):
                replace(SideSampling(), **control)


if __name__ == '__main__':
    unittest.main()
