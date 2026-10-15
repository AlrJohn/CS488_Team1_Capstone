"""Small color-aware tracker with conservative, observed boundary transitions."""

from dataclasses import dataclass, field
import math


@dataclass
class Track:
    id: int
    color: str
    center: tuple
    box: tuple
    last_frame: int
    hits: int = 1
    missed: int = 0
    velocity: tuple = (0.0, 0.0)
    stable_side: int = 0
    candidate_side: int = 0
    side_hits: int = 0
    blocked: bool = False
    updated: bool = True
    saw_lane: bool = False
    began_in_band: bool = False


@dataclass
class TrackerResult:
    tracks: list = field(default_factory=list)
    crossings: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    pending: bool = False


class ColorTracker:
    def __init__(self, settings):
        self.settings = settings
        self.tracks = {}
        self.next_id = 1

    def _observe_side(self, track, result):
        side = self.settings.side(track.center)
        if side == -1:
            track.saw_lane = True
        if side == 0:
            track.candidate_side = 0
            track.side_hits = 0
            return
        if track.candidate_side == side:
            track.side_hits += 1
        else:
            track.candidate_side, track.side_hits = side, 1
        if track.hits < self.settings.min_hits or track.side_hits < self.settings.side_frames:
            return
        if not track.stable_side and side == 1 and (track.saw_lane or track.began_in_band):
            track.blocked = True
            result.warnings.append(f"Unconfirmed origin for {track.color} track {track.id}: movement was too brief to count")
        if track.stable_side and side != track.stable_side and not track.blocked:
            result.crossings.append((track.id, track.color, 1 if side == 1 else -1))
        track.stable_side = side

    def update(self, detections, frame_index):
        result = TrackerResult()
        settings = self.settings
        predictions = {}
        for track in self.tracks.values():
            track.updated = False
            elapsed = frame_index - track.last_frame
            predictions[track.id] = tuple(p + v * min(elapsed, settings.max_crossing_gap + 1) for p, v in zip(track.center, track.velocity))

        rejected = set()
        for index, detection in enumerate(detections):
            x, y, w, h = detection.box
            inside = [t for t in self.tracks.values() if t.color == detection.color and t.hits >= settings.min_hits and x <= t.center[0] <= x + w and y <= t.center[1] <= y + h]
            if len(inside) > 1:
                rejected.add(index)
                for track in inside:
                    track.blocked = True
                result.warnings.append(f"Merged {detection.color} tracks: separate the cans and verify the count")

        costs = []
        for track in self.tracks.values():
            for index, detection in enumerate(detections):
                if index in rejected or detection.color != track.color:
                    continue
                distance = math.dist(predictions[track.id], detection.center)
                if distance <= settings.match_distance:
                    costs.append((distance, track.id, index))

        # Near ties indicate that color/location cannot establish a unique match.
        for track_id in self.tracks:
            options = sorted(c[0] for c in costs if c[1] == track_id)
            if len(options) > 1 and options[1] - options[0] < settings.ambiguity_margin:
                self.tracks[track_id].blocked = True
                result.warnings.append(f"Ambiguous {self.tracks[track_id].color} match: verify the count")
        for index, detection in enumerate(detections):
            options = sorted((c[0], c[1]) for c in costs if c[2] == index)
            if len(options) > 1 and options[1][0] - options[0][0] < settings.ambiguity_margin:
                for _, track_id in options:
                    self.tracks[track_id].blocked = True
                result.warnings.append(f"Ambiguous {detection.color} identity: verify the count")

        matched_tracks, matched_detections = set(), set()
        for _, track_id, index in sorted(costs):
            if track_id in matched_tracks or index in matched_detections:
                continue
            track, detection = self.tracks[track_id], detections[index]
            gap = frame_index - track.last_frame - 1
            new_side = settings.side(detection.center)
            if gap > settings.max_crossing_gap:
                # Re-acquisition is allowed on the same side, but never used to
                # silently infer a crossing that happened behind a hand.
                if new_side == 0 or track.stable_side == 0 or new_side != track.stable_side:
                    track.blocked = True
                    result.warnings.append(f"Unseen movement for {track.color} track {track.id}: verify the count")
                track.candidate_side, track.side_hits = 0, 0
            elapsed = max(frame_index - track.last_frame, 1)
            measured = tuple((n - old) / elapsed for n, old in zip(detection.center, track.center))
            track.velocity = tuple(0.5 * old + 0.5 * new for old, new in zip(track.velocity, measured))
            track.center, track.box = detection.center, detection.box
            track.last_frame, track.missed, track.updated = frame_index, 0, True
            track.hits += 1
            self._observe_side(track, result)
            matched_tracks.add(track_id)
            matched_detections.add(index)
            # An observed departure beyond the transfer area on the confirmed
            # side is expected. Re-entry can establish a new track. We never
            # retire a missing track this way or infer a crossing from it.
            if not settings.inside_transfer(track.center) and track.stable_side and settings.side(track.center) == track.stable_side:
                del self.tracks[track_id]

        for track_id, track in list(self.tracks.items()):
            if track_id in matched_tracks:
                continue
            track.missed = frame_index - track.last_frame
            if track.missed > settings.max_missed:
                if track.hits >= settings.min_hits and track.stable_side != 1:
                    result.warnings.append(f"Lost {track.color} track {track.id} before a confirmed exit: verify the count")
                del self.tracks[track_id]

        for index, detection in enumerate(detections):
            if index in matched_detections or index in rejected:
                continue
            if not settings.inside_transfer(detection.center):
                continue
            track = Track(self.next_id, detection.color, detection.center, detection.box, frame_index)
            track.began_in_band = settings.side(detection.center) == 0
            self.tracks[track.id] = track
            self.next_id += 1
            self._observe_side(track, result)

        result.tracks = list(self.tracks.values())
        result.pending = any(
            (t.hits >= settings.min_hits and (t.missed > 0 and t.stable_side != 1 or settings.side(t.center) == 0 or t.candidate_side != t.stable_side))
            or (t.updated and t.hits < settings.min_hits)
            for t in result.tracks
        )
        return result
