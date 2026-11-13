# Build and deployment

CS488 · Team 1 · Module 3 development

The application runs from the checkout. There is no separate generated Python program to copy onto the Pi. The two selected models are included, so normal deployment requires installing the correct runtime, choosing the station settings and starting the application.

## Files required for operation

| Location | Required contents |
| --- | --- |
| `vision/common/` | Shared color, identity, count and support modules, including the licensed tracker in `vendor/` |
| `vision/pi/` | Pi terminal runner, camera/calibration, Hailo decoder/backend and GPIO driver |
| `vision/windows/` | Workstation runner and PyTorch adapter, for laptop testing |
| `vision/models/` | `.pt` for Windows; `.hef` for Hailo-8; matching identity JSON files |
| `vision/configs/` | Runtime, color, view and calibration examples |
| `UI_Design/corrected/` | Integrated HMI code, four Designer screens, can images, logo and station defaults |

The HMI uses the Pi/shared modules directly. It does not contain another detector or independent counting rule. The top-level UI prototype and retired color-only runner are no longer launch options.

## Raspberry Pi setup

Use a Pi 5 with the AI HAT+ 26 TOPS **Hailo-8**, the matched HailoRT/driver/firmware 4.24.0 stack and Python 3.12. The [Pi setup guide](../pi/README.md) gives the OS and wheel requirements. Run the following from the repository root, substituting the downloaded binding's actual path:

```bash
python3.12 -m venv .venv-pi
source .venv-pi/bin/activate
python -m pip install -r vision/pi/requirements.txt
python -m pip install /path/to/hailort-4.24.0-cp312-cp312-linux_aarch64.whl
python -m pip install -r vision/pi/requirements-gpio.txt
python -m pip install -r UI_Design/corrected/requirements.txt
python vision/tools/verify_models.py
hailortcli fw-control identify
```

Use the existing working environment if it is already configured. The Hailo Python wheel does not install the OS driver. Never replace the system Python to match this application.

For the integrated application, start from the Pi desktop:

```bash
python UI_Design/corrected/main.py --backend hailo --source 0 --gpio --gpio-active-low --camera-fps 60
```

The two GPIO flags match our low-trigger relay setup. Leave them out for a camera-only test. Only one counter, calibration screen or light-test program should own the hardware at a time. The camera request is 1280×720 MJPG; 60 FPS is an explicit request in this command. The published default remains 30 FPS and the preview limit is 10 FPS. Measure delivered camera FPS and analyzed FPS separately.

For live color setup, close the HMI and use the terminal runner:

```bash
python vision/pi/run.py --backend hailo --source 0 --camera-fps 60 --calibrate
```

Save & Test loads the new profile in that runner. To reuse it later in the HMI, pass the actual saved filename:

```bash
python UI_Design/corrected/main.py --backend hailo --source 0 --gpio --gpio-active-low --camera-fps 60 --color-config vision/configs/local/color-profiles/YOUR-SAVED-PROFILE.json
```

## Station settings

| File | Effective settings |
| --- | --- |
| `runtime.json` | Pi rotation, recipe, inference dimensions/confidence/NMS and tracker parameters |
| `colors.json` or a saved profile | HSV hue/tolerance, minimum saturation/value, interior and side evidence limits |
| `view.json` | Normalized count ROI and left defect position |
| `calibration.json` | Example collection, fitting and fresh color verification |
| HMI `station_settings.json` | Camera source/dimensions/format/FPS and preview rate |

Copy the three station JSON files into an ignored folder such as `vision/configs/local/station/`, then select it with `--config-dir`. Individual `--runtime-config`, `--color-config` and `--view-config` options override that folder. The HMI's selected recipe changes that session's target without rewriting runtime JSON. Some recorded policy values in runtime JSON describe Python defaults rather than adjustable controls; the [architecture guide](architecture.md) lists the actual sources.

Outputs are created automatically. Pi logs go under `vision/runs/pi/`, HMI session logs under `vision/runs/pi-ui/`, HMI recipes/history under `UI_Design/corrected/local/`, and Windows recordings under `vision/runs/windows/`. These folders and local color profiles stay out of Git.

## Windows setup

Create a Python 3.12 environment, install the appropriate CPU/CUDA PyTorch wheels and `vision/windows/requirements.txt`, then run:

```powershell
python vision/tools/verify_models.py
python vision/windows/run.py --source 0
```

The [Windows guide](../windows/README.md) covers GPU selection, ROI setup, defect calibration and recordings. Windows uses the `.pt` checkpoint; the Pi uses the `.hef`. The shared color and count modules are the same.

## Updating source or models

For source changes, use the [PC-to-GitHub-to-Pi update procedure](../pi/UPDATING.md). Preserve Pi-only edits and station profiles before pulling. Run the software checks, verify model identities, and then repeat a known pack and defect-removal test on the Pi.

Ordinary Python, HSV, ROI and UI changes do not require recompilation. New weights or network dimensions do. The [model tools guide](../tools/README.md) covers training, raw-head ONNX export, training-only calibration and Hailo compilation. Keep training, validation and test pickup sequences separate. Replace a selected model only after comparing masks, colors, identities and complete carton events.
