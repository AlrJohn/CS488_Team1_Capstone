"""Connect the Qt screens to the same Pi model, ledger and GPIO used by run.py.

The camera worker owns this object. Qt widgets never access its model or ledger.
No model weights or station configurations are copied into the UI directory.
"""
from collections import deque
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

BASE = Path(__file__).resolve().parent
VISION_ROOT = BASE.parents[1] / 'vision'
COLORS = ('red', 'green', 'blue')
PALETTE = {'red': (0, 0, 255), 'green': (0, 230, 0),
           'blue': (255, 110, 40), 'unknown': (160, 160, 160)}


class VisionSetupError(RuntimeError):
    """Report a model, configuration or hardware problem on the HMI."""


def configuration_paths(root, config_dir=None, runtime=None, colors=None, view=None):
    """Use the same configuration precedence as the terminal program."""
    folder = Path(config_dir) if config_dir else Path(root) / 'configs'
    return {name: Path(override) if override else folder / (name + '.json')
            for name, override in (('runtime', runtime), ('colors', colors), ('view', view))}


def import_pi_modules(root):
    """Resolve the repository layout: vision/common and vision/pi/yardspi."""
    root = Path(root).resolve()
    for folder in (root, root / 'pi'):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    from yardspi.backends import HailoBackend, OnnxBackend
    from yardspi.pipeline import Pipeline
    from yardspi.camera import open_camera
    from stack_lights import StackLights, status_color
    return HailoBackend, OnnxBackend, Pipeline, open_camera, StackLights, status_color


def display_colors(values):
    """Translate the shared lowercase recipe into the Designer label names."""
    return {color.capitalize(): int(values.get(color, 0)) for color in COLORS}


def inspection_status(expected, observed, metadata):
    """A matching total is accepted only when the shared counter is ready."""
    if observed != expected:
        return 'FAIL'
    if (not metadata.get('pack_ready') or metadata.get('reviews')
            or metadata.get('framing_warning') or metadata.get('status') != 'RECIPE REACHED'):
        return 'REVIEW'
    return 'PASS'


def draw_vision_frame(frame, row, masks, defect_exit_x):
    """Draw masks within each can rectangle, plus the ROI and defect boundary."""
    view = frame.copy()
    x, y, width, height = map(int, row['roi_xywh'])
    region = view[y:y+height, x:x+width]
    for observation, mask in zip(row['observations'], masks):
        color = PALETTE.get(observation['color'], PALETTE['unknown'])
        mask = np.asarray(mask, dtype=np.uint8)
        mx, my, mw, mh = cv2.boundingRect(mask)
        if mw and mh:
            tile = region[my:my+mh, mx:mx+mw]
            selected = mask[my:my+mh, mx:mx+mw].astype(bool)
            tile[selected] = (tile[selected] * .65 + np.asarray(color) * .35).astype(np.uint8)
        a, b, c, d = map(round, observation['xyxy_roi'])
        cv2.rectangle(view, (x+a, y+b), (x+c, y+d), color, 1)
        cv2.putText(view, f'T{observation["track_id"]} {observation["color"]}',
                    (x+a, max(15, y+b-3)), 0, .45, color, 1, cv2.LINE_AA)
    cv2.rectangle(view, (x, y), (x+width, y+height), (0, 230, 255), 2)
    defect = round(x + width * defect_exit_x)
    cv2.line(view, (defect, y), (defect, y+height), (255, 80, 230), 2)
    return view


class VisionEngine:
    """Own one Hailo session, shared counting pipeline, log and stack light."""

    def __init__(self, root=VISION_ROOT, *, backend='hailo', model=None,
                 config_dir=None, runtime=None, colors=None, view=None, recipe=None,
                 gpio=False, gpio_active_low=False, gpio_chip=None, output=None,
                 module_loader=import_pi_modules):
        self.root = Path(root).resolve()
        self.backend_name = backend
        self.model_path = Path(model) if model else None
        self.paths = configuration_paths(self.root, config_dir, runtime, colors, view)
        self.recipe = None if recipe is None else {k.lower(): v for k, v in recipe.items()}
        self.gpio_options = dict(enabled=gpio, active_low=gpio_active_low, chip=gpio_chip)
        self.output = Path(output) if output else self.root / 'runs' / 'pi-ui'
        self._module_loader = module_loader
        self.backend = self.pipeline = self.lights = None
        self.config = {}
        self._resources = ExitStack()
        self._times = deque(maxlen=30)
        self._samples = {}
        self._last = None
        self._snapshot_time = 0.
        self._log = None
        self.folder = None
        self.processed = 0
        self._failure = None

    def start(self, camera_info=None):
        """Validate the real model and open resources in the worker thread."""
        if self.backend is not None:
            raise VisionSetupError('Vision is already running.')
        try:
            for path in self.paths.values():
                if not path.is_file():
                    raise VisionSetupError('Missing station configuration: ' + str(path))
            configurations = {name: json.loads(path.read_text(encoding='utf-8'))
                              for name, path in self.paths.items()}
            self.config = configurations['runtime']
            if type(self.config.get('rotate_180')) is not bool:
                raise VisionSetupError('runtime.json needs rotate_180 set to true or false.')
            chosen = self.backend_name
            if chosen == 'auto':
                chosen = ('hailo' if self.model_path and self.model_path.suffix == '.hef'
                          else 'onnx' if self.model_path
                          else 'hailo' if (self.root/'models/can-camera-v1.hef').is_file()
                          else 'onnx')
            if chosen not in ('hailo', 'onnx'):
                raise VisionSetupError('Choose the hailo or onnx backend.')
            model = self.model_path or self.root/'models'/(
                'can-camera-v1.hef' if chosen == 'hailo' else 'can-camera-v1.onnx')
            if not model.is_file():
                raise VisionSetupError('Missing trained model: ' + str(model))
            identity_path = model.with_suffix(model.suffix + '.json')
            identity = json.loads(identity_path.read_text(encoding='utf-8'))
            if identity.get('sha256') != hashlib.sha256(model.read_bytes()).hexdigest():
                raise VisionSetupError('Model hash does not match its identity JSON.')
            source_hash = identity.get('source_sha256', identity.get('source_checkpoint_sha256'))
            if source_hash != self.config['model_sha256']:
                raise VisionSetupError('Model checkpoint does not match runtime.json.')
            Hailo, Onnx, Pipeline, _, Lights, self._status_color = self._module_loader(self.root)
            self.lights = self._resources.enter_context(Lights(**self.gpio_options))
            self.lights.update()
            self.backend = (Hailo if chosen == 'hailo' else Onnx)(model, self.config['inference'])
            self._resources.callback(self.backend.close)
            self.pipeline = Pipeline(self.root, self.backend, **self.paths, recipe=self.recipe)
            self.backend_name = chosen
            self._open_recording(configurations, identity, camera_info)
        except Exception as exc:
            self.fail(exc)
            self.close()
            if isinstance(exc, VisionSetupError):
                raise
            raise VisionSetupError(str(exc)) from exc

    def _open_recording(self, configurations, identity, camera_info):
        """Save station settings and real observations under ignored vision/runs."""
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
        self.folder = self.output / stamp
        self.folder.mkdir(parents=True)
        metadata = dict(interface='qt-hmi', backend=self.backend_name,
                        entry_point=str(BASE/'main.py'), vision_root=str(self.root),
                        python_executable=sys.executable, camera=camera_info,
                        model_identity=identity, started_utc=stamp,
                        effective_recipe=dict(self.pipeline.ledger.recipe),
                        stack_lights=self.lights.metadata(),
                        configurations={name: dict(path=str(self.paths[name].resolve()), contents=value)
                                        for name, value in configurations.items()})
        (self.folder/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        self._log = self._resources.enter_context(
            (self.folder/'observations.jsonl').open('w', encoding='utf-8'))

    def orient(self, frame):
        """Apply the same station rotation as run.py before ROI processing."""
        return cv2.rotate(frame, cv2.ROTATE_180) if self.config.get('rotate_180') else frame

    def preview(self, frame):
        """Show the configured boundaries during setup/pause without counting."""
        from common.geometry import restore_view
        frame = self.orient(frame)
        row = dict(roi_xywh=restore_view(self.pipeline.view, frame.shape[:2]), observations=[])
        return draw_vision_frame(frame, row, [], self.pipeline.view['defect_exit_x'])

    def snapshot(self, now=0.):
        """Read counts from the shared ledger, including pending/review status."""
        self._snapshot_time = now
        pack = (self.pipeline.counter.snapshot(now) if self.pipeline.counter
                else self.pipeline.ledger.snapshot())
        metadata = dict(ready=True, backend=self.backend_name, recipe=display_colors(pack['recipe']),
                        status=pack['status'], pack_ready=pack['ready'], reviews=list(pack['reviews']),
                        box=pack['box'], total=pack['total'],
                        stack_light=self.lights.state,
                        framing_warning=(self._last or {}).get('framing_warning', ''),
                        timing_ms=(self._last or {}).get('timing_ms', {}),
                        processed_fps=(self._last or {}).get('processed_fps', 0.))
        return display_colors(pack['counts']), metadata

    def process(self, frame, now, *, render=True, read_ms=0.):
        """Process every frame; draw only when a Qt preview update is due."""
        started = time.perf_counter()
        frame = self.orient(frame)
        row, masks = self.pipeline.process(frame, now)
        self.lights.update(row['pack'])
        counted = time.perf_counter()
        self._times.append(time.perf_counter())
        row['processed_fps'] = ((len(self._times)-1)/(self._times[-1]-self._times[0])
                                if len(self._times)>1 else 0.)
        row['timing_ms']['read_ms'] = read_ms
        row['timing_ms']['read_to_count_ms'] = (counted-started)*1000 + read_ms
        row['stack_light'] = self.lights.state
        self.processed += 1
        self._last = row
        overlay = (draw_vision_frame(frame, row, masks, self.pipeline.view['defect_exit_x'])
                   if render else None)
        row['timing_ms']['render_ms'] = (time.perf_counter()-counted)*1000
        row['timing_ms']['host_read_to_result_ms'] = (time.perf_counter()-started)*1000 + read_ms
        if self._log:
            self._log.write(json.dumps(row)+'\n')
            self._log.flush()
        for key, value in row['timing_ms'].items():
            self._samples.setdefault(key, []).append(value)
        counts, metadata = self.snapshot(now)
        return overlay, list(row['transfer_events']), counts, metadata

    def new_box(self, now):
        """Clear tracking and counts only after the operator requests a new box."""
        self.pipeline.new_box(now)
        self._last = None
        self._times.clear()
        self.lights.update()

    def pause(self, paused):
        """Show yellow while counting is paused, retaining the current box."""
        if paused:
            self.lights.update()
            self._times.clear()

    def undo(self, now):
        """Use the same undo operation as the terminal U key."""
        self.pipeline.ledger.undo(now)
        pack = (self.pipeline.counter.snapshot(now) if self.pipeline.counter
                else self.pipeline.ledger.snapshot())
        self.lights.update(pack)

    def acknowledge_review(self, now):
        """Use the terminal A action after an operator checks the actual box."""
        self.pipeline.ledger.acknowledge_review(now)
        pack = (self.pipeline.counter.snapshot(now) if self.pipeline.counter
                else self.pipeline.ledger.snapshot())
        self.lights.update(pack)

    def fail(self, error):
        """Retain the failure for the private session summary."""
        self._failure = str(error)

    def close(self):
        """Turn off GPIO, write a final record, then release Hailo and log files."""
        try:
            if self.lights:
                self.lights.show('off')
            if self.folder and self.pipeline:
                summary = dict(processed_frames=self.processed, failure=self._failure,
                               recording_status='failed' if self._failure else 'complete',
                               final=(self.pipeline.counter.snapshot(self._snapshot_time)
                                      if self.pipeline.counter else self.pipeline.ledger.snapshot()),
                               timing_ms={key: dict(median=float(np.median(values)),
                                                    p95=float(np.percentile(values, 95)))
                                          for key, values in self._samples.items()},
                               hardware_inference_executed=self.backend_name=='hailo' and self.processed>0)
                (self.folder/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
                (self.folder/'pack-events.json').write_text(
                    json.dumps(self.pipeline.ledger.events, indent=2), encoding='utf-8')
        finally:
            self._resources.close()
            self.backend = self.pipeline = self.lights = self._log = None
