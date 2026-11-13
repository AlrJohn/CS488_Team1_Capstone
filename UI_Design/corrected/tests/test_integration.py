"""Test UI/shared-counter integration without opening a camera, Hailo or GPIO.

CS488 Capstone, Team 1.
"""

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI))
from vision_runtime import (
    VISION_ROOT,
    VisionEngine,
    VisionSetupError,
    configuration_paths,
    import_pi_modules,
    inspection_status,
)
from recipe_store import load_recipes, save_recipes
from history_store import save_box
from worker import CameraWorker
from main import HMI, parse_arguments

Hailo, Onnx, Pipeline, open_camera, StackLights, status_color = import_pi_modules(VISION_ROOT)
from common.geometry import Boxes


class SyntheticBackend:
    """Return one separate can mask; inference itself is not part of this test."""

    instances = []

    def __init__(self, *args):
        """Initialize isolated fake state without opening physical hardware."""
        self.closed = False
        self.seen = None
        self.instances.append(self)

    def predict(self, frame):
        """Return synthetic detections instead of invoking a model."""
        self.seen = frame.copy()
        height, width = frame.shape[:2]
        mask = np.zeros((1, height, width), np.uint8)
        mask[0, height // 4 : 3 * height // 4, width // 2 : 3 * width // 4] = 1
        return (
            mask,
            Boxes(
                [[width // 2, height // 4, 3 * width // 4, 3 * height // 4, 0.95, 0]],
                (height, width),
            ),
            {"inference_ms": 0.0},
        )

    def close(self):
        """Mark this fake resource closed for cleanup assertions."""
        self.closed = True


class FakeLights:
    """Record shared status decisions without claiming any GPIO lines."""

    instances = []

    def __init__(self, **options):
        """Initialize isolated fake state without opening physical hardware."""
        self.options = options
        self.state = "off"
        self.closed = False
        self.instances.append(self)

    def __enter__(self):
        """Return the fake resource for a context-managed test."""
        return self

    def __exit__(self, *args):
        """Release the fake resource and retain cleanup evidence."""
        self.closed = True
        self.state = "off"

    def update(self, pack=None):
        """Advance simulated resource state for this test."""
        self.state = status_color(pack)

    def show(self, color):
        """Record the requested logical light color."""
        self.state = color

    def metadata(self):
        """Return the fake output's options for logging assertions."""
        return self.options


def modules(root):
    """Supply synthetic inference and light adapters with the real counting pipeline."""
    return SyntheticBackend, SyntheticBackend, Pipeline, open_camera, FakeLights, status_color


@pytest.fixture
def station(tmp_path):
    """Use real station settings with a tiny fake model and complete identity."""
    root = tmp_path / "vision"
    (root / "configs").mkdir(parents=True)
    for path in (VISION_ROOT / "configs").glob("*.json"):
        (root / "configs" / path.name).write_bytes(path.read_bytes())
    runtime = json.loads((root / "configs/runtime.json").read_text())
    runtime["rotate_180"] = True
    (root / "configs/runtime.json").write_text(json.dumps(runtime))
    (root / "configs/view.json").write_text(
        json.dumps(dict(normalized_xywh=[0, 0, 1, 1], defect_exit_x=0.1))
    )
    (root / "models").mkdir()
    model = root / "models/can-camera-v1.hef"
    model.write_bytes(b"fake test model; never sent to Hailo")
    model.with_suffix(".hef.json").write_text(
        json.dumps(
            dict(
                sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                source_sha256=runtime["model_sha256"],
            )
        )
    )
    return root


def test_ui_recipe_rotation_masks_logging_and_light_cleanup(station):
    """Check that ui recipe rotation masks logging and light cleanup."""
    original = (station / "configs/runtime.json").read_bytes()
    engine = VisionEngine(
        station,
        recipe={"Red": 1, "Green": 0, "Blue": 0},
        gpio=True,
        gpio_active_low=True,
        module_loader=modules,
    )
    engine.start(camera_info={"requested_fps": 60})
    backend, lights = engine.backend, engine.lights
    try:
        frame = np.full((140, 200, 3), (0, 0, 240), np.uint8)
        frame[0, 0] = (10, 20, 30)
        first = engine.process(frame, 0.1, render=True)
        second = engine.process(frame, 0.2, render=False)
        assert first[0].shape == frame.shape
        assert second[0] is None
        np.testing.assert_array_equal(backend.seen, cv2.rotate(frame, cv2.ROTATE_180))
        counts, metadata = engine.snapshot(0.6)
        assert counts == {"Red": 1, "Green": 0, "Blue": 0}
        assert metadata["pack_ready"]
        assert metadata["recipe"] == counts
        assert lights.options["active_low"] is True
        engine.process(frame, 0.7)
        assert lights.state == "green"
        engine.pause(True)
        assert lights.state == "yellow"
        engine.new_box(0.8)
        assert engine.snapshot(0.8)[0] == dict(Red=0, Green=0, Blue=0)
        assert engine.snapshot(0.8)[1]["box"] == 2
    finally:
        engine.close()
    assert lights.closed and lights.state == "off" and backend.closed
    assert (station / "configs/runtime.json").read_bytes() == original
    summary = json.loads((engine.folder / "summary.json").read_text())
    assert summary["processed_frames"] == 3
    assert "read_to_count_ms" in summary["timing_ms"]
    assert len((engine.folder / "observations.jsonl").read_text().splitlines()) == 3


def test_bad_model_identity_is_rejected_before_hardware(station):
    """Check that bad model identity is rejected before hardware."""
    engine = VisionEngine(station, module_loader=lambda root: pytest.fail("Opened hardware"))
    (station / "models/can-camera-v1.hef").write_bytes(b"wrong model")
    with pytest.raises(VisionSetupError, match="hash"):
        engine.start()


def test_summary_keeps_pending_confirmation_instead_of_ready_total(station):
    """Check that summary keeps pending confirmation instead of ready total."""
    engine = VisionEngine(station, recipe=dict(Red=1, Green=0, Blue=0), module_loader=modules)
    engine.start()
    frame = np.full((140, 200, 3), (0, 0, 240), np.uint8)
    engine.process(frame, 0.1, render=False)
    engine.process(frame, 0.2, render=False)
    assert engine.snapshot(0.2)[1]["status"] == "WAIT"
    engine.close()
    final = json.loads((engine.folder / "summary.json").read_text())["final"]
    assert final["counts"]["red"] == 1 and not final["ready"]
    assert final["status"] == "WAIT"


def test_backend_startup_failure_releases_lights(station):
    """Check that backend startup failure releases lights."""

    def broken_backend(*args):
        """Raise a startup error to check that opened outputs are released."""
        raise RuntimeError("No Hailo device")

    engine = VisionEngine(
        station,
        module_loader=lambda root: (
            broken_backend,
            Onnx,
            Pipeline,
            open_camera,
            FakeLights,
            status_color,
        ),
    )
    with pytest.raises(VisionSetupError, match="No Hailo"):
        engine.start()
    assert FakeLights.instances[-1].closed


def test_config_precedence_and_cli_flags(tmp_path):
    """Check that config precedence and cli flags."""
    paths = configuration_paths(VISION_ROOT, config_dir=tmp_path, colors=tmp_path / "profile.json")
    assert paths["runtime"] == tmp_path / "runtime.json"
    assert paths["colors"] == tmp_path / "profile.json"
    args = parse_arguments(["--backend", "hailo", "--source", "0", "--gpio", "--gpio-active-low"])
    assert args.gpio and args.gpio_active_low and args.source == 0
    with pytest.raises(SystemExit):
        parse_arguments(["--gpio-active-low"])


@pytest.mark.parametrize(
    "override,expected",
    [
        ({}, "PASS"),
        ({"pack_ready": False, "status": "WAIT"}, "REVIEW"),
        ({"reviews": ["Check box"]}, "REVIEW"),
        ({"framing_warning": "clipped"}, "REVIEW"),
    ],
)
def test_saved_box_uses_counter_ready_not_just_totals(tmp_path, override, expected):
    """Check that saved box uses counter ready not just totals."""
    recipe = dict(Red=4, Green=4, Blue=4)
    metadata = dict(pack_ready=True, status="RECIPE REACHED", reviews=[], **{})
    metadata.update(override)
    status = inspection_status(recipe, recipe, metadata)
    assert status == expected
    record = save_box(tmp_path / "history.csv", "Test", recipe, recipe, status_override=status)
    assert record["Status"] == expected
    assert inspection_status(recipe, dict(Red=5, Green=4, Blue=3), metadata) == "FAIL"


def test_custom_recipe_persistence_keeps_current_station_default(tmp_path):
    """Check that custom recipe persistence keeps current station default."""
    path = tmp_path / "recipes.json"
    save_recipes(
        path,
        {"Station Recipe": dict(Red=4, Green=4, Blue=4), "Two Each": dict(Red=2, Green=2, Blue=2)},
    )
    recipes = load_recipes(path, dict(Red=1, Green=1, Blue=1))
    assert recipes["Station Recipe"]["Red"] == 1
    assert recipes["Two Each"]["Blue"] == 2


@pytest.fixture(scope="session")
def app():
    """Provide an offscreen Qt application for widget and worker tests."""
    return QApplication.instance() or QApplication([])


def wait_until(app, condition, timeout=3.0):
    """Process Qt events until the condition succeeds or the test times out."""
    deadline = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > deadline:
            pytest.fail("Timed out waiting for the camera worker")
        time.sleep(0.002)
    app.processEvents()


class FakeCamera:
    """Group synthetic checks and fixtures for this module's behavior."""

    released = False
    reads = 0

    def read(self):
        """Return the next synthetic camera image or the configured failure."""
        time.sleep(0.003)
        self.reads += 1
        return True, np.zeros((40, 60, 3), np.uint8)

    def release(self):
        """Record release of the fake device."""
        self.released = True


class FakeEngine:
    """Increment every analyzed frame so a stale preview count is detectable."""

    def __init__(self, *args, **kwargs):
        """Initialize isolated fake state without opening physical hardware."""
        self.count = self.processed = self.resets = 0
        self.closed = False

    def start(self, **kwargs):
        """Record that the fake engine has entered its running state."""
        pass

    def snapshot(self, now=0):
        """Return the fake engine's current carton status."""
        return dict(Red=self.count, Green=0, Blue=0), dict(ready=True, status="IN PROGRESS")

    def orient(self, frame):
        """Return the synthetic input without camera orientation changes."""
        return frame

    def preview(self, frame):
        """Return a synthetic preview image for Qt delivery checks."""
        return frame

    def process(self, frame, now, render=True, **kwargs):
        """Advance the simulated engine's observation and carton snapshot."""
        self.count += 1
        self.processed += 1
        counts, metadata = self.snapshot(now)
        return frame if render else None, [], counts, metadata

    def new_box(self, now):
        """Clear the simulated carton and restart its count state."""
        self.count = 0
        self.resets += 1

    def pause(self, paused):
        """Record the simulated engine's pause state."""
        pass

    def fail(self, error):
        """Simulate the configured operation failure for error-handling checks."""
        pass

    def close(self):
        """Mark this fake resource closed for cleanup assertions."""
        self.closed = True


def test_worker_processes_beyond_preview_and_freezes_before_acknowledging(app):
    """Check that worker processes beyond preview and freezes before acknowledging."""
    camera, engine = FakeCamera(), FakeEngine()
    worker = CameraWorker(
        dict(frame_width=60, frame_height=40, camera_fps=60, preview_fps=10),
        engine_factory=lambda *args, **kwargs: engine,
        camera_opener=lambda *args: (camera, {}),
    )
    previews, commands = [], []
    worker.frame_ready.connect(lambda frame, events, counts, metadata: previews.append(counts))
    worker.command_done.connect(lambda command, result: commands.append((command, result)))
    worker.start()
    try:
        wait_until(app, lambda: len(previews) == 1)
        assert engine.processed == 0  # Setup does not count cans already in the ROI.
        worker.start_box()
        wait_until(app, lambda: engine.processed >= 12)
        assert len(previews) == 1  # A slow GUI cannot accumulate frame signals.
        worker.freeze_box()
        wait_until(app, lambda: any(command == "finish" for command, _ in commands))
        frozen = next(
            result["counts"]["Red"] for command, result in commands if command == "finish"
        )
        assert frozen == engine.count and frozen >= 12
        assert frozen > previews[0]["Red"]
        reads = camera.reads
        wait_until(app, lambda: camera.reads > reads + 3)
        assert engine.count == frozen
        worker.start_box()
        wait_until(app, lambda: engine.resets == 1)
        assert (
            next(
                result["counts"]["Red"]
                for command, result in reversed(commands)
                if command == "start"
            )
            == 0
        )
    finally:
        assert worker.stop()
        app.processEvents()
    assert engine.closed and camera.released


def test_qt_pages_load_and_finish_saves_worker_snapshot(app, tmp_path, monkeypatch):
    """Check that qt pages load and finish saves worker snapshot."""
    hmi = HMI(windowed=True, data_dir=tmp_path)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
    try:
        for page in ("home", "configure", "recipes", "run", "history"):
            hmi.show(page)
            app.processEvents()
        hmi.show("run")
        hmi.config = dict(Red=4, Green=4, Blue=4)
        hmi.counts = dict(Red=3, Green=4, Blue=4)  # Stale preview before Finish acknowledgment.
        hmi.box_started = hmi._finishing = True
        metadata = dict(
            ready=True,
            pack_ready=True,
            status="RECIPE REACHED",
            recipe=dict(hmi.config),
            reviews=[],
        )
        hmi.on_worker_command(
            "finish", dict(counts=dict(hmi.config), metadata=metadata, active=False)
        )
        with hmi.history_file.open(newline="") as stream:
            record = next(csv.DictReader(stream))
        assert record["Observed Red"] == "4" and record["Status"] == "PASS"
        assert not hmi.running and not hmi.box_started
        assert hmi.finish_button.text() == "START NEXT BOX"
    finally:
        hmi.box_started = False
        hmi.window.close()
