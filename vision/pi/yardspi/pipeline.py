"""Can-color sampling and shared V4 tracking and counting stages.

CS488 Capstone, Team 1.
"""

import json
from pathlib import Path
from types import SimpleNamespace
import time
from common.geometry import Boxes, restore_view
from common.color_analysis import sample_colors
from common.settings import InteriorSampling, SideSampling
from common.instance_quality import deduplicate
from common.instance_memory import context_area, clipped_edges
from common.pack_ledger import PackLedger
from common.pack_crossing import RoiCounter, left_defect_boundary
from common.observer import RoiObserver


class Pipeline:
    """Combine Pi inference, mask colors, physical tracking and carton counting."""

    def __init__(self, root, backend, *, view=None, runtime=None, colors=None, recipe=None):
        """Load station settings; an HMI recipe overrides only this session's target."""
        self.root = Path(root)
        self.backend = backend
        self.config = json.loads(Path(runtime or self.root / "configs/runtime.json").read_text())
        self.view = json.loads(Path(view or self.root / "configs/view.json").read_text())
        colors = json.loads(Path(colors or self.root / "configs/colors.json").read_text())
        self.settings = SimpleNamespace(
            colors={k: SimpleNamespace(**v) for k, v in colors["colors"].items()},
            side_sampling=SideSampling(**colors.get("side_sampling", {})),
            interior_sampling=InteriorSampling(**colors.get("interior_sampling", {})),
        )
        self.ledger = PackLedger(self.config["expected_recipe"] if recipe is None else recipe)
        self.counter = None
        self.observer = RoiObserver(self.config["tracker"])
        self.roi = None

    def new_box(self, now):
        """Reset tracking and the counter together, returning the closed carton status."""
        closed = self.ledger.new_box(now)
        self.observer = RoiObserver(self.config["tracker"])
        self.counter = None
        return closed

    def process(self, frame, now):
        """Analyze one oriented BGR image and advance the shared carton counter.

        Args:
            frame: Current camera image after the configured rotation.
            now: Observation time in seconds.
        Returns:
            A log row with observations, events and stage times, plus ROI display masks.

        Color sampling uses context masks; returned display masks are cropped to the ROI.
        """
        start = time.perf_counter()
        # The larger crop keeps a fast-moving can visible near the count-area edge.
        self.roi = restore_view(self.view, frame.shape[:2])
        roi_x, roi_y, roi_width, roi_height = self.roi
        context_x, context_y, context_width, context_height = context_area(
            self.roi, frame.shape[:2], self.config["tracking_context"]["padding_fraction"]
        )
        context = frame[
            context_y : context_y + context_height, context_x : context_x + context_width
        ]
        masks, boxes, timing = self.backend.predict(context)
        detected = time.perf_counter()
        # Sample actual mask pixels, then remove duplicate predictions in this frame.
        labels, votes = sample_colors(context, masks, self.settings, interior=True)
        colored = time.perf_counter()
        keep, suppressed = deduplicate(masks, labels, boxes.conf)
        masks = masks[keep]
        context_data = boxes.data[keep].copy()
        data = context_data.copy()
        labels = [labels[i] for i in keep]
        votes = [votes[i] for i in keep]
        # Tracking and the ledger use coordinates relative to the count area.
        data[:, [0, 2]] += context_x - roi_x
        data[:, [1, 3]] += context_y - roi_y
        observations, confirmed = self.observer.update(
            Boxes(data, (roi_height, roi_width)), labels, now
        )
        warnings = []
        for observation, color_evidence, context_box in zip(
            observations, votes, context_data[:, :4]
        ):
            observation["color_analysis"] = color_evidence
            observation["context_edges"] = clipped_edges(
                context_box, (context_height, context_width)
            )
            known = observation["color"] in ("red", "green", "blue") or confirmed.get(
                observation["track_id"], {}
            ).get("color") in ("red", "green", "blue")
            if observation["inside_roi"] and known:
                if observation["context_edges"]:
                    warnings.append(
                        "CAN CLIPPED AT TRACKING EDGE: " + ", ".join(observation["context_edges"])
                    )
                elif observation["roi_edges"]:
                    warnings.append(
                        "ROI edge: "
                        + ", ".join(observation["roi_edges"])
                        + " | following in tracking margin"
                    )
        if self.counter is None:
            self.counter = RoiCounter(
                (roi_height, roi_width),
                self.ledger,
                reject_boundary=left_defect_boundary(self.view["defect_exit_x"]),
            )
        # Advance counts once per observed frame, independently of screen refresh.
        events = self.counter.update(observations, confirmed, self.observer.index, now)
        timing.update(
            color_ms=(colored - detected) * 1000,
            tracking_count_ms=(time.perf_counter() - colored) * 1000,
            pipeline_ms=(time.perf_counter() - start) * 1000,
        )
        return dict(
            index=self.observer.index,
            timestamp_seconds=now,
            roi_xywh=self.roi,
            tracking_context_xywh=[context_x, context_y, context_width, context_height],
            roi_group=self.observer.group,
            observations=observations,
            confirmed=confirmed,
            pack=self.counter.snapshot(now),
            transfer_events=events,
            timing_ms=timing,
            suppressed_duplicates=suppressed,
            frame_shape=list(frame.shape[:2]),
            framing_warning=" | ".join(dict.fromkeys(warnings)),
        ), masks[
            :,
            roi_y - context_y : roi_y - context_y + roi_height,
            roi_x - context_x : roi_x - context_x + roi_width,
        ]
