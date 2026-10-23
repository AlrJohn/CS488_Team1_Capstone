# Updating the Pi from the repository

The supported application is `vision/pi/run.py` in the Git checkout. It imports shared processing from that checkout's `vision/common/` and the model from `vision/models/`. The Python environment supplies installed libraries and can be kept separately from the source.

Our normal workflow is to edit and test on the PC, commit and push reviewed changes, then pull on the Pi. Pi recordings and station calibration stay outside tracked source. New Python files do not need to be copied into old `yards-pilot-*` or `yards-gpio-pilot-*` folders.

## Preserve campus changes before the first update

The campus session included Python and calibration changes made only on the Pi. Those files have not been compared on the PC. Before pulling into that checkout, save its source and settings. From the Pi repository root:

```bash
git status --short
stamp=$(date +%Y%m%d-%H%M%S)
tar -czf "../yards-campus-$stamp.tar.gz" vision/pi vision/common vision/configs
git diff --binary HEAD -- vision > "../yards-campus-$stamp.patch"
```

The archive includes current source and ignored local calibration, while the patch records tracked changes. If the edited code is still in an old pilot copy, archive its corresponding `vision/pi`, `vision/common` and `vision/configs` too. These folders contain no run recordings. Keep the archive private because station settings may include machine-specific paths.

Bring these files back to the PC for comparison and merge the campus Python changes before treating both versions as equivalent. GitHub commits `fe4edee` and `2ae8232` already include two-of-five confirmation and the red tolerance/saturation adjustment. Further Pi-only changes may exist. Do not reset the Pi checkout or replace edited files to make a pull succeed.

## Station calibration

After identifying the actual files used on campus, keep copies here:

```text
vision/configs/local/pi/
    runtime.json
    colors.json
    view.json
```

Use the settings selected by the old launch command or session metadata; they may differ from the defaults. This folder is ignored by Git, so pulling source does not replace the calibration. Changes intended for every station can instead be reviewed on the PC and committed to the public examples.

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --config-dir vision/configs/local/pi
```

Startup should print a source path inside this checkout. Saved metadata includes the entry point, interpreter and loaded settings. Existing desktop shortcuts must also select the repository entry point rather than an old source copy.

## Normal updates after migration

On the PC, run the checks in the development environment before reviewing and committing:

```powershell
python -m unittest discover -s vision/tests -v
python vision/tools/verify_models.py
git status --short
```

Commit and push the intended source/config changes. Runs remain ignored. Module 3 working documents remain locally excluded until the team is ready to publish them.

On the Pi, stop the counter and confirm the checkout is clean before pulling:

```bash
git status --short
git pull --ff-only
.venv-pi/bin/python -m pip install -r vision/pi/requirements.txt
.venv-pi/bin/python vision/tools/verify_models.py
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --config-dir vision/configs/local/pi
```

Tracked Pi edits must first be preserved and reconciled on the PC. Do not use a hard reset or blindly apply an old patch over the updated program. Pulling does not install HailoRT, its driver or optional GPIO libraries; those are environment components covered in the Pi README. Add `--gpio` after installing its dependency and checking the breadboard circuit.

An existing working interpreter outside the repo can replace `.venv-pi/bin/python` in these commands. The source argument remains this checkout's `vision/pi/run.py`.
