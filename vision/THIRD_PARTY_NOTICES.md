# Third-party components

The current software uses Ultralytics YOLO and includes a portable copy of its ByteTrack implementation. The retained upstream license is [AGPL-3.0](licenses/Ultralytics-AGPL-3.0.txt). Tracker provenance and the original portability modifications are recorded in [licenses/provenance.json](licenses/provenance.json). During repository organization, imports were redirected to `vision/common/`; the tracking equations and count policy were preserved.

The shipped one-class segmentation checkpoints use an Ultralytics architecture. Consult the [upstream licensing information](https://www.ultralytics.com/license) before redistributing or integrating those components. This notice does not assign a new license to the team's research documents, photographs or presentation files.

Other runtime dependencies retain their own licenses: PyTorch/torchvision, NumPy, OpenCV, lap and imageio-ffmpeg. FFmpeg is provided through imageio-ffmpeg or a system installation for Windows recordings. The Pi uses HailoRT and its matching OS driver/firmware; official installers and Hailo Dataflow Compiler are not included in this repository.
