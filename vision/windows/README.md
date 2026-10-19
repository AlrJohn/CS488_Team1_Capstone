# Windows can counter

This is the current laptop program. It loads our camera-v1 one-class segmentation checkpoint, classifies label color with OpenCV and uses the shared V4 counter. An NVIDIA GPU is optional; CPU inference is supported but needs its own timing measurement.

## Install on another computer

Use 64-bit Python 3.12 and open the repository root in VS Code. Create your own environment:

```powershell
py -3.12 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install --upgrade pip
```

Choose one PyTorch installation. For a CPU-only computer:

```powershell
.\.venv-windows\Scripts\python.exe -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu
```

For the NVIDIA/CUDA 11.8 configuration used in our laptop trials:

```powershell
.\.venv-windows\Scripts\python.exe -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu118
```

Then install the remaining pinned dependencies and verify the model:

```powershell
.\.venv-windows\Scripts\python.exe -m pip install -r vision/windows/requirements.txt
.\.venv-windows\Scripts\python.exe vision/tools/verify_models.py
.\.venv-windows\Scripts\python.exe vision/windows/run.py --source 0
```

The code selects CUDA when available and otherwise selects CPU. Force CPU with `--device cpu`. If the camera is a different device, try `--source 1`. The default camera backend is DirectShow; `--backend auto` or `--backend msmf` provide alternatives. For other CUDA configurations, use the [official PyTorch version instructions](https://pytorch.org/get-started/previous-versions/#v271); keep the documented torch/torchvision pair together.

Select `.venv-windows` as the VS Code Python interpreter. The Run and Debug configuration named **Current Windows — 12-pack counter** uses this entry point; the earlier demo is labeled separately.

## Set up your view

1. Aim the camera so complete labels remain visible throughout a pick. Keep stationary stock below or outside the active ROI.
2. Check orientation. Our example uses 180-degree rotation; use `--no-rotate-180` for an upright camera. A rotation change requires recalibrating any saved view.
3. Press **O** and select the yellow count area.
4. Press **D** and click the left defect line, leaving space to see a can on its left after crossing.
5. Keep that area empty, begin with an empty carton, and press **P**.

The application saves your geometry to ignored `vision/configs/local/windows-view.json`. The public `configs/view.json` is only an example. To adjust HSV, copy `configs/colors.json` under `configs/local/`, edit its ranges and pass `--color-config` with that path. The ranges must not overlap. Color uncertainty should stay `unknown` rather than being forced to the desired recipe.

## Controls and files

| Key | Action |
| --- | --- |
| P | Start the current empty box trial |
| N | Save the trial and prepare the next empty box; press P again to start it |
| O / D | Set ROI / defect exit while not recording |
| U | Undo the last count transaction |
| A | Acknowledge a review after independently checking the counts; this does not correct totals |
| Q | Save and quit |

The default recipe is `--recipe 4,4,4`; values are red, green, blue. Picks are admitted from the ROI, without a packaging-line crossing. Only observed left-side defects subtract. Carton placement remains an assumption.

`run.py` manages the camera, geometry controls, ledger and recording. `detector.py` loads PyTorch weights, predicts boxes/masks, invokes the shared HSV/deduplication functions and draws can contours. All counting and physical-instance rules come from `../common/`.

Every active trial saves lossless source images, annotated JPEGs, JSON observations, events and a summary below ignored `vision/runs/windows/`. FFmpeg finalizes timed raw/annotated MP4s after the trial. Closing may take several seconds. The video can repeat a display image to preserve timing; repeated display frames are not new detections. Recording speed is part of the laptop measurements.

Use `--output-root` for a different private run directory. Do not place raw footage in the source folders. No Hailo installation or private experiment directory is needed on Windows.
