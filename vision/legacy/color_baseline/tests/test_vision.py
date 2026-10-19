"""Behavioral tests for counting mistakes that matter during a camera trial."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from yards_vision.config import COLORS, ColorRange, Settings, parse_recipe
from yards_vision.counting import BatchCounter
from yards_vision.demo import DEMO_FRAMES, demo_frame
from yards_vision.detection import color_mask, detect
from yards_vision.pipeline import Pipeline
from yards_vision.app import Desktop, main, open_source, orient_frame, recorded_rotation
from yards_vision.presentation import PresentationRecorder, encoder_executable

PIXELS = {"red": (0, 0, 220), "green": (0, 190, 0), "blue": (220, 0, 0)}


def scene(*objects):
    frame = np.full((480, 640, 3), 30, np.uint8)
    for color, x, y in objects:
        cv2.ellipse(frame, (round(x * 640), round(y * 480)), (18, 29), 0, 0, 360, PIXELS[color], -1)
    return frame


def bench():
    settings = Settings()
    settings.recipe = dict.fromkeys(COLORS, 1)
    return settings


class ColorDetectionTests(unittest.TestCase):
    def test_red_wraps_around_hue_zero(self):
        hsv = np.array([[[178, 220, 180], [2, 220, 180], [60, 220, 180]]], np.uint8)
        self.assertEqual(color_mask(hsv, ColorRange(0, 10)).tolist(), [[255, 255, 0]])

    def test_three_separate_colors_and_neutral_glare(self):
        frame = scene(("red", .2, .25), ("green", .2, .5), ("blue", .2, .75))
        cv2.rectangle(frame, (350, 100), (400, 150), (240, 240, 240), -1)
        detections, _, warnings = detect(frame, bench())
        self.assertCountEqual([d.color for d in detections], COLORS)
        self.assertFalse(warnings)

    def test_moderate_brightness_change_preserves_colors(self):
        frame = scene(("red", .2, .25), ("green", .2, .5), ("blue", .2, .75))
        frame = (frame.astype(float) * 0.55).astype(np.uint8)
        detections, _, _ = detect(frame, bench())
        self.assertCountEqual([d.color for d in detections], COLORS)

    def test_roi_excludes_colored_background_outside_work_area(self):
        settings = bench()
        settings.roi = [.1, .1, .8, .8]
        detections, _, _ = detect(scene(("red", .2, .5), ("blue", .97, .5)), settings)
        self.assertEqual([d.color for d in detections], ["red"])

    def test_large_exit_blob_requests_review_instead_of_counting_a_group_as_one(self):
        frame = scene()
        cv2.rectangle(frame, (310, 100), (600, 350), PIXELS["red"], -1)
        detections, _, warnings = detect(frame, bench())
        self.assertFalse(detections)
        self.assertTrue(warnings)

    def test_unusable_region_beyond_transfer_band_does_not_block_a_finished_pick(self):
        settings = bench()
        settings.transfer_band = [.14, .22]
        frame = scene()
        cv2.rectangle(frame, (500, 100), (639, 450), PIXELS["blue"], -1)
        detections, _, warnings = detect(frame, settings)
        self.assertFalse(detections)
        self.assertFalse(warnings)
        cv2.rectangle(frame, (330, 100), (639, 450), PIXELS["blue"], -1)
        _, _, warnings = detect(frame, settings)
        self.assertTrue(warnings)


class PickAndReturnTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = Pipeline(bench())
        self.index = 0

    def feed(self, objects=(), frames=1):
        result = None
        for _ in range(frames):
            result = self.pipeline.process(scene(*objects), self.index / 30, self.index)
            self.index += 1
        return result

    def move(self, xs, color="red", y=.5):
        for x in xs:
            self.feed(((color, x, y),))

    def events(self):
        return [e for e in self.pipeline.counter.events if e["event"] in ("pick", "return")]

    def pick(self):
        self.move([.3] * 5 + list(np.linspace(.3, .7, 20)) + [.7] * 5)

    def test_still_can_does_not_count(self):
        self.feed((("red", .3, .5),), 40)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.assertFalse(self.events())

    def test_pick_counts_once_while_held_on_exit_side(self):
        self.pick()
        self.feed((("red", .7, .5),), 60)
        self.assertEqual(self.pipeline.counter.counts["red"], 1)
        self.assertEqual(len(self.events()), 1)

    def test_return_subtracts_and_second_pick_adds_again(self):
        self.pick()
        self.move(list(np.linspace(.7, .3, 20)) + [.3] * 5)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.move(list(np.linspace(.3, .7, 20)) + [.7] * 5)
        self.assertEqual([e["delta"] for e in self.events()], [1, -1, 1])

    def test_jitter_inside_dead_band_does_not_count(self):
        self.move([.3] * 5 + list(np.linspace(.3, .49, 15)))
        self.move([.49, .51, .50, .48, .52] * 10)
        self.assertFalse(self.events())
        self.assertEqual(self.pipeline.counter.counts["red"], 0)

    def test_new_track_can_return_after_original_left_camera_view(self):
        self.pick()
        self.move(list(np.linspace(.7, 1.1, 20)))
        self.feed(frames=20)
        self.move([.9] * 5 + list(np.linspace(.9, .3, 35)) + [.3] * 5)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.assertEqual([e["delta"] for e in self.events()], [1, -1])
        self.assertFalse(self.pipeline.counter.reviews)

    def test_unmatched_return_never_makes_count_negative(self):
        self.move([.8] * 5 + list(np.linspace(.8, .3, 25)) + [.3] * 5)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.assertTrue(self.pipeline.counter.reviews)

    def test_one_frame_occlusion_can_recover_without_a_duplicate(self):
        self.move([.3] * 5 + list(np.linspace(.3, .46, 12)))
        self.feed()
        self.move(list(np.linspace(.47, .7, 15)) + [.7] * 5)
        self.assertEqual(self.pipeline.counter.counts["red"], 1)
        self.assertFalse(self.pipeline.counter.reviews)

    def test_long_occlusion_across_boundary_requires_review_and_does_not_guess(self):
        self.move([.4] * 5 + [.46] * 3)
        self.feed(frames=6)
        self.move([.54] * 5 + [.6] * 5)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.assertTrue(self.pipeline.counter.reviews)
        self.assertEqual(self.pipeline.counter.status(self.index / 30), "REVIEW NEEDED")

    def test_disappearance_inside_lane_is_not_a_pick(self):
        self.feed((("red", .3, .5),), 5)
        self.feed(frames=20)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.assertTrue(self.pipeline.counter.reviews)

    def test_too_brief_lane_observation_is_not_silently_accepted_as_a_pick(self):
        self.move([.46] * 2 + [.54] * 5)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)
        self.assertTrue(self.pipeline.counter.reviews)

    def test_two_same_color_tracks_merging_require_review(self):
        self.feed((("red", .28, .5), ("red", .42, .5)), 5)
        frame = scene()
        cv2.ellipse(frame, (round(.35 * 640), 240), (68, 30), 0, 0, 360, PIXELS["red"], -1)
        self.pipeline.process(frame, self.index / 30, self.index)
        self.assertTrue(self.pipeline.counter.reviews)
        self.assertEqual(self.pipeline.counter.counts["red"], 0)

    def test_demo_includes_a_return_and_finishes_one_of_each(self):
        pipeline = Pipeline(bench())
        for index in range(DEMO_FRAMES):
            result = pipeline.process(demo_frame(index), index / 30, index)
        self.assertEqual(pipeline.counter.counts, dict.fromkeys(COLORS, 1))
        self.assertEqual(result["status"], "READY")
        self.assertFalse(pipeline.counter.reviews)
        self.assertEqual([e["event"] for e in pipeline.counter.events], ["pick", "return", "pick", "pick", "pick"])

    def test_transfer_band_ignores_occluded_inventory_outside_the_transfer(self):
        self.pipeline.settings.transfer_band = [.14, .22]
        self.feed((("red", .2, .5),), 10)
        self.feed(frames=30)
        self.assertFalse(self.pipeline.counter.reviews)
        self.assertFalse(self.pipeline.tracker.tracks)
        self.assertFalse(self.events())

    def test_transfer_band_counts_picks_and_returns_then_retires_expected_departures(self):
        self.pipeline.settings.transfer_band = [.14, .22]
        self.move(list(np.linspace(.2, .9, 65)))
        self.feed(frames=20)
        self.assertEqual(self.pipeline.counter.counts["red"], 1)
        self.assertFalse(self.pipeline.tracker.tracks)
        self.move(list(np.linspace(.9, .2, 65)))
        self.feed(frames=20)
        self.assertEqual([e["delta"] for e in self.events()], [1, -1])
        self.assertFalse(self.pipeline.counter.reviews)
        self.assertFalse(self.pipeline.tracker.tracks)

    def test_transfer_band_still_requires_review_for_a_lost_can_inside_it(self):
        self.pipeline.settings.transfer_band = [.14, .22]
        self.feed((("red", .4, .5),), 6)
        self.feed(frames=20)
        self.assertTrue(self.pipeline.counter.reviews)
        self.assertFalse(self.events())


class BatchAndStagedTests(unittest.TestCase):
    def test_exact_recipe_and_settling_are_required_for_ready(self):
        ledger = BatchCounter(dict.fromkeys(COLORS, 1))
        for index, color in enumerate(COLORS):
            ledger.apply(index, color, 1, 1.0)
        self.assertEqual(ledger.status(1.2), "WAIT")
        self.assertEqual(ledger.status(2.0), "READY")
        self.assertEqual(ledger.status(2.0, pending=True), "WAIT")
        ledger.apply(7, "red", 1, 2.1)
        self.assertEqual(ledger.status(3.0), "TOO MANY CANS")

    def test_review_blocks_an_otherwise_complete_recipe(self):
        ledger = BatchCounter(dict.fromkeys(COLORS, 1))
        ledger.counts = dict.fromkeys(COLORS, 1)
        ledger.review("Can hidden during transfer", 1.0)
        self.assertEqual(ledger.status(3.0), "REVIEW NEEDED")
        ledger.acknowledge_review(3.0)
        self.assertEqual(ledger.status(4.0), "READY")

    def test_new_batch_does_not_inherit_counts_or_track_identities(self):
        pipeline = Pipeline(bench())
        pipeline.counter.apply(1, "red", 1, 1.0)
        pipeline.reset(2.0, completed=True)
        self.assertEqual(pipeline.counter.counts, dict.fromkeys(COLORS, 0))
        self.assertEqual(pipeline.counter.batch, 2)
        self.assertEqual(pipeline.counter.events[-1]["event"], "carton_completed")
        self.assertFalse(pipeline.tracker.tracks)

    def test_staged_mode_requires_a_quiet_complete_arrangement(self):
        pipeline = Pipeline(bench(), "staged")
        frame = scene(("red", .2, .25), ("green", .4, .5), ("blue", .7, .75))
        for index in range(35):
            result = pipeline.process(frame, index / 30, index)
        self.assertEqual(result["status"], "READY")
        moving_hand = frame.copy()
        cv2.rectangle(moving_hand, (400, 20), (550, 150), (170, 170, 170), -1)
        result = pipeline.process(moving_hand, 1.2, 36)
        self.assertNotEqual(result["status"], "READY")

    def test_staged_mode_rejects_wrong_mix_even_when_total_is_correct(self):
        pipeline = Pipeline(bench(), "staged")
        frame = scene(("red", .2, .25), ("red", .4, .5), ("blue", .7, .75))
        for index in range(35):
            result = pipeline.process(frame, index / 30, index)
        self.assertEqual(result["status"], "TOO MANY CANS")

    def test_staged_mode_reviews_unresolved_extra_regions_anywhere_in_roi(self):
        settings = bench()
        settings.transfer_band = [.14, .22]
        pipeline = Pipeline(settings, "staged")
        frame = scene(("red", .6, .25), ("green", .6, .5), ("blue", .8, .75))
        cv2.rectangle(frame, (10, 30), (220, 450), PIXELS["red"], -1)
        for index in range(35):
            result = pipeline.process(frame, index / 30, index)
        self.assertEqual(result["status"], "REVIEW NEEDED")


class CameraOpeningTests(unittest.TestCase):
    def test_windows_auto_recovers_when_directshow_cannot_open_camera(self):
        unavailable = Mock()
        unavailable.isOpened.return_value = False
        available = Mock()
        available.isOpened.return_value = True
        available.read.return_value = (True, scene(("red", .3, .5)))
        with patch("yards_vision.app.sys.platform", "win32"), patch("yards_vision.app.cv2.VideoCapture", side_effect=[unavailable, available]) as factory:
            capture, camera = open_source("0", "auto", 1280, 720)
        self.assertIs(capture, available)
        self.assertTrue(camera)
        unavailable.release.assert_called_once()
        available.release.assert_not_called()
        self.assertEqual([call.args[1] for call in factory.call_args_list], [cv2.CAP_DSHOW, cv2.CAP_MSMF])

    def test_auto_rejects_a_backend_that_opens_but_only_returns_gray_frames(self):
        blank = Mock()
        blank.isOpened.return_value = True
        blank.read.return_value = (True, np.full((48, 64, 3), 16, np.uint8))
        available = Mock()
        available.isOpened.return_value = True
        available.read.return_value = (True, scene(("blue", .3, .5)))
        with patch("yards_vision.app.sys.platform", "win32"), patch("yards_vision.app.cv2.VideoCapture", side_effect=[blank, available]):
            capture, camera = open_source("0", "auto", 1280, 720)
        self.assertIs(capture, available)
        self.assertTrue(camera)
        blank.release.assert_called_once()

    def test_camera_becoming_blank_stops_and_logs_review(self):
        capture = Mock()
        capture.get.return_value = 30
        capture.read.return_value = (True, np.full((48, 64, 3), 16, np.uint8))
        with TemporaryDirectory() as directory:
            with patch("yards_vision.app.VISION", Path(directory)), patch("yards_vision.app.open_source", return_value=(capture, True)), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(["--headless", "--max-frames", "1"])
            logs = list(Path(directory).glob("runs/*/events.csv"))
            self.assertEqual(len(logs), 1)
            with logs[0].open(newline="", encoding="utf-8") as source:
                events = list(csv.DictReader(source))
            self.assertEqual(code, 1)
            self.assertEqual(events[0]["event"], "review")
            self.assertIn("blank image", events[0]["message"])
            self.assertFalse(list(Path(directory).glob("runs/*/summary.json")))
        capture.release.assert_called_once()

    def test_explicit_backend_failure_releases_camera_and_reports_error(self):
        unavailable = Mock()
        unavailable.isOpened.return_value = False
        with patch("yards_vision.app.cv2.VideoCapture", return_value=unavailable) as factory:
            with self.assertRaisesRegex(RuntimeError, "Cannot open source"):
                open_source("0", "dshow", 1280, 720)
        factory.assert_called_once_with(0, cv2.CAP_DSHOW)
        unavailable.release.assert_called_once()


class RecordingTests(unittest.TestCase):
    def test_presentation_preserves_elapsed_time_and_holds_earlier_views(self):
        process = Mock()
        process.returncode = 0
        process.stderr.read.return_value = b""
        with TemporaryDirectory() as directory, patch("yards_vision.presentation.subprocess.Popen", return_value=process):
            recorder = PresentationRecorder(Path(directory) / "clip.mp4", "ffmpeg", fps=10)
            for value, timestamp in [(10, 7.0), (20, 7.04), (30, 7.2), (40, 7.5)]:
                recorder.add(np.full((2, 2, 3), value, np.uint8), timestamp)
            recorder.close()
            values = [call.args[0][0] for call in process.stdin.write.call_args_list]
            self.assertEqual(values, [10, 20, 30, 30, 30, 40])
            self.assertEqual(recorder.frames, 6)
            process.stdin.close.assert_called_once()
            recorder.close()  # Closing twice must not append another frame.
            self.assertEqual(process.stdin.write.call_count, 6)

    def test_presentation_does_not_start_during_paused_camera_setup(self):
        capture = Mock()
        capture.get.return_value = 30
        capture.read.return_value = (True, scene(("red", .2, .5)))
        with TemporaryDirectory() as directory:
            with (
                patch("yards_vision.app.VISION", Path(directory)),
                patch("yards_vision.app.encoder_executable", return_value="ffmpeg"),
                patch("yards_vision.app.open_source", return_value=(capture, True)),
                patch("yards_vision.app.cv2.namedWindow"),
                patch("yards_vision.app.cv2.setMouseCallback"),
                patch("yards_vision.app.cv2.imshow"),
                patch("yards_vision.app.cv2.waitKey", return_value=ord("q")),
                patch("yards_vision.app.cv2.destroyAllWindows"),
                patch("yards_vision.presentation.subprocess.Popen") as encoder,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(["--record-presentation"]), 0)
            encoder.assert_not_called()
            self.assertFalse(list(Path(directory).glob("runs/*/presentation.mp4")))
        capture.release.assert_called_once()

    def test_snapshot_contains_the_displayed_counts_as_well_as_the_raw_frame(self):
        with TemporaryDirectory() as directory:
            pipeline = Pipeline(bench())
            frame = scene(("red", .2, .5))
            result = pipeline.process(frame, 1.0, 0)
            desktop = Desktop(pipeline.settings, pipeline, Path(directory), Path(directory) / "settings.json", paused=False, visible=False)
            output = desktop.draw(frame, result, 1.0, 30)
            desktop.key(ord("s"), frame, result, 1.0)
            slide = cv2.imread(str(Path(directory) / "slide-1.000.png"))
            np.testing.assert_array_equal(slide, output)
            self.assertEqual(slide.shape[1], frame.shape[1] + 340)
            self.assertTrue((Path(directory) / "frame-1.000.jpg").is_file())

    def test_presentation_exports_a_playable_video_with_the_final_demo_result(self):
        try:
            encoder_executable()
        except RuntimeError:
            self.skipTest("Optional presentation encoder is not installed")
        with TemporaryDirectory() as directory:
            with patch("yards_vision.app.VISION", Path(directory)), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--demo", "--headless", "--record-presentation"]), 0)
            import json
            session = next(Path(directory).glob("runs/*"))
            summary = json.loads((session / "summary.json").read_text())
            self.assertEqual(summary["counts"], dict.fromkeys(COLORS, 1))
            self.assertEqual(summary["status"], "READY")
            self.assertEqual(summary["presentation_frames"], DEMO_FRAMES)
            capture = cv2.VideoCapture(summary["presentation_video"])
            try:
                self.assertEqual(round(capture.get(cv2.CAP_PROP_FPS)), 30)
                count, last = 0, None
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    last, count = frame, count + 1
                self.assertEqual(count, DEMO_FRAMES)
                self.assertEqual(last.shape, (480, 980, 3))
                panel = last[:50, 640:]
                green_text = (panel[:, :, 1].astype(int) - panel[:, :, 0] > 60) & (panel[:, :, 1].astype(int) - panel[:, :, 2] > 60)
                self.assertGreater(np.count_nonzero(green_text), 30)
            finally:
                capture.release()

    def test_upside_down_correction_is_recorded_and_replayed_once(self):
        with TemporaryDirectory() as directory:
            with patch("yards_vision.app.VISION", Path(directory)), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--demo", "--headless", "--rotate-180", "--record-session"]), 0)
                session = next(Path(directory).glob("runs/*"))
                video = session / "camera.avi"
                self.assertTrue(recorded_rotation(video))
                capture = cv2.VideoCapture(str(video))
                try:
                    ok, first = capture.read()
                    self.assertTrue(ok)
                    expected = cv2.rotate(demo_frame(0), cv2.ROTATE_180)
                    self.assertLess(float(np.abs(first.astype(float) - expected.astype(float)).mean()), 5)
                finally:
                    capture.release()
                self.assertEqual(main(["--source", str(video), "--config", str(session / "settings.json"), "--headless"]), 0)
            summaries = []
            import json
            for path in Path(directory).glob("runs/*/summary.json"):
                summaries.append(json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(len(summaries), 2)
            for summary in summaries:
                self.assertEqual(summary["counts"], dict.fromkeys(COLORS, 1))
                self.assertEqual(summary["status"], "READY")
                self.assertEqual(summary["review_reasons"], [])

    def test_repeated_sessions_keep_separate_videos_and_aligned_frame_times(self):
        with TemporaryDirectory() as directory:
            with patch("yards_vision.app.VISION", Path(directory)), redirect_stdout(io.StringIO()):
                for _ in range(2):
                    self.assertEqual(main(["--demo", "--headless", "--record-session"]), 0)
            sessions = list(Path(directory).glob("runs/*"))
            self.assertEqual(len(sessions), 2)
            for session in sessions:
                with (session / "frame_times.csv").open(newline="", encoding="utf-8") as source:
                    frames = list(csv.DictReader(source))
                self.assertEqual(len(frames), DEMO_FRAMES)
                self.assertEqual([int(row["frame_index"]) for row in frames], list(range(DEMO_FRAMES)))
                self.assertTrue(all(row["counting_active"] == "1" for row in frames))
                self.assertAlmostEqual(float(frames[-1]["time_seconds"]), (DEMO_FRAMES - 1) / 30, places=5)
                capture = cv2.VideoCapture(str(session / "camera.avi"))
                try:
                    count = 0
                    while capture.read()[0]:
                        count += 1
                    self.assertEqual(count, DEMO_FRAMES)
                finally:
                    capture.release()
                import json
                summary = json.loads((session / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["recording"], str(session / "camera.avi"))
                self.assertEqual(summary["counts"], dict.fromkeys(COLORS, 1))
                self.assertEqual(summary["status"], "READY")

    def test_existing_recording_is_protected_before_camera_opens(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trial.avi"
            path.write_bytes(b"existing recording")
            with patch("yards_vision.app.open_source") as opener, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--record", str(path)])
            self.assertEqual(error.exception.code, 2)
            opener.assert_not_called()
            self.assertEqual(path.read_bytes(), b"existing recording")


class ConfigurationTests(unittest.TestCase):
    def test_rotation_keeps_the_same_physical_roi_and_pick_direction(self):
        settings = bench()
        settings.roi = [.05, .2, .85, .75]
        settings.transfer_band = [.12, .22]
        rotated = settings.with_rotation(True)
        self.assertEqual(rotated.roi, [.1, .05, .85, .75])
        self.assertFalse(settings.rotate_180)
        self.assertTrue(rotated.rotate_180)
        for point in [(0.3, 0.5), (0.49, 0.5), (0.7, 0.5)]:
            transformed = (1 - point[0], 1 - point[1])
            self.assertEqual(settings.side(point), rotated.side(transformed))
            self.assertEqual(settings.inside_transfer(point), rotated.inside_transfer(transformed))
        self.assertEqual(rotated.with_rotation(True), rotated)
        self.assertEqual(rotated.with_rotation(False), settings)

    def test_frame_rotation_moves_opposite_corners_and_skips_corrected_recordings(self):
        frame = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
        np.testing.assert_array_equal(orient_frame(frame, True), frame[::-1, ::-1])
        np.testing.assert_array_equal(orient_frame(frame, True, True), frame)

    def test_default_and_bench_recipes_are_valid(self):
        self.assertEqual(Settings().validate().recipe, dict.fromkeys(COLORS, 4))
        self.assertEqual(parse_recipe("1,1,1"), dict.fromkeys(COLORS, 1))

    def test_rejects_bad_recipes(self):
        for value in ("0,0,0", "-1,4,4", "4,4", "red,green,blue"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_recipe(value)

    def test_rejects_overlapping_hues(self):
        settings = bench()
        settings.colors["green"].hue = 5
        with self.assertRaises(ValueError):
            settings.validate()

    def test_rejects_roi_without_visible_space_on_both_sides(self):
        settings = bench()
        settings.roi = [.0, .0, .3, 1.0]
        with self.assertRaises(ValueError):
            settings.validate()

    def test_boundary_orientation_can_be_reversed(self):
        settings = bench()
        settings.packing_point = [.1, .5]
        settings.validate()
        self.assertEqual(settings.side((.2, .5)), 1)
        self.assertEqual(settings.side((.8, .5)), -1)

    def test_transfer_band_uses_lane_and_exit_orientation(self):
        settings = bench()
        settings.packing_point = [.1, .5]
        settings.transfer_band = [.12, .22]
        settings.validate()
        self.assertTrue(settings.inside_transfer((.59, .5)))
        self.assertTrue(settings.inside_transfer((.30, .5)))
        self.assertFalse(settings.inside_transfer((.65, .5)))
        self.assertFalse(settings.inside_transfer((.20, .5)))

    def test_rejects_transfer_band_that_cannot_confirm_both_sides(self):
        settings = bench()
        settings.transfer_band = [.01, .2]
        with self.assertRaisesRegex(ValueError, "Transfer band"):
            settings.validate()


if __name__ == "__main__":
    unittest.main()
