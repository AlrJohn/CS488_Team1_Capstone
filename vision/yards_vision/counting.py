"""Batch ledger: observed picks add one; observed returns subtract one."""

from dataclasses import dataclass, field
from .config import COLORS


@dataclass
class BatchCounter:
    recipe: dict
    settle_seconds: float = 0.8
    counts: dict = field(default_factory=lambda: dict.fromkeys(COLORS, 0))
    reviews: set = field(default_factory=set)
    last_change: float = 0.0
    batch: int = 1
    events: list = field(default_factory=list)

    def record(self, timestamp, kind, color="", delta=0, track_id="", message=""):
        event = {"time_seconds": round(timestamp, 3), "batch": self.batch,
                 "event": kind, "color": color, "delta": delta, "track_id": track_id,
                 **{name: self.counts[name] for name in COLORS}, "message": message}
        self.events.append(event)
        return event

    def review(self, message, timestamp):
        if message not in self.reviews:
            self.reviews.add(message)
            self.record(timestamp, "review", message=message)

    def apply(self, track_id, color, delta, timestamp):
        if delta == -1 and self.counts[color] == 0:
            self.review(f"Unmatched {color} return: no counted {color} can is available to subtract", timestamp)
            return
        self.counts[color] += delta
        self.last_change = timestamp
        self.record(timestamp, "pick" if delta == 1 else "return", color, delta, track_id)

    def acknowledge_review(self, timestamp):
        self.record(timestamp, "manual_review_acknowledged", message="Operator confirmed the displayed counts against the current carton")
        self.reviews.clear()
        self.last_change = timestamp

    def reset(self, timestamp, completed=False):
        self.record(timestamp, "carton_completed" if completed else "batch_reset", message="Operator starts a new empty carton")
        self.batch += 1
        self.counts = dict.fromkeys(COLORS, 0)
        self.reviews.clear()
        self.last_change = timestamp

    def status(self, timestamp, pending=False):
        if self.reviews:
            return "REVIEW NEEDED"
        if any(self.counts[name] > self.recipe[name] for name in COLORS):
            return "TOO MANY CANS"
        if self.counts != self.recipe:
            return "IN PROGRESS"
        if pending or timestamp - self.last_change < self.settle_seconds:
            return "WAIT"
        return "READY"
