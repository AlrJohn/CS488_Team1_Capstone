# Source and private material

We publish the current Windows and Raspberry Pi runtimes, the shared implementation, the two selected model artifacts, model identity metadata, example configuration, tests and reusable model-build entry points. We retain the earlier color-only source/manual and dated research notes to show how the approach changed.

We do not publish the complete experimental workspace. Its directories mix private recordings, draft annotations, intermediate checkpoints, environment packages, compiler outputs and scripts tied to individual trials. The [development history](development-history.md) records their role and the reasons for the changes.

## Kept local by Git ignore rules

- Raw source videos, annotated camera videos, snapshots and trial frames.
- `vision/runs/` and nested sessions/results/source-version folders, including detailed logs and timing arrays.
- Training datasets, labels, calibration tensors and evaluation footage.
- Downloaded candidate checkpoints, ONNX/HAR intermediates, installers and package archives. Only the two named runtime models in `vision/models/` are included.
- Virtual environments, caches, machine calibration under `configs/local/`, browser downloads and SSH/access files.

The ignore rules do not delete any of those files. Ignoring a path does not remove a file already committed, so inspect `git diff --cached --stat` and `git ls-files` before committing footage from another location. Share private evidence separately when the team needs it.

## Portability

Each platform has its own dependency file and installation guide. Paths are resolved from the repository instead of a team member's home directory. No runtime import requires `runs`. New recordings are written into ignored output directories. The shared code avoids duplicated PC/Pi counting rules.

The published geometry and HSV ranges are examples from the controlled view, not a universal calibration. A new camera requires checking the view and light. The Pi additionally needs the correct Hailo-8 OS driver/runtime and Python binding; the repository does not bundle installers or the proprietary compiler.

The compatibility `vision/run.py` and `vision/yards_vision` import forward to the earlier color-only implementation so old commands/local experiments still resolve. New work starts at `windows/run.py` or `pi/run.py`.

## Before pushing

Run the documented model and software checks, inspect the source/model diff, and confirm that `runs`, camera footage, environment files and local configuration remain ignored. Keep the [third-party notices](../THIRD_PARTY_NOTICES.md). Record any later model replacement with its source identity and new validation; a copied filename alone is insufficient.
