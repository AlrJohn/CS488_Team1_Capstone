"""Camera delivery and CLI checks using a simulated capture device."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2

VISION = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(VISION), str(VISION/'pi')]
from yardspi.camera import open_camera, measure_delivery


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now


class FakeCapture:
    def __init__(self, clock=None):
        self.clock = clock or Clock()
        self.released = False
        self.requests = {}

    def isOpened(self):
        return True

    def set(self, key, value):
        self.requests[key] = value
        return True

    def get(self, key):
        return self.requests.get(key, 0.)

    def read(self):
        self.clock.now += .04  # Actual 25 FPS, irrespective of the request.
        return True, None

    def release(self):
        self.released = True


class PiCameraTests(unittest.TestCase):
    def test_delivery_uses_elapsed_reads_instead_of_reported_fps(self):
        clock = Clock()
        cap = FakeCapture(clock)
        cap.set(cv2.CAP_PROP_FPS, 30.)
        result = measure_delivery(cap, seconds=1., warmup_seconds=.2, clock=clock)
        self.assertAlmostEqual(result['delivered_fps'], 25.)
        self.assertAlmostEqual(result['read_interval_ms']['median'], 40.)
        self.assertFalse(result['model_loaded'])
        self.assertFalse(result['image_saving'])

    def test_probe_read_failure_is_reported(self):
        cap = FakeCapture()
        with patch.object(cap, 'read', return_value=(False, None)):
            with self.assertRaisesRegex(RuntimeError, 'delivery measurement'):
                measure_delivery(cap, seconds=1., warmup_seconds=0., clock=cap.clock)

    def test_camera_settings_include_mjpeg_and_requested_dimensions(self):
        cap = FakeCapture()
        with patch('yardspi.camera.cv2.VideoCapture', return_value=cap):
            actual, info = open_camera(0, 640, 480, 'MJPG', 30.)
        self.assertIs(actual, cap)
        self.assertEqual(info['actual_fourcc'], 'MJPG')
        self.assertEqual(info['actual_size'], [640, 480])
        self.assertEqual(info['reported_fps'], 30.)

    def test_failed_open_releases_device(self):
        cap = FakeCapture()
        with patch('yardspi.camera.cv2.VideoCapture', return_value=cap), patch.object(cap, 'isOpened', return_value=False):
            with self.assertRaises(RuntimeError):
                open_camera(0)
        self.assertTrue(cap.released)

    def test_invalid_camera_parameters_do_not_open_a_device(self):
        with patch('yardspi.camera.cv2.VideoCapture') as create:
            for kwargs in [dict(width=0), dict(fps=float('nan')), dict(pixel_format='BAD')]:
                with self.assertRaises(ValueError):
                    open_camera(0, **kwargs)
            create.assert_not_called()

    def test_probe_cli_does_not_load_hailo_or_open_gpio(self):
        spec = importlib.util.spec_from_file_location('pi_runner_probe_test', VISION/'pi/run.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        cap = FakeCapture()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(runner, 'open_camera', return_value=(cap, {'reported_fps': 30.})), \
                patch.object(runner, 'measure_delivery', return_value={'delivered_fps': 15.}), \
                patch.object(runner, 'HailoBackend') as hailo, \
                patch.object(runner, 'StackLights') as lights, redirect_stdout(io.StringIO()):
            runner.main(['--probe-camera', '--source', '0', '--seconds', '1', '--output', folder])
            saved = list(Path(folder).glob('camera-probe-*.json'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(json.loads(saved[0].read_text())['delivered_fps'], 15.)
            hailo.assert_not_called()
            lights.assert_not_called()
        self.assertTrue(cap.released)


if __name__ == '__main__':
    unittest.main()
