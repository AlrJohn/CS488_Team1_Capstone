"""Test supervised HSV fitting, held-out decisions and local profile saving."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
from common.color_calibration import (CalibrationPolicy, Verification, collect_pixels,
                                      fit_profile, save_profile, select_seed)
from common.settings import COLORS, Settings


class ColorCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.policy = replace(CalibrationPolicy.load(VISION/'configs/calibration.json'),
                              collection_frames=5, verification_frames=5)
        self.base = json.loads((VISION/'configs/colors.json').read_text())
        self.seeds = {name: dict(hue=hue, saturation=100., value=150.)
                      for name, hue in zip(COLORS, [179, 70, 117])}
        self.samples = {name: [np.tile([seed['hue'], 100, 150], (100, 1)).astype(np.uint8)
                              for _ in range(self.policy.collection_frames)]
                        for name, seed in self.seeds.items()}

    def test_seed_rejects_white_and_pixels_outside_the_can(self):
        frame = np.full((40, 80, 3), 220, np.uint8)
        frame[10:30, 20:30] = (0, 0, 240)
        mask = np.zeros((40, 80), np.uint8)
        mask[10:30, 20:60] = 1
        seed = select_seed(frame, mask, (25, 20), self.policy)
        self.assertLessEqual(seed['hue'], 2)
        for point in [(45, 20), (5, 5), (-1, 20)]:
            with self.subTest(point=point), self.assertRaises(ValueError):
                select_seed(frame, mask, point, self.policy)

    def test_collection_excludes_printing_and_background_and_is_bounded(self):
        hsv = np.full((100, 100, 3), (116, 220, 220), np.uint8)
        mask = np.zeros((100, 100), np.uint8)
        mask[10:90, 20:80] = 1
        hsv[mask > 0] = (0, 0, 220)
        hsv[10:90, 21:27] = (179, 100, 150)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        seed = dict(hue=179, saturation=100, value=150)
        pixels = collect_pixels(frame, mask, seed, replace(self.policy, max_pixels_per_frame=60))
        self.assertEqual(len(pixels), 60)
        self.assertTrue(np.all(pixels[:, 1] > 80))
        self.assertTrue(np.all((pixels[:, 0] >= 175) | (pixels[:, 0] <= 3)))

    def test_fit_handles_red_wrap_preserves_other_controls_and_does_not_mutate_base(self):
        before = deepcopy(self.base)
        for frame in self.samples['red']:
            frame[::2, 0] = 0
        profile, report = fit_profile(self.base, self.samples, self.seeds, self.policy)
        Settings.from_dict(profile)
        self.assertEqual(self.base, before)
        self.assertEqual(profile['interior_sampling'], self.base['interior_sampling'])
        self.assertEqual(profile['side_sampling'], self.base['side_sampling'])
        self.assertLess(profile['colors']['blue']['saturation_min'], self.base['colors']['blue']['saturation_min'])
        self.assertTrue(profile['colors']['red']['hue'] >= 175 or profile['colors']['red']['hue'] <= 3)
        self.assertTrue(all(value['selected_pixel_recall'] >= .9 for value in report.values()))

    def test_fit_requires_all_colors_and_rejects_similar_or_mislabeled_seeds(self):
        with self.assertRaisesRegex(ValueError, 'green'):
            fit_profile(self.base, {**self.samples, 'green': []}, self.seeds, self.policy)
        seeds = deepcopy(self.seeds)
        seeds['blue']['hue'] = 70
        samples = deepcopy(self.samples)
        for values in samples['blue']:
            values[:, 0] = 70
        with self.assertRaises(ValueError):
            fit_profile(self.base, samples, seeds, self.policy)

    def test_old_profiles_get_explicit_effective_color_limits_when_fitted(self):
        self.base.pop('interior_sampling')
        self.base.pop('side_sampling')
        profile, _ = fit_profile(self.base, self.samples, self.seeds, self.policy)
        self.assertEqual(profile['interior_sampling']['min_pixels'], 25)
        self.assertEqual(profile['side_sampling']['min_pixels'], 40)

    def test_verification_counts_unknowns_and_wrong_colors_instead_of_skipping_them(self):
        item = Verification('red', self.policy)
        for prediction in ['red', 'red', 'unknown', 'blue', 'red']:
            item.add(prediction)
        result = item.summary()
        self.assertEqual((result['total'], result['correct'], result['wrong'], result['unknown']), (5, 3, 1, 1))
        self.assertFalse(result['passed'])
        item.add('red')
        self.assertEqual(item.summary()['total'], 5)

    def test_saving_requires_all_verified_colors_and_never_overwrites_a_profile(self):
        profile, report = fit_profile(self.base, self.samples, self.seeds, self.policy)
        verification = {name: Verification(name, self.policy) for name in COLORS}
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                save_profile(folder, profile, verification, dict(fit=report))
            self.assertEqual(list(Path(folder).iterdir()), [])
            for name, item in verification.items():
                for _ in range(self.policy.verification_frames):
                    item.add(name)
            first = save_profile(folder, profile, verification, dict(fit=report))
            original = first.read_bytes()
            second = save_profile(folder, profile, verification, dict(fit=report))
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original)
            Settings.load(first)
            self.assertTrue(json.loads(first.read_text())['calibration']['verification']['blue']['passed'])

    def test_policy_is_json_controlled_and_rejects_invalid_limits(self):
        self.assertEqual(CalibrationPolicy(**asdict(self.policy)), self.policy)
        for changes in [dict(collection_frames=0), dict(probe_seconds=float('nan')),
                        dict(seed_hue_window=90), dict(max_hue_tolerance=45),
                        dict(minimum_verification_accuracy=1.1), dict(collection_timeout_seconds=.1)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.policy, **changes)


if __name__ == '__main__':
    unittest.main()
