"""Evaluate existing color detection/tracking on a recording without webcam changes."""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from yards_vision.app import _line_in_roi, orient_frame, recorded_rotation
from yards_vision.config import COLORS, Settings
from yards_vision.detection import BGR
from yards_vision.pipeline import Pipeline
from yards_vision.presentation import PresentationRecorder, encoder_executable


def text(image, message, point, color=(235, 235, 235), size=.57):
    cv2.putText(image, message, point, cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)


def render(frame, result, pipeline, timestamp, label):
    """Show candidate regions and masks; all numerical counts stay marked unverified."""
    settings = pipeline.settings
    height, width = frame.shape[:2]
    view = frame.copy()
    x, y, w, h = settings.roi
    cv2.rectangle(view, (round(x * width), round(y * height)),
                  (round((x + w) * width), round((y + h) * height)), (230, 230, 230), 1)
    _line_in_roi(view, settings)
    for offset in (-settings.hysteresis, settings.hysteresis):
        _line_in_roi(view, settings, offset, (120, 120, 120), 1)
    if settings.transfer_band:
        sign = 1 if settings.distance(settings.packing_point) > 0 else -1
        for offset in (-settings.transfer_band[0] * sign, settings.transfer_band[1] * sign):
            _line_in_roi(view, settings, offset, (220, 180, 50), 1)
    colored = np.zeros_like(frame)
    for color, mask in result["masks"].items():
        colored[mask > 0] = BGR[color]
    for detection in result["detections"]:
        x, y, w, h = detection.box
        p1 = (round(x * width), round(y * height))
        p2 = (round((x + w) * width), round((y + h) * height))
        cv2.rectangle(view, p1, p2, BGR[detection.color], 2)
        text(view, detection.color, (p1[0], max(16, p1[1] - 4)), BGR[detection.color], .45)
    for track in result["tracks"]:
        if track.updated:
            center = (round(track.center[0] * width), round(track.center[1] * height))
            cv2.circle(view, center, 3, BGR[track.color], -1)
            text(view, f"#{track.id}" + (" ?" if track.blocked else ""),
                 (center[0] + 5, center[1]), BGR[track.color], .4)
    # This experiment displays the upper half of the portrait recording, where
    # the pickup action occurs. Detection itself still uses the full-frame ROI.
    crop_height = min(height, round(width * 540 / 620))
    output = np.full((720, 1280, 3), 22, np.uint8)
    output[60:600, 10:630] = cv2.resize(view[:crop_height], (620, 540))
    output[60:600, 650:1270] = cv2.resize(colored[:crop_height], (620, 540))
    text(output, f"{label} | source time {timestamp:.2f}s", (12, 23), size=.65)
    text(output, "Candidate regions and tracks", (12, 48), size=.48)
    text(output, "HSV masks inside the inspection area", (650, 48), size=.48)
    counts = pipeline.counter.counts
    text(output, f"UNVERIFIED net crossings: red {counts['red']} | green {counts['green']} | blue {counts['blue']}"
         f"     {result['status']}", (12, 628), (0, 190, 255), .57)
    text(output, "Regions are not physical can counts. Continuous diagnostic: no carton resets or load verification.",
         (12, 652), size=.48)
    reasons = sorted(pipeline.counter.reviews)
    message = reasons[-1] if reasons else "No automatic review so far; this does not establish correct counts."
    text(output, message[:145], (12, 677), (0, 190, 255), .45)
    text(output, "Existing OpenCV algorithm; separate recording calibration. Screen recording / moving camera.",
         (12, 704), size=.48)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--label", default="Recorded clip experiment")
    parser.add_argument("--snapshots", default="", help="Comma-separated source times in seconds")
    parser.add_argument("--no-video", action="store_true", help="Save logs and requested images without encoding a video")
    args = parser.parse_args(argv)
    if args.start < 0 or args.end is not None and args.end <= args.start:
        parser.error("Use nonnegative start and end greater than start.")
    settings = Settings.load(args.config)
    source_rotation = recorded_rotation(args.source)
    executable = encoder_executable() if not args.no_video else None
    output = args.output or Path(__file__).resolve().parent / "runs" / datetime.now().strftime("clip-%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True, exist_ok=False)
    settings.save(output / "settings.json")
    snapshots = sorted(float(item) for item in args.snapshots.split(",") if item.strip())
    cap = cv2.VideoCapture(str(args.source))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot read {args.source}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        cap.release()
        raise RuntimeError("Source does not report a usable frame rate.")
    pipeline = Pipeline(settings)
    video = PresentationRecorder(output / "analysis.mp4", executable) if executable else None
    started = time.perf_counter()
    frame_index, processed, timestamp = -1, 0, None
    last_source_time = None
    first_time = None
    repeated = 0
    previous_crop = None
    fallback_timestamps = 0
    status_frames = {}
    try:
        with (output / "detections.csv").open("w", newline="", encoding="utf-8") as detection_file, \
             (output / "frames.csv").open("w", newline="", encoding="utf-8") as frame_file:
            detection_writer = csv.DictWriter(detection_file, fieldnames=["frame_index", "time_seconds", "color", "x", "y", "width", "height", "colored_area"])
            detection_writer.writeheader()
            frame_writer = csv.DictWriter(frame_file, fieldnames=["frame_index", "time_seconds", "status", *COLORS, "red_regions", "green_regions", "blue_regions"])
            frame_writer.writeheader()
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_index += 1
                source_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if not np.isfinite(source_time) or last_source_time is not None and source_time <= last_source_time:
                    source_time = frame_index / fps
                    fallback_timestamps += 1
                if last_source_time is not None and source_time < last_source_time:
                    raise RuntimeError("Source timestamps went backwards.")
                last_source_time = source_time
                if source_time < args.start:
                    continue
                if args.end is not None and source_time >= args.end:
                    break
                timestamp = source_time
                if first_time is None:
                    first_time = timestamp
                frame = orient_frame(frame, settings.rotate_180, source_rotation)
                gray = cv2.cvtColor(frame[:min(600, frame.shape[0])], cv2.COLOR_BGR2GRAY)
                if previous_crop is not None and float(cv2.absdiff(gray, previous_crop).mean()) < .1:
                    repeated += 1
                previous_crop = gray
                result = pipeline.process(frame, timestamp, frame_index)
                view = render(frame, result, pipeline, timestamp, args.label) if video or snapshots and timestamp >= snapshots[0] else None
                if video:
                    video.add(view, timestamp)
                while snapshots and timestamp >= snapshots[0]:
                    target = snapshots.pop(0)
                    cv2.imwrite(str(output / f"snapshot-{target:05.2f}.png"), view)
                for detection in result["detections"]:
                    x, y, width, height = detection.box
                    detection_writer.writerow({"frame_index": frame_index, "time_seconds": f"{timestamp:.6f}",
                        "color": detection.color, "x": x, "y": y, "width": width, "height": height,
                        "colored_area": detection.area})
                frame_writer.writerow({"frame_index": frame_index, "time_seconds": f"{timestamp:.6f}",
                    "status": result["status"], **pipeline.counter.counts,
                    **{color + "_regions": sum(d.color == color for d in result["detections"]) for color in COLORS}})
                status_frames[result["status"]] = status_frames.get(result["status"], 0) + 1
                processed += 1
        if video:
            video.close()
        if not processed:
            raise RuntimeError("The selected interval contains no frames.")
        with (output / "events.csv").open("w", newline="", encoding="utf-8") as target:
            fields = ["time_seconds", "batch", "event", "color", "delta", "track_id", *COLORS, "message"]
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            writer.writerows(pipeline.counter.events)
        root = Path(__file__).resolve().parent
        hashes = {name: hashlib.sha256((root / "yards_vision" / name).read_bytes()).hexdigest()
                  for name in ("detection.py", "tracking.py", "counting.py", "pipeline.py")}
        summary = {"source": str(args.source.resolve()), "source_fps_reported": fps,
            "first_source_time": first_time, "last_source_time": timestamp, "frames_processed": processed,
            "timestamp_fallback_frames": fallback_timestamps, "near_repeated_action_frames": repeated,
            "near_repeat_definition": "Mean absolute grayscale difference below 0.1 in the upper 600 image rows; includes static/paused scenes.",
            "settings": asdict(settings), "algorithm_sha256": hashes,
            "counts_unverified": pipeline.counter.counts, "status_frames": status_frames,
            "review_reasons": sorted(pipeline.counter.reviews),
            "logged_picks": {color: sum(e["event"] == "pick" and e["color"] == color for e in pipeline.counter.events) for color in COLORS},
            "logged_returns": {color: sum(e["event"] == "return" and e["color"] == color for e in pipeline.counter.events) for color in COLORS},
            "analysis_video": str((output / "analysis.mp4").resolve()) if video else None,
            "output_frames": video.frames if video else 0,
            "output_fps": video.fps if video else None, "processing_wall_seconds": round(time.perf_counter() - started, 3),
            "limitations": ["Calibration and visual inspection use this clip; no independent validation set.",
                "Camera moves and the input is a screen recording; no production timing conclusion.",
                "No carton reset or manual ground-truth event matching; counts are diagnostic only."]}
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(output.resolve()), "frames": processed,
            "counts_unverified": pipeline.counter.counts, "review_count": len(pipeline.counter.reviews)}, indent=2))
    finally:
        cap.release()
        if video:
            video.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
