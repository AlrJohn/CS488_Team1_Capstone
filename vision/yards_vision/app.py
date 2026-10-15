"""Desktop test bench for visible can transfers and staged color counting."""

import argparse
import copy
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from .config import COLORS, Settings, parse_recipe
from .demo import DEMO_FRAMES, demo_frame
from .detection import BGR, color_mask, detect
from .pipeline import Pipeline

VISION = Path(__file__).resolve().parents[1]
WINDOW = "Yards - Can Inspection Test Bench"
CALIBRATION = "Color calibration"
STATUS_COLORS = {"READY": (70, 210, 70), "REVIEW NEEDED": (0, 190, 255),
                 "TOO MANY CANS": (50, 50, 240), "WAIT": (0, 190, 255),
                 "IN PROGRESS": (220, 220, 220), "PAUSED": (0, 190, 255)}


def has_image_signal(frame):
    """Reject empty/constant backend frames; this does not assess lighting quality."""
    return frame is not None and frame.size > 0 and int(np.ptp(frame)) > 3


def orientation_path(path):
    path = Path(path)
    return path.with_suffix(path.suffix + ".orientation.json")


def recorded_rotation(path):
    metadata = orientation_path(path)
    if not metadata.exists():
        return False  # Older recordings contain the original camera view.
    data = json.loads(metadata.read_text(encoding="utf-8"))
    if data.get("version") != 1 or type(data.get("rotate_180")) is not bool:
        raise ValueError(f"Invalid recording orientation in {metadata}")
    return data["rotate_180"]


def orient_frame(frame, target_rotation, source_rotation=False):
    # A recorded file may already contain the correction. Apply only the
    # difference so replay uses the same coordinates as the saved calibration.
    return cv2.rotate(frame, cv2.ROTATE_180) if target_rotation != source_rotation else frame


def open_source(source, backend, width, height):
    camera = source.isdecimal()
    value = int(source) if camera else source
    apis = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}
    if not camera:
        backends = [cv2.CAP_ANY]
    elif backend != "auto":
        backends = [apis[backend]]
    elif sys.platform == "win32":
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY]
    blank_camera = False
    for api in backends:
        capture = cv2.VideoCapture(value, api)
        if not capture.isOpened():
            capture.release()
            continue
        if camera:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Some backends report success but deliver a constant gray image.
            # Allow startup frames, then reject that source instead of showing
            # an apparently working inspection window with no camera evidence.
            visible = False
            for _ in range(30):
                ok, frame = capture.read()
                if ok and has_image_signal(frame):
                    visible = True
                    break
            if not visible:
                blank_camera = True
                capture.release()
                continue
        return capture, camera
    if blank_camera:
        raise RuntimeError(f"Source {source!r} opened but delivered no usable image. Check the lens, lighting, and camera backend; try --backend dshow from the VS Code terminal.")
    raise RuntimeError(f"Cannot open source {source!r}. Close other camera apps, check Windows camera permissions, or try --source 1 / --backend msmf.")


def list_cameras(backend, limit):
    found = []
    for index in range(limit):
        try:
            capture, _ = open_source(str(index), backend, 640, 480)
            ok, frame = capture.read()
            if ok:
                found.append({"index": index, "width": frame.shape[1], "height": frame.shape[0], "backend": capture.getBackendName()})
            capture.release()
        except RuntimeError:
            pass
    print(json.dumps({"cameras": found}, indent=2))
    return 0 if found else 1


def _text(image, text, xy, color=(225, 225, 225), size=0.52):
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)


def _line_in_roi(image, settings, offset=0.0, color=(255, 255, 255), thickness=2):
    height, width = image.shape[:2]
    a, b = np.array(settings.boundary_start), np.array(settings.boundary_end)
    direction = b - a
    normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
    a, b = a + offset * normal, b + offset * normal
    p1, p2 = a - 10 * direction, b + 10 * direction
    p1, p2 = tuple(np.round(p1 * [width, height]).astype(int).tolist()), tuple(np.round(p2 * [width, height]).astype(int).tolist())
    x, y, w, h = settings.roi
    valid, p1, p2 = cv2.clipLine((round(x * width), round(y * height), max(1, round(w * width)), max(1, round(h * height))), p1, p2)
    if valid:
        cv2.line(image, p1, p2, color, thickness, cv2.LINE_AA)


class Desktop:
    def __init__(self, settings, pipeline, run_dir, save_config, paused, recording=None):
        self.settings, self.pipeline = settings, pipeline
        self.run_dir, self.save_config = run_dir, save_config
        self.paused = paused
        self.recording = recording
        self.calibrating = False
        self.selected = "red"
        self.show_masks = False
        self.boundary_points = None
        self.frame = None
        self.message = "Set ROI (O), boundary (B), and colors (C). Press P to start."
        if settings.transfer_band is not None:
            self.message = "Transfer band loaded. Keep labels visible between the cyan lines. Press P to start."
        self.confirm_action = None
        self.confirm_time = 0.0
        self.timestamp = 0.0
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WINDOW, self.mouse)

    def _zero_batch(self):
        if any(self.pipeline.counter.counts.values()) or self.pipeline.counter.reviews:
            self.message = "Start an empty batch with N before changing calibration or geometry."
            return False
        return True

    def _replace_settings(self, candidate):
        try:
            candidate.validate()
            candidate.save(self.save_config)
            candidate.save(self.run_dir / "settings.json")
        except (ValueError, OSError) as exc:
            self.message = str(exc)
            return False
        old_events = self.pipeline.counter.events
        old_batch = self.pipeline.counter.batch
        self.settings = candidate
        self.pipeline = Pipeline(candidate, self.pipeline.mode)
        self.pipeline.counter.events = old_events
        self.pipeline.counter.batch = old_batch
        self.pipeline.counter.record(self.timestamp, "settings_changed", message="Calibration/geometry updated while batch empty")
        self.paused = True
        self.message = "Settings saved. Start with cans in the lane; press P when ready."
        return True

    def mouse(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN or self.frame is None:
            return
        height, width = self.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return
        point = [x / width, y / height]
        if self.boundary_points is not None:
            self.boundary_points.append(point)
            if len(self.boundary_points) == 3:
                candidate = copy.deepcopy(self.settings)
                candidate.boundary_start, candidate.boundary_end, candidate.packing_point = self.boundary_points
                self.boundary_points = None
                self._replace_settings(candidate)
            return
        if self.calibrating:
            patch = self.frame[max(0, y - 4):y + 5, max(0, x - 4):x + 5]
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            pixels = hsv.reshape(-1, 3)
            pixels = pixels[pixels[:, 1] >= 45]
            if len(pixels) < 8:
                self.message = "Click the colored label, away from silver tops, white print, or glare."
                return
            angle = pixels[:, 0].astype(float) * (2 * math.pi / 180)
            hue = round(math.atan2(np.sin(angle).mean(), np.cos(angle).mean()) * 180 / (2 * math.pi)) % 180
            cv2.setTrackbarPos("Hue", CALIBRATION, hue)
            cv2.setTrackbarPos("S min", CALIBRATION, max(40, int(np.percentile(pixels[:, 1], 20) * 0.65)))
            cv2.setTrackbarPos("V min", CALIBRATION, max(25, int(np.percentile(pixels[:, 2], 20) * 0.55)))
            self.message = f"Sampled {self.selected}. Check the mask and sample several parts of the label."

    def _load_sliders(self):
        color = self.working.colors[self.selected]
        for name, value in [("Hue", color.hue), ("Hue width", color.tolerance), ("S min", color.saturation_min), ("V min", color.value_min)]:
            cv2.setTrackbarPos(name, CALIBRATION, value)

    def _read_sliders(self):
        color = self.working.colors[self.selected]
        color.hue = cv2.getTrackbarPos("Hue", CALIBRATION)
        color.tolerance = max(1, cv2.getTrackbarPos("Hue width", CALIBRATION))
        color.saturation_min = cv2.getTrackbarPos("S min", CALIBRATION)
        color.value_min = cv2.getTrackbarPos("V min", CALIBRATION)

    def toggle_calibration(self):
        if self.calibrating:
            self._read_sliders()
            if not self._replace_settings(self.working):
                return
            self.calibrating = False
            cv2.destroyWindow(CALIBRATION)
            return
        if not self._zero_batch():
            return
        self.working = copy.deepcopy(self.settings)
        self.paused = True
        self.calibrating = True
        cv2.namedWindow(CALIBRATION, cv2.WINDOW_NORMAL)
        for name, maximum in [("Hue", 179), ("Hue width", 44), ("S min", 255), ("V min", 255)]:
            cv2.createTrackbar(name, CALIBRATION, 0, maximum, lambda value: None)
        self._load_sliders()
        self.message = "1 red / 2 green / 3 blue. Click a label to sample. A measures one can. C saves."

    def draw(self, frame, result, timestamp, fps):
        self.frame = frame
        self.timestamp = timestamp
        settings = self.working if self.calibrating else self.settings
        view = frame.copy()
        height, width = frame.shape[:2]
        if self.calibrating:
            self._read_sliders()
            mask = color_mask(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), settings.colors[self.selected])
            cv2.imshow(CALIBRATION, cv2.bitwise_and(frame, frame, mask=mask))
        x, y, w, h = settings.roi
        cv2.rectangle(view, (round(x * width), round(y * height)), (min(width - 1, round((x + w) * width)), min(height - 1, round((y + h) * height))), (220, 220, 220), 1)
        if self.pipeline.mode == "picks":
            _line_in_roi(view, settings)
            for offset in (-settings.hysteresis, settings.hysteresis):
                _line_in_roi(view, settings, offset, (120, 120, 120), 1)
            if settings.transfer_band is not None:
                sign = 1 if settings.distance(settings.packing_point) > 0 else -1
                for offset in (-settings.transfer_band[0] * sign, settings.transfer_band[1] * sign):
                    _line_in_roi(view, settings, offset, (220, 180, 50), 1)
            px, py = settings.packing_point
            _text(view, "EXIT / PACKING SIDE", (max(5, min(width - 200, round(px * width) - 80)), max(20, round(py * height))), (255, 255, 255))
        for detection in result["detections"]:
            bx, by, bw, bh = detection.box
            p1, p2 = (round(bx * width), round(by * height)), (round((bx + bw) * width), round((by + bh) * height))
            cv2.rectangle(view, p1, p2, BGR[detection.color], 2)
            _text(view, detection.color, (p1[0], max(15, p1[1] - 6)), BGR[detection.color])
        for track in result["tracks"]:
            if track.updated:
                cx, cy = round(track.center[0] * width), round(track.center[1] * height)
                cv2.circle(view, (cx, cy), 4, BGR[track.color], -1)
                _text(view, f"#{track.id}" + (" ?" if track.blocked else ""), (cx + 7, cy), BGR[track.color], 0.45)
        if self.boundary_points is not None:
            for point in self.boundary_points:
                cv2.circle(view, (round(point[0] * width), round(point[1] * height)), 6, (0, 255, 255), -1)
            prompt = ["Click boundary start", "Click boundary end", "Click the visible EXIT side"][len(self.boundary_points)]
            cv2.rectangle(view, (0, 0), (width, 35), (25, 25, 25), -1)
            _text(view, prompt, (10, 24), (0, 255, 255))

        panel = np.full((max(height, 480), 340, 3), 24, np.uint8)
        status = "PAUSED" if self.paused or self.boundary_points is not None else result["status"]
        _text(panel, status, (14, 32), STATUS_COLORS[status], 0.7)
        _text(panel, f"Batch {self.pipeline.counter.batch} | {self.pipeline.mode} | {fps:.0f} fps", (14, 61))
        if self.recording:
            _text(panel, "Recording video + frame times", (14, 81), (180, 220, 180), 0.43)
        for index, name in enumerate(COLORS):
            _text(panel, f"{name.upper():5}   {self.pipeline.counter.counts[name]} / {settings.recipe[name]}", (14, 105 + index * 32), BGR[name], 0.7)
        lines = ["P pause/start   C calibrate", "O select ROI   B set boundary", "M masks        S save snapshot", "SPACE finish ready carton", "N reset batch (confirm twice)", "V verify counts (confirm twice)", "Q quit / ESC cancel boundary"]
        for index, text in enumerate(lines):
            _text(panel, text, (14, 215 + index * 23), size=0.47)
        messages = list(self.pipeline.counter.reviews)[-1:] or [self.message]
        message = self.message if self.confirm_action or self.calibrating else messages[0]
        words, wrapped, line = message.split(), [], ""
        for word in words:
            if len(line) + len(word) > 40:
                wrapped.append(line)
                line = ""
            line += (" " if line else "") + word
        wrapped.append(line)
        for index, text in enumerate(wrapped[:4]):
            _text(panel, text, (14, 400 + index * 20), (0, 200, 255), 0.43)
        output = np.full((panel.shape[0], width + panel.shape[1], 3), 24, np.uint8)
        output[:height, :width] = view
        output[:, width:] = panel
        cv2.imshow(WINDOW, output)
        if self.show_masks:
            colored = np.zeros_like(frame)
            for name, mask in result["masks"].items():
                colored[mask > 0] = BGR[name]
            cv2.imshow("Color masks", colored)
        return output

    def _confirm(self, action, timestamp):
        if self.confirm_action == action and timestamp - self.confirm_time <= 3:
            self.confirm_action = None
            return True
        self.confirm_action, self.confirm_time = action, timestamp
        self.message = "Press N again to discard/reset this batch." if action == "reset" else "Manually check ALL displayed counts, then press V again. If wrong, reset and recount."
        return False

    def key(self, key, frame, result, timestamp):
        if key == 27 and self.boundary_points is not None:
            self.boundary_points = None
            self.message = "Boundary change canceled."
            return True
        if key in (ord("q"), 27):
            return False
        if key == ord("c"):
            self.toggle_calibration()
        elif self.calibrating and key in (ord("1"), ord("2"), ord("3")):
            self._read_sliders()
            self.selected = COLORS[key - ord("1")]
            self._load_sliders()
        elif self.calibrating and key == ord("a"):
            box = cv2.selectROI("Select ONE can's full label; ENTER confirms", frame, False, False)
            cv2.destroyWindow("Select ONE can's full label; ENTER confirms")
            x, y, w, h = box
            if w and h:
                self._read_sliders()
                mask = color_mask(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), self.working.colors[self.selected])
                fraction = np.count_nonzero(mask[y:y + h, x:x + w]) / (frame.shape[0] * frame.shape[1])
                if fraction > 0:
                    self.working.min_area = max(0.00001, fraction * 0.35)
                    self.working.max_area = min(0.95, fraction * 1.65)
                    self.message = f"Single-can colored area {fraction:.4f}; min/max area updated."
        elif not self.calibrating and key == ord("o") and self._zero_batch():
            self.paused = True
            x, y, w, h = cv2.selectROI("Select lane AND a visible exit area; ENTER confirms", frame, False, False)
            cv2.destroyWindow("Select lane AND a visible exit area; ENTER confirms")
            if w and h:
                height, width = frame.shape[:2]
                candidate = copy.deepcopy(self.settings)
                candidate.roi = [x / width, y / height, w / width, h / height]
                rx, ry, rw, rh = candidate.roi
                candidate.boundary_start, candidate.boundary_end = [rx + rw / 2, ry], [rx + rw / 2, ry + rh]
                candidate.packing_point = [rx + rw * 0.85, ry + rh / 2]
                self._replace_settings(candidate)
        elif not self.calibrating and key == ord("b") and self._zero_batch():
            self.paused = True
            self.boundary_points = []
            self.message = "Click 2 points for the boundary, then a point on the visible exit side."
        elif not self.calibrating and self.boundary_points is None and key == ord("p"):
            if self.paused and any(self.pipeline.counter.counts.values()):
                self.pipeline.counter.review("Counting was paused during an active batch: verify nothing moved unobserved", timestamp)
            self.paused = not self.paused
            self.pipeline.counter.record(timestamp, "paused" if self.paused else "resumed")
        elif key == ord("m"):
            self.show_masks = not self.show_masks
            if not self.show_masks:
                try:
                    cv2.destroyWindow("Color masks")
                except cv2.error:
                    pass
        elif key == ord("s"):
            path = self.run_dir / f"frame-{timestamp:.3f}.jpg"
            if not cv2.imwrite(str(path), frame):
                raise OSError(f"Could not save {path}")
            self.message = f"Saved {path.name}"
        elif not self.calibrating and key == ord("n") and self._confirm("reset", timestamp):
            self.pipeline.reset(timestamp)
            self.paused = True
            self.message = "New empty batch. Put cans back on the lane side, then press P."
        elif not self.calibrating and key == ord("v") and self.pipeline.counter.reviews and self._confirm("review", timestamp):
            self.pipeline.acknowledge_review(timestamp)
            self.message = "Manual count check acknowledged and logged."
        elif key == ord(" ") and not self.paused:
            occupied_exit = any(t.updated and self.settings.side(t.center) == 1 for t in result["tracks"])
            if result["status"] != "READY":
                self.message = "The current carton is not READY."
            elif occupied_exit and self.pipeline.mode == "picks":
                self.message = "Clear the transfer area before confirming the packed carton."
            else:
                self.pipeline.reset(timestamp, completed=True)
                self.message = "Carton completed; counting the next carton."
        return True


def parser():
    cli = argparse.ArgumentParser(description="Yards color inspection prototype: visible picks/returns or staged counts.")
    cli.add_argument("--source", default="0", help="USB camera index, or a recorded video path")
    cli.add_argument("--backend", choices=("auto", "dshow", "msmf", "any"), default="auto")
    cli.add_argument("--config", type=Path, help="Saved JSON settings (default: configs/local.json if present)")
    cli.add_argument("--save-config", type=Path, default=VISION / "configs/local.json")
    cli.add_argument("--recipe", help="RED,GREEN,BLUE; production default 4,4,4; bench example 1,1,1")
    cli.add_argument("--mode", choices=("picks", "staged"), default="picks")
    cli.add_argument("--rotate-180", action=argparse.BooleanOptionalAction, default=None, help="Correct an upside-down view; also remaps saved geometry for this run")
    cli.add_argument("--demo", action="store_true", help="Use artificial can motion, with a 1,1,1 recipe unless overridden")
    cli.add_argument("--headless", action="store_true", help="Process a source without desktop windows")
    cli.add_argument("--max-frames", type=int, default=0, help="Stop after this many frames; 0 runs until quit/end")
    cli.add_argument("--width", type=int, default=1280)
    cli.add_argument("--height", type=int, default=720)
    cli.add_argument("--display-width", type=int, default=960)
    cli.add_argument("--events", type=Path, help="Custom event CSV output path")
    recording = cli.add_mutually_exclusive_group()
    recording.add_argument("--record", type=Path, help="Save unannotated frames in the displayed orientation to a new MJPG .avi path")
    recording.add_argument("--record-session", action="store_true", help="Save camera.avi inside this run's unique session folder")
    cli.add_argument("--list-cameras", action="store_true")
    cli.add_argument("--camera-limit", type=int, default=4)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    if args.max_frames < 0 or min(args.width, args.height, args.display_width, args.camera_limit) < 1:
        parser().error("Dimensions and camera-limit must be positive; max-frames must be nonnegative.")
    if args.record and args.record.suffix.lower() != ".avi":
        parser().error("Use an .avi path for --record (MJPG codec).")
    if args.record and (args.record.exists() or orientation_path(args.record).exists()):
        parser().error("Recording already exists. Use --record-session or choose a new filename.")
    if args.list_cameras:
        return list_cameras(args.backend, args.camera_limit)
    capture, writer, desktop, log, csv_writer = None, None, None, None, None
    frame_log, frame_csv = None, None
    pipeline = None
    cursor = 0
    try:
        config_path = args.config or (args.save_config if args.save_config.exists() and not args.demo else None)
        settings = Settings.load(config_path)
        if args.rotate_180 is not None:
            settings = settings.with_rotation(args.rotate_180)
        if args.recipe:
            settings.recipe = parse_recipe(args.recipe)
        elif args.demo:
            settings.recipe = dict.fromkeys(COLORS, 1)
        elif args.config is None:
            # Automatically loaded calibration should not silently replace the
            # production recipe with the recipe used for a three-can bench test.
            settings.recipe = dict.fromkeys(COLORS, 4)
        settings.validate()
        pipeline = Pipeline(settings, args.mode)
        run_dir = VISION / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        run_dir.mkdir(parents=True)
        record_path = args.record or (run_dir / "camera.avi" if args.record_session else None)
        settings.save(run_dir / "settings.json")
        events_path = args.events or run_dir / "events.csv"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        log = events_path.open("w", newline="", encoding="utf-8")
        fields = ["frame_index", "time_seconds", "batch", "event", "color", "delta", "track_id", *COLORS, "message"]
        csv_writer = csv.DictWriter(log, fieldnames=fields)
        csv_writer.writeheader()
        if record_path:
            frame_log = (run_dir / "frame_times.csv").open("w", newline="", encoding="utf-8")
            frame_csv = csv.DictWriter(frame_log, fieldnames=["frame_index", "time_seconds", "batch", "counting_active", "status"])
            frame_csv.writeheader()
        cursor = 0
        camera = False
        source_rotation = False
        fps = 30.0
        if not args.demo:
            if not args.source.isdecimal():
                source_rotation = recorded_rotation(args.source)
            capture, camera = open_source(args.source, args.backend, args.width, args.height)
            measured_fps = capture.get(cv2.CAP_PROP_FPS)
            if math.isfinite(measured_fps) and 1 <= measured_fps <= 240:
                fps = measured_fps
        if not args.headless:
            desktop = Desktop(settings, pipeline, run_dir, args.save_config, paused=camera, recording=record_path)
        print(f"Mode: {args.mode}; recipe: {settings.recipe}; event log: {events_path}", flush=True)
        if record_path:
            print(f"Recording: {record_path}", flush=True)
        if camera and desktop:
            print("Counting starts PAUSED. Set O/B/C, then press P. The box can remain outside the image.", flush=True)
        start = time.monotonic()
        last_tick, display_fps = start, fps
        frame_index, result, timestamp = 0, None, 0.0
        while not args.max_frames or frame_index < args.max_frames:
            if args.demo:
                if frame_index >= DEMO_FRAMES:
                    break
                frame = demo_frame(frame_index)
            else:
                ok, frame = capture.read()
                if not ok:
                    if camera:
                        pipeline.counter.review("Camera frame read failed; counting stopped", timestamp)
                        raise RuntimeError("Camera stopped delivering frames. No approval is retained.")
                    break
            if frame.shape[1] > args.display_width:
                scale = args.display_width / frame.shape[1]
                frame = cv2.resize(frame, (args.display_width, round(frame.shape[0] * scale)))
            timestamp = time.monotonic() - start if camera else frame_index / fps
            if camera and not has_image_signal(frame):
                pipeline.counter.review("Camera returned a blank image; counting stopped", timestamp)
                raise RuntimeError("Camera returned a blank image. Check the camera and restart; no approval is retained.")
            if desktop:
                pipeline = desktop.pipeline
            frame = orient_frame(frame, pipeline.settings.rotate_180, source_rotation)
            now = time.monotonic()
            display_fps = 0.9 * display_fps + 0.1 / max(now - last_tick, 0.001)
            last_tick = now
            if record_path:
                if writer is None:
                    record_path.parent.mkdir(parents=True, exist_ok=True)
                    writer = cv2.VideoWriter(str(record_path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (frame.shape[1], frame.shape[0]))
                    if not writer.isOpened():
                        raise RuntimeError(f"Cannot create recording {record_path}")
                    with orientation_path(record_path).open("x", encoding="utf-8") as metadata:
                        json.dump({"version": 1, "rotate_180": pipeline.settings.rotate_180}, metadata, indent=2)
                        metadata.write("\n")
                writer.write(frame)
            if desktop:
                pipeline = desktop.pipeline
            active = not desktop or not desktop.paused and not desktop.calibrating and desktop.boundary_points is None
            if active:
                result = pipeline.process(frame, timestamp, frame_index)
            else:
                detections, masks, _ = detect(frame, desktop.working if desktop.calibrating else desktop.settings, pipeline.mode)
                result = {"detections": detections, "masks": masks, "tracks": [], "pending": True, "status": "PAUSED"}
            if frame_csv:
                frame_csv.writerow({"frame_index": frame_index, "time_seconds": f"{timestamp:.6f}", "batch": pipeline.counter.batch, "counting_active": int(active), "status": result["status"]})
                frame_log.flush()
            running = True
            if desktop:
                desktop.draw(frame, result, timestamp, display_fps)
                delay = 1 if camera else max(1, round(1000 / fps))
                running = desktop.key(cv2.waitKey(delay) & 0xFF, frame, result, timestamp)
                pipeline = desktop.pipeline
            for event in pipeline.counter.events[cursor:]:
                csv_writer.writerow({"frame_index": frame_index, **event})
            cursor = len(pipeline.counter.events)
            log.flush()
            frame_index += 1
            if not running:
                break
        if frame_index == 0:
            raise RuntimeError("No frames were read from the source.")
        summary = {"frames": frame_index, "mode": args.mode, "counts": pipeline.counter.counts,
                   "recipe": pipeline.counter.recipe, "status": "PAUSED" if desktop and desktop.paused else pipeline.counter.status(timestamp, result["pending"]),
                   "review_reasons": sorted(pipeline.counter.reviews), "events_csv": str(events_path),
                   "recording": str(record_path) if record_path else None,
                   "frame_times_csv": str(run_dir / "frame_times.csv") if record_path else None}
        elapsed = time.monotonic() - start
        summary.update(elapsed_seconds=round(elapsed, 3), processed_fps=round(frame_index / max(elapsed, .001), 2))
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError, cv2.error) as exc:
        if pipeline and log and csv_writer:
            for event in pipeline.counter.events[cursor:]:
                csv_writer.writerow({"frame_index": frame_index, **event})
            log.flush()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if capture is not None:
            capture.release()
        if writer is not None:
            writer.release()
        if log is not None:
            log.close()
        if frame_log is not None:
            frame_log.close()
        if desktop:
            cv2.destroyAllWindows()
