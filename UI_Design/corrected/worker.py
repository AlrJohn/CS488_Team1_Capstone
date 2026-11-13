"""Keep camera/model work off the GUI thread and serialize operator commands.

CS488 Capstone, Team 1.
"""

import queue
import threading
import time

from PySide6.QtCore import QThread, Signal

from vision_runtime import VisionEngine, VISION_ROOT, import_pi_modules


class CameraWorker(QThread):
    """Own one camera and model; publish immutable snapshots to Qt widgets."""

    frame_ready = Signal(object, object, object, object)
    camera_error = Signal(str)
    command_done = Signal(str, object)

    def __init__(
        self,
        settings,
        source=0,
        vision_root=VISION_ROOT,
        backend="hailo",
        model=None,
        parent=None,
        recipe=None,
        vision_options=None,
        engine_factory=VisionEngine,
        camera_opener=None,
    ):
        """Prepare the analysis thread, command queue and bounded preview delivery."""
        super().__init__(parent)
        self.settings = dict(settings)
        self.source = int(source)
        self.root = vision_root
        self.engine_options = dict(
            vision_options or {}, backend=backend, model=model, recipe=recipe
        )
        self._engine_factory = engine_factory
        self._camera_opener = camera_opener
        self._stop = threading.Event()
        self._commands = queue.Queue()
        self._preview_pending = threading.Event()

    def start_box(self):
        """Start the first box or reset the finished box in the worker thread."""
        self._commands.put(("start", None))

    def set_active(self, active):
        """Queue pause/resume without editing the ledger from the UI thread."""
        self._commands.put(("active", bool(active)))

    def freeze_box(self):
        """Freeze before publishing the authoritative counts for Finish Box."""
        self._commands.put(("finish", None))

    def undo(self):
        """Queue the terminal counter's undo operation."""
        self._commands.put(("undo", None))

    def acknowledge_review(self):
        """Queue a manual review acknowledgment."""
        self._commands.put(("verify", None))

    def preview_consumed(self):
        """Allow another frame after the GUI consumes the previous one."""
        self._preview_pending.clear()

    def stop(self):
        """Request cleanup; never destroy a still-running QThread."""
        self._stop.set()
        return not self.isRunning() or self.wait(10000)

    def run(self):
        """Capture and analyze continuously, limiting only GUI updates."""
        cap = engine = None
        active = started_box = False
        began = time.perf_counter()
        last_preview = float("-inf")
        counts = {"Red": 0, "Green": 0, "Blue": 0}
        metadata = {"ready": False}
        try:
            opener = self._camera_opener or import_pi_modules(self.root)[3]
            cap, camera_info = opener(
                self.source,
                int(self.settings["frame_width"]),
                int(self.settings["frame_height"]),
                self.settings.get("camera_format", "MJPG"),
                float(self.settings["camera_fps"]),
            )
            engine = self._engine_factory(self.root, **self.engine_options)
            engine.start(camera_info=camera_info)
            counts, metadata = engine.snapshot()
            while not self._stop.is_set():
                now = time.perf_counter() - began
                while not self._commands.empty():
                    command, value = self._commands.get_nowait()
                    if command == "start":
                        if started_box:
                            engine.new_box(now)
                        started_box = active = True
                    elif command == "active":
                        active = bool(value) and started_box
                        engine.pause(not active)
                    elif command == "finish":
                        active = False
                        engine.pause(True)
                    elif command == "undo":
                        engine.undo(now)
                    elif command == "verify":
                        engine.acknowledge_review(now)
                    if not active:
                        engine.pause(True)
                    counts, metadata = engine.snapshot(now)
                    self.command_done.emit(
                        command, dict(counts=counts, metadata=metadata, active=active)
                    )
                read_start = time.perf_counter()
                ok, frame = cap.read()
                read_end = time.perf_counter()
                if not ok or frame is None:
                    raise RuntimeError("Camera stopped returning images. Check its USB connection.")
                now = read_end - began
                limit = float(self.settings.get("preview_fps", 10))
                render = not self._preview_pending.is_set() and (
                    limit == 0 or read_end - last_preview >= 1 / limit
                )
                events = []
                if active:
                    overlay, events, counts, metadata = engine.process(
                        frame, now, render=render, read_ms=(read_end - read_start) * 1000
                    )
                else:
                    overlay = engine.preview(frame) if render else None
                if render:
                    self._preview_pending.set()
                    self.frame_ready.emit(
                        overlay,
                        events,
                        counts.copy(),
                        dict(metadata, paused=not active, box_started=started_box),
                    )
                    last_preview = read_end
        except Exception as exc:
            if engine:
                engine.fail(exc)
            self.camera_error.emit(str(exc))
        finally:
            try:
                if engine:
                    engine.close()
            except Exception as exc:
                self.camera_error.emit("Could not finish station cleanup: " + str(exc))
            finally:
                if cap is not None:
                    cap.release()
