"""Check Windows capture orientation and source recording without real devices.

CS488 Capstone, Team 1.
"""

from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
from common.camera import (
    has_image_signal,
    open_source,
    orient_frame,
    orientation_path,
    recorded_rotation,
)
from common.recording import Trial
from common.video import encoder_executable


class CameraRecordingTests(unittest.TestCase):
    """Keep source images, acquisition times and saved orientation consistent."""

    def test_orientation_sidecar_prevents_a_second_rotation(self):
        """Rotate a source once and preserve already-oriented recordings on replay."""
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "clip.mp4"
            self.assertFalse(recorded_rotation(video))
            sidecar = orientation_path(video)
            sidecar.write_text(json.dumps(dict(version=1, rotate_180=True)))
            self.assertTrue(recorded_rotation(video))
            frame = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
            np.testing.assert_array_equal(orient_frame(frame, True), frame[::-1, ::-1])
            self.assertIs(orient_frame(frame, True, True), frame)
            sidecar.write_text(json.dumps(dict(version=1, rotate_180="yes")))
            with self.assertRaises(ValueError):
                recorded_rotation(video)

    def test_blank_camera_is_released_instead_of_accepted(self):
        """Reject a device that opens successfully but only returns constant pixels."""
        capture = SimpleNamespace(
            isOpened=lambda: True,
            set=lambda *args: True,
            read=lambda: (True, np.full((20, 20, 3), 80, np.uint8)),
        )
        capture.release = unittest.mock.Mock()
        with patch("common.camera.cv2.VideoCapture", return_value=capture):
            with self.assertRaisesRegex(RuntimeError, "no usable image"):
                open_source("0", "dshow", 1280, 720)
        capture.release.assert_called_once()
        self.assertFalse(has_image_signal(None))

    def test_camera_and_file_sources_use_the_expected_capture_options(self):
        """Configure live dimensions while leaving file sources independent of the camera API."""
        capture = unittest.mock.Mock()
        capture.isOpened.return_value = True
        capture.read.return_value = (True, np.arange(120, dtype=np.uint8).reshape(4, 10, 3))
        with patch("common.camera.cv2.VideoCapture", return_value=capture) as factory:
            opened, is_camera = open_source("0", "dshow", 1280, 720)
            self.assertIs(opened, capture)
            self.assertTrue(is_camera)
            capture.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            factory.assert_called_once_with(0, cv2.CAP_DSHOW)
        with patch("common.camera.cv2.VideoCapture", return_value=capture) as factory:
            _, is_camera = open_source("clip.mp4", "dshow", 1280, 720)
            self.assertFalse(is_camera)
            factory.assert_called_once_with("clip.mp4", cv2.CAP_ANY)

    def test_recording_retains_actual_images_times_and_final_summary(self):
        """Save two real PNG sources while substituting only the FFmpeg process."""
        with tempfile.TemporaryDirectory() as folder:
            trial = Trial({"rotate_180": True}, folder, "synthetic-ffmpeg")
            frame = np.full((40, 60, 3), (0, 0, 200), np.uint8)
            for index, timestamp in ((1, 0.1), (2, 0.3)):
                trial.add(
                    frame,
                    frame,
                    dict(
                        index=index,
                        timestamp_seconds=timestamp,
                        pattern_matches_now=index == 2,
                        confirmed={},
                        five_frame_span_seconds=None,
                    ),
                )
            with patch(
                "common.recording.subprocess.run", return_value=SimpleNamespace(returncode=0)
            ) as encode:
                trial.close()
            self.assertEqual(encode.call_count, 2)
            summary = json.loads((trial.path / "summary.json").read_text())
            self.assertEqual(summary["processed_frames"], 2)
            self.assertEqual(summary["first_pattern_match"]["frame"], 2)
            self.assertTrue(summary["preview_terminal_duplicate"])
            np.testing.assert_array_equal(
                cv2.imread(str(trial.path / "source_frames/000001.png")), frame
            )
            lines = (trial.path / "observations.jsonl").read_text().splitlines()
            self.assertEqual([json.loads(line)["timestamp_seconds"] for line in lines], [0.1, 0.3])
            with self.assertRaisesRegex(ValueError, "closed"):
                trial.add(frame, frame, {})
            trial.close()

    def test_recording_failure_keeps_source_evidence_and_error_summary(self):
        """Retain acquisition images even if final video encoding fails."""
        with tempfile.TemporaryDirectory() as folder:
            trial = Trial({"rotate_180": False}, folder, "synthetic-ffmpeg")
            image = np.zeros((20, 20, 3), np.uint8)
            trial.add(image, image, dict(index=1, timestamp_seconds=0.1, pattern_matches_now=False))
            with patch(
                "common.recording.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stderr=b"encode failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "encoding failed"):
                    trial.close()
            summary = json.loads((trial.path / "summary.json").read_text())
            self.assertIn("acquisition images retained", summary["recording_status"])
            self.assertTrue((trial.path / "source_frames/000001.png").is_file())

    def test_encoder_uses_the_bundled_ffmpeg_path(self):
        """Use the executable supplied by imageio rather than assuming a machine path."""
        with patch.dict(
            sys.modules, imageio_ffmpeg=SimpleNamespace(get_ffmpeg_exe=lambda: "bundled-ffmpeg")
        ):
            self.assertEqual(encoder_executable(), "bundled-ffmpeg")


if __name__ == "__main__":
    unittest.main()
