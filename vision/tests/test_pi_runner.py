"""Exercise repository entry points and preview throttling without hardware."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(VISION), str(VISION/'pi')]
from common.geometry import Boxes


class SyntheticBackend:
    instances = []

    def __init__(self, *args):
        self.closed = False
        self.__class__.instances.append(self)

    def predict(self, frame):
        height, width = frame.shape[:2]
        x0, x1 = width//2, 3*width//4
        y0, y1 = height//4, 3*height//4
        masks = np.zeros((1, height, width), np.uint8)
        masks[0, y0:y1, x0:x1] = 1
        return masks, Boxes([[x0, y0, x1, y1, .95, 0]], (height, width)), {'inference_ms': 0.}

    def close(self):
        self.closed = True


class PiRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.configs = self.root/'station'
        self.configs.mkdir()
        for name in ('runtime.json', 'colors.json', 'view.json'):
            shutil.copy2(VISION/'configs'/name, self.configs/name)
        runtime = json.loads((self.configs/'runtime.json').read_text())
        runtime['expected_recipe'] = dict(red=2, green=0, blue=0)
        (self.configs/'runtime.json').write_text(json.dumps(runtime))
        self.model = self.root/'synthetic.onnx'
        self.model.write_bytes(b'not a real model - backend is simulated')
        self.model.with_suffix('.onnx.json').write_text(json.dumps({
            'sha256': hashlib.sha256(self.model.read_bytes()).hexdigest(),
            'source_sha256': runtime['model_sha256'],
        }))
        self.session = self.root/'session'
        (self.session/'source_frames').mkdir(parents=True)
        rows = []
        for index in range(1, 9):
            cv2.imwrite(str(self.session/'source_frames'/f'{index:06d}.png'),
                        np.full((240, 320, 3), (0, 0, 240), np.uint8))
            rows.append(json.dumps(dict(index=index, timestamp_seconds=index/30)))
        (self.session/'observations.jsonl').write_text('\n'.join(rows))
        spec = importlib.util.spec_from_file_location('pi_runner_integration_test', VISION/'pi/run.py')
        self.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runner)
        SyntheticBackend.instances.clear()

    def run_trial(self, *options):
        args = ['--backend', 'onnx', '--model', str(self.model), '--session', str(self.session),
                '--config-dir', str(self.configs), '--output', str(self.root/'output'),
                '--auto-start', '--max-frames', '8', *options]
        with patch.object(self.runner, 'OnnxBackend', SyntheticBackend), \
                patch.object(self.runner.cv2, 'imshow') as show, \
                patch.object(self.runner.cv2, 'waitKey', return_value=255), \
                patch.object(self.runner.cv2, 'destroyAllWindows'), redirect_stdout(io.StringIO()):
            self.runner.main(args)
        folder = next((self.root/'output').iterdir())
        summary = json.loads((folder/'summary.json').read_text())
        metadata = json.loads((folder/'metadata.json').read_text())
        rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text().splitlines()]
        return summary, metadata, rows, show.call_count

    def test_headless_replay_uses_station_settings_and_closes_backend(self):
        summary, metadata, rows, shows = self.run_trial('--headless')
        self.assertEqual(summary['processed_frames'], 8)
        self.assertEqual(summary['final']['counts'], dict(red=1, green=0, blue=0))
        self.assertEqual(summary['final']['recipe'], dict(red=2, green=0, blue=0))
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]['pack']['total'], 0)
        self.assertEqual(rows[1]['pack']['total'], 1)
        self.assertEqual(shows, 0)
        self.assertEqual(metadata['code_root'], str(VISION))
        self.assertEqual(metadata['configurations']['runtime']['contents']['expected_recipe']['red'], 2)
        self.assertTrue(SyntheticBackend.instances[0].closed)
        self.assertFalse(summary['hardware_inference_executed'])

    def test_skipped_preview_draws_do_not_skip_analysis_or_counting(self):
        summary, _, rows, shows = self.run_trial('--preview-fps', '0.000001')
        self.assertEqual(shows, 1)
        self.assertEqual(summary['processed_frames'], 8)
        self.assertEqual(len(rows), 8)
        self.assertEqual(summary['final']['counts']['red'], 1)
        self.assertEqual(sum(len(row['transfer_events']) for row in rows), 1)
        self.assertTrue(all('render_ms' in row['timing_ms'] for row in rows))

    def test_preview_recording_keeps_every_analyzed_frame(self):
        summary, _, rows, shows = self.run_trial('--preview-fps', '0.000001', '--save-preview')
        self.assertEqual(shows, 1)
        images = list((Path(summary['output'])/'preview').glob('*.jpg'))
        self.assertEqual(len(images), len(rows))
        self.assertEqual(len(images), 8)
        self.assertEqual(summary['final']['counts']['red'], 1)

    def live_calibration_trial(self, saved_profile):
        """Simulate setup returning a profile while retaining the camera/model."""
        frame = cv2.cvtColor(np.full((240, 320, 3), (116, 100, 180), np.uint8), cv2.COLOR_HSV2BGR)
        class Camera:
            released = False
            def read(camera):
                return True, frame.copy()
            def isOpened(camera):
                return True
            def release(camera):
                camera.released = True
        camera = Camera()
        with patch.object(self.runner, 'OnnxBackend', SyntheticBackend), \
                patch.object(self.runner, 'open_camera', return_value=(camera, {})), \
                patch('yardspi.calibration.configure_camera', return_value=saved_profile) as setup, \
                patch.object(self.runner.cv2, 'imshow'), \
                patch.object(self.runner.cv2, 'waitKey', side_effect=[ord('p'), 255, 255, ord('q')]), \
                patch.object(self.runner.cv2, 'destroyAllWindows'), redirect_stdout(io.StringIO()):
            self.runner.main(['--backend', 'onnx', '--model', str(self.model), '--source', '0',
                              '--config-dir', str(self.configs), '--calibrate', '--output', str(self.root/'output')])
        return camera, setup

    def test_live_setup_profile_is_used_by_counter_and_recorded_in_metadata(self):
        profile = self.root/'calibrated-colors.json'
        colors = json.loads((self.configs/'colors.json').read_text())
        colors['colors']['blue']['saturation_min'] = 90
        profile.write_text(json.dumps(colors))
        camera, setup = self.live_calibration_trial(profile)
        folder = next((self.root/'output').iterdir())
        summary = json.loads((folder/'summary.json').read_text())
        metadata = json.loads((folder/'metadata.json').read_text())
        self.assertEqual(summary['processed_frames'], 3)
        self.assertEqual(summary['final']['counts']['blue'], 1)
        self.assertEqual(metadata['configurations']['colors']['path'], str(profile.resolve()))
        self.assertEqual(len(SyntheticBackend.instances), 1)
        self.assertIs(setup.call_args.args[0], camera)
        self.assertIs(setup.call_args.args[1], SyntheticBackend.instances[0])
        self.assertTrue(camera.released)
        self.assertTrue(SyntheticBackend.instances[0].closed)

    def test_cancelled_setup_starts_no_counting_or_recording_and_closes_resources(self):
        camera, _ = self.live_calibration_trial(None)
        self.assertFalse((self.root/'output').exists())
        self.assertTrue(camera.released)
        self.assertTrue(SyntheticBackend.instances[0].closed)

    def test_calibration_rejects_noninteractive_or_non_camera_inputs_before_opening(self):
        for options in [ ['--source', 'clip.mp4'], ['--source', '0', '--headless'],
                         ['--source', '0', '--auto-start'], ['--source', '0', '--probe-camera'] ]:
            with self.subTest(options=options), patch.object(self.runner, 'open_camera') as camera, \
                    patch.object(self.runner, 'OnnxBackend') as model, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.runner.main(['--backend', 'onnx', '--calibrate', *options])
                camera.assert_not_called()
                model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
