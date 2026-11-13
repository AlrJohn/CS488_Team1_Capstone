# Software and libraries

CS488 · Team 1 · Module 3 development

We maintain separate dependency files for the workstation and Pi because their model backends differ. Install the file for the machine running the application. The selected model files are already included in `vision/models/`.

| Software | Version recorded in the project | Purpose and source |
| --- | --- | --- |
| Python | 3.12; Pi deployment guide records 3.12.15 | Application language; https://www.python.org/ |
| PyTorch / torchvision | 2.7.1 / 0.22.1 | Windows model execution; https://pytorch.org/ |
| Ultralytics | 8.4.177 | YOLOv8 segmentation, training and export; https://docs.ultralytics.com/ |
| NumPy | Windows 2.5.4; Pi 1.26.4 | Mask arrays, coordinates and calculations; https://numpy.org/ |
| OpenCV Python | Windows 5.0.0.93; Pi 4.11.0.86 | Capture, HSV sampling, geometry and previews; https://pypi.org/project/opencv-python/ |
| lap | 0.5.12 | Assignment operations used by tracking; https://pypi.org/project/lap/ |
| imageio-ffmpeg | 0.6.0 | FFmpeg executable for Windows recordings; https://pypi.org/project/imageio-ffmpeg/ |
| HailoRT, driver and firmware | 4.24.0 | Hailo-8 inference on the Pi; https://github.com/hailo-ai/hailort/releases/tag/v4.24.0 |
| gpiod | 2.5.0 | Pi GPIO lines for the stack light; see `pi/requirements-gpio.txt`; https://pypi.org/project/gpiod/ |
| PySide6 Essentials | Supported range >=6.8,<7; local cleanup checks used 6.12.0 | Qt widgets, Designer loading and worker thread; https://doc.qt.io/qtforpython-6/ |
| Hailo Dataflow Compiler | 3.34.0 | Workstation-only HEF compilation; https://hailo.ai/developer-zone/software-downloads/ |
| ONNX / ONNX Runtime | 1.18.0 / 1.22.0 | Workstation export and conversion checks; https://onnx.ai/ and https://onnxruntime.ai/ |
| Ruff / pytest / coverage | 0.17.5 / 9.2.0 / 7.17.3 | Optional formatting and software checks; `vision/requirements-dev.txt` |

The exact pins live in `windows/requirements.txt`, `pi/requirements.txt`, `pi/requirements-gpio.txt` and `tools/requirements-export.txt`. The touchscreen adds `UI_Design/corrected/requirements.txt` to the existing Pi environment. Its supported Qt range is not a record of the exact version installed on every Pi. Capture `python -m pip freeze` with each hardware test so its environment can be reproduced.

The Pi deployment guide records Ubuntu 26.04 ARM64 with a separate Python 3.12 environment. The original compiler build used Ubuntu 22.04 x86-64 under WSL and Python 3.10. The compiler does not run on the Pi and is not needed to use the shipped HEF.

Software sources above identify the packages; the dependency files define this project's selected versions. Third-party tracking code and model/library licenses are described in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
