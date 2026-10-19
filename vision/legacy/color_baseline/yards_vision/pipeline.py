"""Frame processing is independent of the webcam and desktop windows."""

from collections import Counter
import cv2
import numpy as np

from .config import COLORS
from .counting import BatchCounter
from .detection import detect
from .tracking import ColorTracker


class Pipeline:
    def __init__(self, settings, mode="picks"):
        self.settings = settings
        self.mode = mode
        self.counter = BatchCounter(settings.recipe.copy(), settings.settle_seconds)
        self.tracker = ColorTracker(settings)
        self.previous_gray = None

    def process(self, frame, timestamp, frame_index):
        detections, masks, warnings = detect(frame, self.settings, self.mode)
        for message in warnings:
            self.counter.review(message, timestamp)
        tracks, pending = [], False
        if self.mode == "picks":
            result = self.tracker.update(detections, frame_index)
            tracks, pending = result.tracks, result.pending
            for message in result.warnings:
                self.counter.review(message, timestamp)
            for track_id, color, delta in result.crossings:
                self.counter.apply(track_id, color, delta, timestamp)
        else:
            visible = Counter(d.color for d in detections)
            counts = {name: visible[name] for name in COLORS}
            if counts != self.counter.counts:
                self.counter.counts = counts
                self.counter.last_change = timestamp
                self.counter.record(timestamp, "staged_counts")
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            x, y, w, h = self.settings.roi
            fh, fw = gray.shape
            crop = gray[round(y * fh):round((y + h) * fh), round(x * fw):round((x + w) * fw)]
            if self.previous_gray is None or self.previous_gray.shape != crop.shape:
                pending = True
                self.counter.last_change = timestamp
            else:
                pending = np.count_nonzero(cv2.absdiff(crop, self.previous_gray) > 20) / crop.size > 0.01
                if pending:
                    self.counter.last_change = timestamp
            self.previous_gray = crop.copy()
        return {"detections": detections, "masks": masks, "tracks": tracks,
                "pending": pending, "status": self.counter.status(timestamp, pending)}

    def reset(self, timestamp, completed=False):
        self.counter.reset(timestamp, completed)
        self.tracker = ColorTracker(self.settings)
        self.previous_gray = None

    def acknowledge_review(self, timestamp):
        self.counter.acknowledge_review(timestamp)
        # A new baseline prevents blocked/uncertain old identities being reused.
        self.tracker = ColorTracker(self.settings)
        self.previous_gray = None
