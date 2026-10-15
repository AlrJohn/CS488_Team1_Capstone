# Can inspection prototype

We are testing two ways to check a variety pack with Python and OpenCV: count cans as we pick and return them, or inspect a staged group before packing. The first camera test uses one red, one green, and one blue can. Our normal recipe is four of each.

The live counting mode needs a boundary **inside the image**, with room to see a can on both sides. The box can stay off camera. A can disappearing behind a hand or leaving the image does not, by itself, establish a pick.

## Run on this computer

Open this repository folder in VS Code. From its PowerShell terminal, run:

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --source 0 --recipe 1,1,1 --record-session
```

We use `1,1,1` while testing the three sample cans. Change it to `4,4,4` for the twelve-can recipe. Recipes always follow the order **red, green, blue**.

In VS Code's Run and Debug menu, choose **Can inspection - three-can bench test** for the sample cans. The separate **USB camera (4 of each)** profile uses the twelve-can recipe. Both camera profiles save a separate recording for every session. Select the Python interpreter in `..\yolo-env\Scripts\python.exe` if VS Code asks. The demo can run without a camera:

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --demo
```

The demo uses artificial colored shapes. It exercises the counting behavior; it does not measure accuracy on cans.

## Set up the camera

The live camera starts paused so we can adjust the view before counting.

1. Aim at the colored labels with a plain background and enough room to see cans move out of the lanes. Keep the camera fixed. Avoid reflections that wash out the label color.
2. Press **O** and drag a rectangle around the lane and a visible exit area. Press Enter to accept the inspection area.
3. Press **B**, click two points along the counting boundary, then click on the exit side. The line extends across the inspection area. The gray lines mark a small band where movement does not change the count.
4. Press **C** to calibrate. Press **1**, **2**, or **3** to choose red, green, or blue. Click the colored part of that can's label. Adjust the hue width and minimum saturation/brightness sliders until the preview keeps the label and excludes the background. Sample each color.
5. While calibrating, press **A** and select the full label area of one can, including its white logo panel, to estimate its size. Only pixels matching the selected color contribute to the measurement. The area limits apply to all three colors, so check that each can produces one box rather than several small boxes. Press **C** to save.
6. Put the cans on the lane side, press **P**, and move one can at a time across the line. Let it remain visible on each side for several frames. Try a return as well as a pick.

Saved calibration goes to `configs/local.json`. Recordings, snapshots, event logs, and settings for each session go to `runs/`. Both locations stay local. Automatic calibration loading keeps the default recipe at `4,4,4`; specify `--recipe 1,1,1` for the bench test. An explicit `--config` uses that file's recipe unless we override it.

The white Yards logo can split a label into separate colored regions. In our first stationary camera check, the red label produced a large region and a smaller strip. Raising the minimum area excluded the strip while retaining one region for each sample can. This depends on the view and visible label area; check all three colors again after changing the camera position or rotating the cans. The `min_area` and `max_area` settings are fractions of the full image area. If no area threshold keeps one region per can, we need to change the view or improve object detection before trusting the count.

Our live test also uses an optional transfer band, shown by two cyan lines around the white counting line. New tracks start inside that band. A can must be visible on the lane side before crossing and remain visible on the exit side for confirmation. An observed departure past either outer edge ends that track without changing the count. This avoids tracking waiting inventory and already-counted cans far beyond the crossing. The color masks still use the full inspection area, so entering the band does not clip the label. The `transfer_band` JSON setting holds the lane-side and exit-side widths in normalized image coordinates; `null` tracks throughout the inspection area. Make the band wide enough to observe each side for several frames. Staged mode uses the full inspection area and ignores this band.

During red calibration, move an empty hand through the preview as well. Some skin and shadow pixels can fall within a broad red range. Adjust hue width and minimum saturation while checking that the red label remains visible. This does not provide a general hand detector.

## Camera orientation

For an upside-down camera, add `--rotate-180`. The program rotates the image before detection, calibration, display, snapshots, and recording. It also rotates the saved inspection area, boundary, and exit point into the corrected view, keeping the same physical pick/return direction. Use `--no-rotate-180` to turn the correction off for a run. To keep an override in the local calibration, open C and save it with C again.

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --source 0 --recipe 1,1,1 --rotate-180 --record-session
```

Recordings use the displayed orientation and include an `.avi.orientation.json` file. Keep that file with the video so replay applies the correction only once. Earlier recordings without this file are treated as the original camera view.

## Controls

Click the inspection window before using the keyboard. Use lowercase letters.

| Key | Action |
|---|---|
| P | Start or pause counting. Resuming an active batch requires a manual check. |
| O | Select the inspection area while the batch is empty. |
| B | Set the boundary and exit side while the batch is empty. Esc cancels. |
| C | Open calibration, or save and close it. |
| 1 / 2 / 3 | Select red / green / blue during calibration. |
| Mouse click | Sample the selected color from the image during calibration. |
| A | Estimate one can's colored area during calibration. |
| M | Show or hide the combined color masks. |
| S | Save the current raw frame. |
| Space | Complete a READY batch and begin the next one. Clear the transfer area first. |
| N twice | Discard/reset the current batch and pause for repositioning. |
| V twice | Acknowledge a review after manually verifying all displayed counts. |
| Q / Esc | Quit, unless Esc is canceling boundary placement. |

**READY means the observed net count matches the recipe.** It does not prove that the cans reached the box. We still need to confirm each carton before starting the next batch. This prototype displays status on screen; stack-light and alarm hardware are not connected yet.

If tracking becomes ambiguous, the display changes to **REVIEW NEEDED**. Check the carton and the displayed counts. If the counts are correct, press V twice to acknowledge that check. If they are wrong, press N twice and recount. Acknowledging a review does not change the counts.

## Record and replay a test

Use `--record-session` to save each trial in its own timestamped folder. It writes `camera.avi` alongside the session's logs, and the terminal prints its location:

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --source 0 --recipe 1,1,1 --record-session
```

We can also choose a filename with `--record`. Existing recordings are protected, so use a new filename for each trial:

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --source 0 --recipe 1,1,1 --record vision\runs\trial-01.avi
..\yolo-env\Scripts\python.exe vision\run.py --source vision\runs\trial-01.avi --config vision\configs\local.json --recipe 1,1,1 --headless
```

The AVI contains unannotated frames in the displayed orientation. Each session saves `events.csv`, `settings.json`, and `summary.json`. Recorded sessions also save `frame_times.csv`, with the actual timestamp, batch, and whether counting was active for each frame. The event log includes frame indices and pause/resume actions so we can compare picks and returns with the footage. AVI playback uses the camera's reported frame rate, which can differ from the actual capture rate; use the frame timestamps when measuring timing. If we move cans while the live program is paused for setup, replay that recording only after trimming those setup frames or account for them when comparing events. Keep the recording, orientation file, frame times, event log, and settings together.

To try the staged alternative:

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --source 0 --mode staged --recipe 1,1,1
```

In staged mode, the inspection area should contain only the selected cans. We remove our hands and let the image settle before accepting a result. The boundary is used only in live pick counting.

## Camera and installation checks

List available camera indices:

```powershell
..\yolo-env\Scripts\python.exe vision\run.py --list-cameras
```

If camera 0 is not the intended camera, try `--source 1`. Automatic setup tries DirectShow, then Media Foundation, then OpenCV's default backend on Windows. If the camera still will not open, close other camera applications. We can also select a backend explicitly with `--backend msmf`. Windows camera permissions must allow desktop applications.

We check startup frames as well as whether the backend opens. In our Windows test, one background launch returned a constant gray image even though the backend reported success. The program now rejects that feed and stops if a live feed becomes blank. If this happens, run from the VS Code terminal with `--backend dshow`. The constant-frame check does not measure whether lighting is good enough for color recognition.

On another computer, create an environment inside the repository and install the dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r vision\requirements.txt
.\.venv\Scripts\python.exe vision\run.py --source 0 --recipe 1,1,1
```

Use the desktop `opencv-python` package, because calibration needs windows and sliders. Select that computer's environment in VS Code.

## Testing and limits

Run the automated tests from the repository root:

```powershell
..\yolo-env\Scripts\python.exe -m unittest discover -s vision -p 'test_*.py' -v
```

These tests cover color masks, boundary crossings, returns, jitter, several tracking failures, recipes, and staged settling. They use synthetic images and detections. Our [camera test plan](docs/testing.md) covers the real cans, hands, lighting, speed, and grouped picks we still need to measure.

Color alone cannot establish can identity or prove that a can reached the carton. Touching cans of the same color can merge into one region, and label artwork can split one can into several regions. A completely hidden pick can be missed without a warning. We need to measure these cases before relying on the count at Yards. Individual lane-purity checks are also still to be implemented.

The [approach notes](docs/approach.md) explain why we are starting with visible crossings and when a different camera angle or staged inspection would be needed. [default.json](configs/default.json) and [bench.json](configs/bench.json) provide example settings. Our earlier [YOLO Windows setup notes](reference/YOLO%20Windows%20Connection%20Next%20Steps.docx) remain available as a reference.
