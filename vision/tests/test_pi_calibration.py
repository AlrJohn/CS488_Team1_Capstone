"""Exercise the setup workflow and screen with simulated camera/model inputs."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(VISION), str(VISION/'pi')]
from common.color_calibration import CalibrationPolicy
from common.geometry import Boxes
from common.settings import COLORS, Settings
from yardspi import calibration


class PiCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.policy = replace(CalibrationPolicy.load(VISION/'configs/calibration.json'),
                              collection_frames=5, verification_frames=5, sample_interval_seconds=.01)
        self.base = json.loads((VISION/'configs/colors.json').read_text())

    def test_missing_masks_count_as_unknown_in_fresh_verification(self):
        session = calibration.CalibrationSession(self.base, self.policy)
        session.phase, session.settings = 'verify', Settings.from_dict(self.base)
        session.action('verify', 0.)
        frame = np.zeros((50, 50, 3), np.uint8)
        for index in range(5):
            session.observe(frame, None, 'red', index*.1)
        result = session.verification['red'].summary()
        self.assertEqual(result['unknown'], 5)
        self.assertFalse(result['passed'])
        self.assertFalse(session.can_save())

    def test_collection_times_out_and_does_not_fit_an_empty_sample(self):
        session = calibration.CalibrationSession(self.base, self.policy)
        session.seeds['red'] = dict(hue=176, saturation=220, value=200)
        session.action('collect', 0.)
        session.observe(np.zeros((50, 50, 3), np.uint8), None, 'unknown', 25.)
        self.assertIsNone(session.active)
        with self.assertRaises(ValueError):
            session.action('fit', 26.)

    def test_recollect_invalidates_the_previous_candidate_and_all_verifications(self):
        session = calibration.CalibrationSession(self.base, self.policy)
        session.profile, session.settings, session.phase = self.base, Settings.from_dict(self.base), 'verify'
        session.action('redo', 0.)
        self.assertIsNone(session.profile)
        self.assertEqual(session.verification, {})
        self.assertEqual(session.phase, 'collect')

    def test_image_click_mapping_rejects_letterbox_and_accounts_for_context(self):
        transform = (100, 200, .5, .5, 500, 300)
        self.assertEqual(calibration.image_point((150, 250), transform, (20, 30)), (80, 70))
        self.assertIsNone(calibration.image_point((10, 250), transform, (20, 30)))

    def test_complete_mouse_and_keyboard_setup_saves_a_loadable_profile(self):
        real_session, real_draw = calibration.CalibrationSession, calibration.draw_screen
        state = dict(clock=0., display=None, session=None, callback=None, waits=0)
        def create_session(*args):
            state['session'] = real_session(*args)
            return state['session']
        def draw(*args):
            result = real_draw(*args)
            state['display'] = result[1]
            self.assertEqual(result[0].shape, (860, 1280, 3))
            return result
        def tick():
            state['clock'] += .1
            return state['clock']
        class Camera:
            def read(camera):
                target = state['session'].target
                hue = self.base['colors'][target]['hue']
                hsv = np.full((140, 200, 3), (0, 0, 220), np.uint8)
                hsv[20:120, 41:49] = (hue, 100, 150)
                hsv[20:120, 151:159] = (hue, 100, 150)
                return True, cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        class Backend:
            def predict(backend, frame):
                mask = np.zeros((1, 140, 200), np.uint8)
                mask[0, 20:120, 40:160] = 1
                return mask, Boxes([[40, 20, 160, 120, .95, 0]], (140, 200)), {}
        def wait_key(_):
            state['waits'] += 1
            self.assertLess(state['waits'], 150, 'Setup failed to finish')
            session = state['session']
            if state['waits'] == 1 or session.active:
                return 255
            if session.phase == 'collect':
                if session.target not in session.seeds:
                    left, top, sx, sy, _, _ = state['display']
                    state['callback'](cv2.EVENT_LBUTTONDOWN, round(left+45*sx), round(top+60*sy), 0, None)
                    return 255
                if len(session.samples[session.target]) < self.policy.collection_frames:
                    return ord('c')
                for index, name in enumerate(COLORS):
                    if len(session.samples[name]) < self.policy.collection_frames:
                        return ord(str(index+1))
                return ord('f')
            if session.can_save():
                return ord('s')
            if session.target not in session.verification:
                return ord('v')
            self.assertTrue(session.verification[session.target].summary()['passed'])
            for index, name in enumerate(COLORS):
                if name not in session.verification:
                    return ord(str(index+1))
            self.fail('Unexpected verification state')
        runtime = json.loads((VISION/'configs/runtime.json').read_text())
        runtime['rotate_180'] = False
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(calibration, 'CalibrationSession', side_effect=create_session), \
                patch.object(calibration, 'draw_screen', side_effect=draw), \
                patch.object(calibration, 'measure_delivery', return_value={'delivered_fps': 15.}), \
                patch.object(calibration.time, 'perf_counter', side_effect=tick), \
                patch.object(calibration.cv2, 'namedWindow'), patch.object(calibration.cv2, 'resizeWindow'), \
                patch.object(calibration.cv2, 'imshow'), patch.object(calibration.cv2, 'destroyWindow'), \
                patch.object(calibration.cv2, 'getWindowProperty', return_value=1.), \
                patch.object(calibration.cv2, 'setMouseCallback', side_effect=lambda window, cb: state.update(callback=cb)), \
                patch.object(calibration.cv2, 'waitKey', side_effect=wait_key):
            saved = calibration.configure_camera(Camera(), Backend(), runtime,
                                                  dict(normalized_xywh=[0, 0, 1, 1]), self.base,
                                                  self.policy, folder, preview_fps=0)
            self.assertTrue(saved.is_file())
            Settings.load(saved)
            data = json.loads(saved.read_text())
            self.assertTrue(all(data['calibration']['verification'][name]['passed'] for name in COLORS))
            self.assertEqual(data['interior_sampling'], self.base['interior_sampling'])
            self.assertEqual(data['side_sampling'], self.base['side_sampling'])
            self.assertLess(data['colors']['red']['saturation_min'], 150)
            self.assertFalse(data['calibration']['camera_delivery']['inference_during_measurement'])
            self.assertTrue(data['calibration']['camera_delivery']['model_loaded'])
            self.assertTrue(all(len(state['session'].samples[name]) == self.policy.collection_frames for name in COLORS))


if __name__ == '__main__':
    unittest.main()
