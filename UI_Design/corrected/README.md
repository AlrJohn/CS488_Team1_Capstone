# Pi touchscreen with the Yards vision counter

This application connects the corrected Qt design to the counter already used on the Raspberry Pi. The model, OpenCV color processing, tracking, defect handling and stack-light decisions come from `vision/pi/` and `vision/common/`. The UI calls those modules directly instead of starting `run.py` as a second process.

## Install and start

Use a terminal on the **Pi desktop**, open the repository root, and activate the same Python environment that runs `vision/pi/run.py` successfully. Keep its existing HailoRT, OpenCV, NumPy, tracker and GPIO packages.

Install the additional Qt dependency once, then launch:

```bash
python -m pip install -r UI_Design/corrected/requirements.txt
python UI_Design/corrected/main.py --backend hailo --source 0 --gpio --gpio-active-low
```

`--gpio` enables the stack light; `--gpio-active-low` uses the existing low-trigger relay wiring. For a camera-only test, leave both flags out. Pin assignments stay in `vision/pi/stack_lights.py`: BCM17 red, BCM27 yellow and BCM22 green. This connects the existing three lights; it does not add buzzer control.

Close `run.py` and any GPIO test before Production Run. Only one program should own the camera, Hailo and relay pins. This UI needs a desktop display; an ordinary SSH terminal alone will not show it. `--windowed` opens a resizable window. Escape closes the application and releases its hardware.

## Run a box

1. Choose **Configure Batch** to select or create a recipe. The initial **Station Recipe** comes from the active `runtime.json`; its normal target is four of each color.
2. Open **Production Run** and wait for the model/camera to load. The preview shows the yellow counting area and pink left defect line. Counting has not started.
3. Clear the counting area and press **Start Box**. Confirmed cans count once; the existing left-side defect rule subtracts removed cans.
4. Yellow means setup, incomplete counts or waiting for confirmation. Green follows the shared counter's ready decision. Red means over target or review. A matching total alone is not enough for green.
5. **Pause** retains counts and stops analysis while preview continues. Keep cans still during a pause; movement during that time is not inspected. **Undo** reverses the last ledger count action. **Review** clears review flags after checking the actual carton; it does not edit quantities.
6. Press **Finish Box**. The worker freezes counting and sends its final snapshot before history is saved. An exact, ready recipe saves as PASS; mismatched counts save as FAIL; matching counts with pending checks, framing warnings or review save as REVIEW.
7. Position the next carton, clear the area, then press **Start Next Box**. This resets counts and tracking together. Counting never restarts automatically while a result dialog is open.

The existing assumption still applies: a confirmed can in the counting area is treated as packed. The camera does not verify release inside the carton. Stop/Back to Home closes the hardware; an unsaved box with counts prompts before leaving.

## Reuse the station settings

There is no second copy of station settings inside the UI:

| Active file | Settings |
| --- | --- |
| `vision/configs/runtime.json` | Inference, tracking, confirmation, station recipe and `rotate_180`. |
| `vision/configs/colors.json` | HSV ranges and interior/side color sampling. |
| `vision/configs/view.json` | Counting ROI and left defect boundary. |

Rotation is applied before analysis and display. The same configuration overrides are accepted:

```bash
python UI_Design/corrected/main.py --backend hailo --source 0 --gpio --gpio-active-low \
  --config-dir vision/configs/local/station \
  --color-config vision/configs/local/color-profiles/YOUR-SAVED-PROFILE.json
```

Replace the example paths with existing files. Individual `--runtime-config`, `--color-config` and `--view-config` options override `--config-dir`. A calibration profile can contain extra calibration information; the pipeline reads its color settings as it does in `run.py`.

**Configure Batch** changes recipe quantities. Color calibration remains in the existing `run.py --calibrate` screen. Complete it there, close that counter, then start the UI with `--color-config` pointing to the saved profile.

Camera defaults are 1280×720, MJPG, requested 30 FPS, preview 10 FPS, as in the terminal runner. To repeat a working 60 FPS request, add `--camera-fps 60`. Other overrides are `--camera-width`, `--camera-height`, `--camera-format` and `--preview-fps`. Requests do not guarantee delivery or model throughput. On-screen **analyzed FPS** measures the processing loop separately from the requested camera rate.

`station_settings.json` stores camera/preview defaults. Selecting a UI recipe overrides the session's target without rewriting `runtime.json`. Custom recipes stay in ignored `local/recipes.json`.

## How the files connect

```text
Qt Designer pages -> main.py -> worker.py
                                  |
                           vision_runtime.py
                                  |
          vision/pi/yardspi/{camera,backends,pipeline}.py
                                  |
                    vision/common/ processing
                                  |
               shared pack ledger -> stack_lights.py
                                  |
                   snapshots back to Qt widgets
```

| File | Responsibility |
| --- | --- |
| `main.py` | Navigation, buttons, count labels and saving a finished box. Widget changes stay on Qt's main thread. |
| `branding.py` | Shared Yards logo loader. Preserves image proportions and loads the image independently of the launch folder. |
| `worker.py` | Camera/analysis loop and queued Start, Pause, Undo, Review and Finish commands. Owns the camera/model on a separate thread. |
| `vision_runtime.py` | Adapter to the existing Pi modules: config/model validation, rotation, overlay, GPIO calls and session logs. |
| The four `.ui` files | Designer layouts and styling. Some preview/control positions are arranged in `main.py`. |
| `recipe_store.py` | Validate and save named custom recipes. |
| `history_store.py` | Save one completed carton to CSV. |
| `widget.py` | History table, details and CSV export. Matched counts/differences compare quantities, rather than measuring physically defective cans. |
| `station_settings.json` | Camera source, dimensions, format, requested FPS and preview limit. |
| `Yards*Can.webp` | Can pictures on the recipe screen. |
| `yards_logo.png` | Shared logo on Home, Configure Batch, Recipe Selection, Production Run and Inspection History. Header positions are arranged in `main.py` and the history layout in `widget.py`. |
| `tests/test_integration.py` | Hardware-free tests of the adapter, worker and controls. |

For detection changes, edit the shared Pi/common modules or JSON settings instead of adding another detector here. `Pipeline` has one optional session recipe argument; existing `run.py` calls retain their behavior.

The worker analyzes every image it reads while limiting preview updates to 10 FPS. At most one unconsumed preview is queued, so a slow screen cannot build a backlog. Mask drawing stays inside each can rectangle and only runs when a preview is due. Actual throughput still needs to be measured on the Pi.

## Local output and updates

History goes to `UI_Design/corrected/local/inspection_history.csv`. Production sessions save settings, per-frame observations/timing, pack events and a summary under `vision/runs/pi-ui/<session>/`. Images and videos are not recorded by this UI. These output folders are ignored by Git.

Before pulling onto a Pi with local edits, follow [the Pi update instructions](../../vision/pi/UPDATING.md). Preserve campus HSV and rotation changes. Keep the existing `.hef` and its matching identity JSON in `vision/models/`; the UI checks the same model identity as the terminal runner.

## Verification

Local tests use synthetic masks/camera frames. They exercise the real pipeline and ledger, recipe overrides, rotation, logging, GPIO cleanup through a fake output, bounded preview delivery, final-count saving and Qt page loading. They do not verify physical lights or Hailo inference.

With Qt, OpenCV, NumPy, lap and pytest in a test environment:

```bash
python -m pytest UI_Design/corrected/tests vision/tests/test_pi_pipeline.py vision/tests/test_pi_runner.py vision/tests/test_stack_lights.py -q
```

On the Pi, confirm preview orientation/ROI, then run a known 12-pack and one defect removal. Compare displayed counts, history and actual light states. Test Pause/Resume and Start Next Box with the area clear. Keep the session folder if behavior differs from the terminal program.
