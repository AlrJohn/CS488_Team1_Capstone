# Raspberry Pi 5 / Hailo-8 counter

This runtime is for a Pi 5 with the **AI HAT+ 26 TOPS, Hailo-8**. It uses the compiled camera-v1 `.hef`; it does not load the PC `.pt` model. The HAT runs the neural network. The Pi CPU reconstructs masks and performs OpenCV color analysis, tracking, counting, drawing and saving.

The current deployed pilot was checked on Ubuntu 26.04 ARM64 with official HailoRT, PCIe driver and firmware **4.24.0**, plus an isolated Python **3.12.15** environment. Those versions describe our checked stack, not a requirement to replace a working OS. Hailo-8L and Hailo-10 are different compilation targets.

## Prepare the Pi

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

`run.py` handles capture, keyboard input, rendering and logs. `yardspi/backends.py` opens HailoRT streams. `yardspi/decoding.py` reconstructs native-resolution can masks and boxes. `yardspi/pipeline.py` invokes the shared modules under `vision/common/`.

The camera request is 1280×720 MJPEG at 30 FPS. Requested/reported settings are logged; actual analyzed FPS is measured separately. The default rotation and ROI match our example setup. The Pi renderer shows a transparent mask fill and box, without the explicit contour stroke used by the Windows renderer. Masks are still used for color analysis.

## Configure another mounting

Copy the public JSON examples to ignored `vision/configs/local/`. Check `normalized_xywh` and `defect_exit_x` in the view, HSV values in colors, and `rotate_180` / `expected_recipe` in the runtime copy. Geometry is expressed in image fractions. The Windows O/D controls can help create a compatible view JSON, but only use it on the Pi if the physical camera framing matches.

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --view-config vision/configs/local/pi-view.json \
  --runtime-config vision/configs/local/pi-runtime.json \
  --color-config vision/configs/local/pi-colors.json
```

The Pi preview does not currently include the Windows calibration dialogs. Many frozen policy entries in runtime JSON are records of the baseline; confirmation/memory limits remain Python defaults. See the [architecture guide](../docs/architecture.md) before changing them.

## Trial controls and output

Click the preview. **P** starts counting with an empty box and count area. **N** closes the box and immediately resets the active counter for the next box; clear the area first. **Q** saves/quits. **U** undoes the last transaction. **A** clears a review after manual verification, without correcting totals.

Normal operation saves observations, events, metadata, timing samples and a summary to ignored `vision/runs/pi/`. Add `--save-preview` for annotated JPEGs or `--save-source` for lossless oriented PNGs. Saving both is useful for diagnosing errors but slows the synchronous capture loop.

For an unattended timing trial, begin with an empty box:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --headless --auto-start --seconds 60
```

For a replay with actual inference and original observation timestamps:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo \
  --session /path/to/private/session --headless --auto-start
```

Replay needs every source PNG and its observation log, plus a view configuration matching that recording. Session PNGs are already oriented. For an already oriented ordinary video, use `--already-oriented` to avoid rotating twice. The optional ONNX backend is a workstation/CPU conversion check, not HAT acceleration.

The first full-pack Pi trial matched twelve cans as six pairs. The earlier trial had an extra admission and a color/identity warning. The known INT8 tracking failure remains open. See [validation](../docs/validation.md) before treating a recipe match as production acceptance.
