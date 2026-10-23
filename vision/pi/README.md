# Raspberry Pi 5 / Hailo-8 counter

This runtime is for a Pi 5 with the **AI HAT+ 26 TOPS, Hailo-8**. It uses the compiled camera-v1 `.hef`; it does not load the PC `.pt` model. The HAT runs the neural network. The Pi CPU reconstructs masks and performs OpenCV color analysis, tracking, counting, drawing and saving.

The current deployed pilot was checked on Ubuntu 26.04 ARM64 with official HailoRT, PCIe driver and firmware **4.24.0**, plus an isolated Python **3.12.15** environment. Those versions describe our checked stack, not a requirement to replace a working OS. Hailo-8L and Hailo-10 are different compilation targets.

## Prepare the Pi

The supported source is this repository's `vision/pi/run.py`, with shared processing in `vision/common/`. Old pilot folders are backups, not the current application. See [updating from the PC and preserving campus changes](UPDATING.md) before the first pull on a Pi with local edits.

1. Install the matching Hailo-8 driver, firmware and HailoRT 4.24.0 for your OS. Download the official ARM64 runtime and the matching CPython 3.12 binding from [Hailo Developer Zone](https://hailo.ai/developer-zone/software-downloads/). The compiler stays on an x86-64 Linux workstation.
2. Run `hailortcli fw-control identify`. It should identify HAILO8. Resolve driver/firmware issues before starting Python.
3. Use Python 3.12 for the pinned ARM64 wheel. If your system Python is newer, install 3.12 separately; do not replace the OS interpreter. Our deployment used [uv-managed Python](https://docs.astral.sh/uv/guides/install-python/).
4. Clone the repository on the Pi. Run all commands below from its root.

With an existing Python 3.12 installation:

```bash
python3.12 -m venv .venv-pi
.venv-pi/bin/python -m pip install -r vision/pi/requirements.txt
.venv-pi/bin/python -m pip install /path/to/hailort-4.24.0-cp312-cp312-linux_aarch64.whl
.venv-pi/bin/python vision/tools/verify_models.py
```

Replace the wheel path with your downloaded file. If using uv, `uv python install 3.12` and `uv venv --python 3.12 .venv-pi` create the same isolated environment. The driver/runtime are OS components; installing a Python wheel alone does not install them. See the [official HailoRT release](https://github.com/hailo-ai/hailort/releases/tag/v4.24.0) and [Raspberry Pi AI overview](https://www.raspberrypi.com/documentation/computers/ai.html). Raspberry Pi OS package commands should not be applied blindly to Ubuntu.

## Start the actual Python application

From a terminal on the Pi desktop:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0
```

`run.py` handles capture, keyboard input, rendering and logs. `yardspi/camera.py` opens the camera and measures delivery without a model. `yardspi/backends.py` opens HailoRT streams. `yardspi/decoding.py` reconstructs native-resolution can masks and boxes. `yardspi/pipeline.py` invokes the shared modules under `vision/common/`. Startup prints the actual source path; metadata records it and the loaded configuration contents.

The camera request is 1280×720 MJPEG at 30 FPS. Requested/reported settings are logged; actual analyzed FPS is measured separately. The preview shows processed FPS, model time, color time and total analysis time. GUI drawing is limited to 10 FPS by default while analysis continues on every image read. `--preview-fps 0` draws every analyzed image. The default rotation and ROI match our example setup. The Pi shows a transparent mask fill and box; masks remain part of color analysis.

To configure colors under the current lighting before counting, add `--calibrate`:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 --calibrate
```

The setup screen collects labeled red/green/blue examples, fits HSV ranges and tests fresh examples before saving a new local profile. **Save & Test** returns to the counter with that profile already loaded; clear the area and press P to start. Use the same `--config-dir` or individual config flags as normal operation so camera geometry and existing station settings are retained. See [the calibration walkthrough](CALIBRATION.md) for the buttons, saved profiles and fitting controls.

## Optional breadboard status LEDs

The Pi can drive separate red, yellow and green indicator LEDs through BCM17, BCM27 and BCM22. Yellow means setup/counting/waiting; green follows the exact-recipe ready decision; red means review or over target. Each LED requires its own series resistor. Follow the [exact wiring and test instructions](GPIO-WIRING.md) before enabling pins.

Install `requirements-gpio.txt` in the same environment, run `check_lights.py` for a read-only availability check, then `check_lights.py --cycle` after wiring. Add `--gpio` to the camera command. `stack_lights.py` handles output and cleanup; model and counting rules are unchanged.

## Configure another mounting

Copy the public JSON examples to ignored `vision/configs/local/`. Check `normalized_xywh` and `defect_exit_x` in the view, HSV values in colors, and `rotate_180` / `expected_recipe` in the runtime copy. Geometry is expressed in image fractions. The Windows O/D controls can help create a compatible view JSON, but only use it on the Pi if the physical camera framing matches.

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --view-config vision/configs/local/pi-view.json \
  --runtime-config vision/configs/local/pi-runtime.json \
  --color-config vision/configs/local/pi-colors.json
```

The Pi has the color setup screen described above; ROI/defect geometry still comes from the view JSON. Many frozen policy entries in runtime JSON are records of the baseline; confirmation/memory limits remain Python defaults. See the [architecture guide](../docs/architecture.md) before changing them.

Both color checks are configured in the active color JSON. The ordinary check uses `interior_sampling`:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `min_pixels` | `25` | Minimum number of pixels matching the winning color |
| `min_coverage` | `0.1` | Winning color covers at least 10% of the sampled mask |
| `min_dominance` | `0.6` | Winning color receives at least 60% of all colored votes |

These are loaded settings, not fixed thresholds in the color-analysis function. Lower values accept less evidence; higher values require more. Use a positive integer pixel count, coverage above zero through one, and dominance above 0.5 through one. Older profiles without this section keep the previous 25 / 0.1 / 0.6 limits. The ordinary limits apply to the primary sample, including the full-mask sample used when an interior is too small.

For a mostly white front label, the shared color sampler can check the can's left and right body areas after an uncertain interior result. This second check has separate controls in the same JSON under `side_sampling`:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `enabled` | `true` | Try side sampling after insufficient interior evidence |
| `band_fraction` | `0.2` | Each band spans 20% of the can's bounding width |
| `min_pixels` | `40` | Minimum matching pixels in a qualifying band |
| `min_coverage` | `0.1` | Matching color covers at least 10% of that band's sampled mask |
| `min_dominance` | `0.8` | At least 80% of colored votes agree, per qualifying band and pooled |
| `min_row_fraction` | `0.35` | At least two matching pixels per row across 35% of the can height |

One qualifying side can be sufficient when the other side is white. Conflicting qualifying sides stay unknown. The one-pixel erosion and top/bottom exclusions still apply. Set `enabled` to `false` to disable the fallback; older files without the section use these defaults. Per-frame color evidence records whether `interior`, `full_mask` or `side_bands` supplied the result. The [architecture guide](../docs/architecture.md) explains the full rule. Start a new run after changing JSON. This adjustment still needs testing with the actual label orientations and campus lighting.

## Keep station settings together

One station folder can hold `runtime.json`, `colors.json` and `view.json` together:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --config-dir vision/configs/local/pi
```

The three files must already exist. They are not overwritten or added to Git by the application. Individual configuration flags override the matching file in `--config-dir`. Without this flag the published examples remain the defaults. See [migration](UPDATING.md) for preserving the actual campus calibration.

## Trial controls and output

Click the preview. **P** starts counting with an empty box and count area. **N** closes the box and immediately resets the active counter for the next box; clear the area first. **Q** saves/quits. **U** undoes the last transaction. **A** clears a review after manual verification, without correcting totals.

Normal operation saves observations, events, metadata, timing samples and a summary to ignored `vision/runs/pi/`. Add `--save-preview` for an annotated JPEG of every analyzed image, regardless of the GUI drawing limit, or `--save-source` for lossless oriented PNGs. Saving both slows the synchronous capture loop. A low GUI refresh rate does not mean analysis skipped those images.

## Measure camera delivery and processing separately

Close other camera programs and measure delivery in the intended lighting:

```bash
.venv-pi/bin/python vision/pi/run.py --probe-camera --source 0 --seconds 30
```

The probe warms up for two seconds, then measures camera reads with no model, GUI, GPIO or image saving. A blocked driver read can extend the duration. The result and `runs/pi/camera-probe-*.json` include measured delivery FPS and read gaps. These are host delivery measurements, not sensor timestamps.

`--camera-width`, `--camera-height`, `--camera-format` and `--camera-fps` select the same requested mode for probing and counting. Camera resolution does not change the HEF dimensions, but may change label detail and requires a framing/color check. A 30 FPS request is not proof of 30 FPS delivery. Linux camera modes and controls can be inspected with `v4l2-ctl --list-formats-ext` and `v4l2-ctl --list-ctrls-menus` if installed; exposure values should come from those supported controls.

For an unattended timing trial, begin with an empty box:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --config-dir vision/configs/local/pi --headless --auto-start --seconds 60
```

For a replay with actual inference and original observation timestamps:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo \
  --session /path/to/private/session --headless --auto-start
```

Replay needs every source PNG and its observation log, plus a view configuration matching that recording. Session PNGs are already oriented. For an already oriented ordinary video, use `--already-oriented` to avoid rotating twice. The optional ONNX backend is a workstation/CPU conversion check, not HAT acceleration.

The first full-pack Pi trial matched twelve cans as six pairs. The earlier trial had an extra admission and a color/identity warning. The known INT8 tracking failure remains open. See [validation](../docs/validation.md) before treating a recipe match as production acceptance.

Compare camera-only delivery with `effective_processed_fps` in the live summary, using the same camera mode and representative lighting. Normal `capture_intervals_ms` values come from the processing loop and cannot establish independent camera capacity. Stage timings separate inference, mask decoding, color analysis, drawing, display and image saving. The loop remains synchronous; this update reduces work without promising a Pi frame rate.
