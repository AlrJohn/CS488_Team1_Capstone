# Yards can inspection software

We use a trained can-instance model to find individual cans, then OpenCV to identify red, green and blue label pixels within each can's mask. We track those instances across images and maintain a cumulative count for one carton. The normal target is four of each color.

Our current rule assumes that a confirmed can in the active count area goes into the carton. An observed crossing of the separate left defect line removes a counted can. We do not verify carton placement, and returning a can through another edge does not subtract it.

## Choose the program

| Program | Purpose | Start here |
| --- | --- | --- |
| Current Windows counter | PyTorch/CUDA or CPU inference, interactive ROI/defect setup, timed trial recording | [Windows setup](windows/README.md), `windows/run.py` |
| Current Raspberry Pi counter | Compiled Hailo-8 model on Pi 5 + AI HAT+ 26 TOPS | [Pi setup](pi/README.md), `pi/run.py` |
| Earlier color-only prototype | Historical HSV connected-region detector and visible pick/return boundary | [Earlier prototype](legacy/color_baseline/README.md) |

The Windows and Pi programs share the same color, duplicate-mask, physical-instance and counting modules in [common](common/README.md). Their inference adapters and preview/capture code are separate. The shipped checkpoint and compiled model are in [models](models/README.md). You do not need our private recordings or old experiment folders to start either program.

## Repository layout

| Path | What it contains |
| --- | --- |
| `windows/` | Current Windows entry point, PyTorch adapter, dependency pins and setup instructions |
| `pi/` | Pi entry point and Hailo/ONNX output adapter and pipeline |
| `common/` | Shared HSV analysis, mask deduplication, tracking memory, ledger, defect rules and recording helpers |
| `configs/` | Published example colors, ROI, recipe and training parameters; save machine-specific copies under `configs/local/` |
| `models/` | The camera-v1 `.pt`, Hailo-8 `.hef`, identity metadata and checksums |
| `tools/` | Model verification and parameterized fine-tuning/export/calibration/compilation entry points |
| `tests/` | Synthetic checks for the current shared counting behavior |
| `legacy/color_baseline/` | Earlier runnable source, tests and historical manuals |
| `docs/` | Development history, architecture, testing, measured performance and publication notes |
| `licenses/` | Retained third-party license and tracker provenance |

## Read the development sequence

The [development history](docs/development-history.md) explains why we moved from color regions to instance masks, added temporal confirmation and cumulative counting, adapted the model to the camera, and compiled it for Hailo. Internal experiment names were not formal releases; this repository uses descriptive folders rather than publishing every trial directory.

The [architecture guide](docs/architecture.md) maps each stage to its Python file. The [test plan](docs/testing.md) separates can recognition, color, identity and pack-level evaluation. The [validation notes](docs/validation.md) distinguish measured results from remaining work.

## Run checks without a camera

After installing the dependencies for your platform, run these from the repository root:

```bash
python vision/tools/verify_models.py
python -m unittest discover -s vision/tests -v
```

The synthetic tests check software behavior. They do not measure accuracy on moving cans. The [earlier prototype](legacy/color_baseline/README.md) has its own independent tests and artificial demo.

## Local material

We keep raw videos, trial images, per-frame logs, datasets, calibration tensors, downloaded installers, environments and unsuccessful build artifacts outside the published source. They are ignored by Git. New Windows and Pi output goes under `vision/runs/`; the folder is created when needed.

Our example geometry comes from a controlled setup and must be checked against your camera. Before counting, keep waiting stock outside the count area and confirm that complete labels remain visible through the lift. The latest Pi trial counted twelve cans correctly as six pairs. Four-can pickups, defect removal, sustained operation and the production environment still need their own checks.

See [what is published and what stays local](docs/publication.md) and the retained [third-party notices](THIRD_PARTY_NOTICES.md).
