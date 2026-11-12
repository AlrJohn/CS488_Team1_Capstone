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
| `CORRECTEDFinalizedCanDetectionUISystem_Yards_Vision_Integrated.zip` | Earlier UI handoff, kept as a reference. The running source is now in `corrected/`. |
| Top-level `.ui`, `widget.py`, `pyproject.toml`, `requirements.txt`, `recipes/` | Original design and prototype files. The integrated application does not load these copies. |

The [integration instructions](corrected/README.md) explain the controls, settings, file responsibilities and Pi checks.
