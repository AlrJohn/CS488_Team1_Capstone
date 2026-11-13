# Can Inspection System UI

The runnable touchscreen application is in **[corrected/](corrected/README.md)**. It uses the Qt Designer screens and the same Pi vision, counting and stack-light modules as `vision/pi/run.py`.

From the repository root, with the Pi's working Python environment activated:

```bash
python -m pip install -r UI_Design/corrected/requirements.txt
python UI_Design/corrected/main.py --backend hailo --source 0 --gpio --gpio-active-low
```

Run this from the Pi desktop. Close the terminal counter and light-test program before opening Production Run; the applications use the same hardware.

| Location | Purpose |
| --- | --- |
| `corrected/` | Editable, integrated application. Start here when changing the running UI. |

The earlier top-level prototype, autosave and ZIP handoff have been removed from the working tree. Their source remains in Git history. `corrected/` is the only maintained UI implementation; we retain that path so the current Pi launch command keeps working. Designer widget names and resource filenames also stay stable.

The [integration instructions](corrected/README.md) explain the controls, settings, file responsibilities and Pi checks.
