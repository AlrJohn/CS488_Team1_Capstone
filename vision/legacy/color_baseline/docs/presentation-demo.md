> Historical baseline note. For the current implementation, see the [vision overview](../../../README.md) and [development history](../../../docs/development-history.md).

# Record the three-can presentation demo

This demonstration shows our current color detection and visible pick/return counting with one red, one green, and one blue can. It uses a `1,1,1` recipe. The lane mockup, paired-pick testing, and full twelve-pack validation are planned next steps in our [prototype direction](../../../../docs/design/prototype-direction.md).

## Start the recorder

The presentation encoder is installed in this computer's `yolo-env`. On another computer, install it with the Python interpreter used to run the program:

```powershell
python -m pip install -r vision\legacy\color_baseline\requirements-presentation.txt
```

Open the repository in VS Code. In Run and Debug, select **Can inspection - presentation recording (3 cans)** and press F5. We can also run this from the repository's terminal:

```powershell
python vision\legacy\color_baseline\run.py --source 0 --backend dshow --recipe 1,1,1 --record-session --record-presentation
```

The camera starts paused. Check that the image is upright and that the saved boundary puts the exit on the intended side. If necessary, use B to place the boundary and choose the exit side, then C to check the color calibration. Each label should produce one detection box. Leave enough visible space on both sides for a confirmed crossing.

The presentation clip starts with the first active counting frame after P. Setup while paused is excluded. Once the clip starts, later pauses and review messages remain in the clip. Q ends the session and finishes the MP4 file.

## A short sequence to show

1. Put all three cans on the lane side with their labels visible. Click the inspection window, press P, and wait about two seconds so the recording shows the initial zero counts.
2. Move red across the boundary into the exit area. Keep its label visible through the crossing. The red count should become 1. Hold it briefly in the visible exit area and press S to capture its detection box and the count, then carry it out of view.
3. Repeat with green, then blue, one at a time. The counts should reach `1,1,1`. Keep blue visible on the confirmed exit side for the next image.
4. Wait for READY. Press S for an image with the detection view and count panel, leave the result visible for about two seconds, then carry blue out of view.
5. To demonstrate returns, bring red back through the exit area and across the boundary to the lane side. The counts should become `0,1,1` and the status should leave READY. Press S for another image.
6. Pick red again, wait for READY, and press S. Leave the final result visible for about two seconds, then press Q.

Use ordinary, visible movements and check the actual counts against the display. If a review appears or an event is wrong, keep that trial for testing and record a fresh session after checking the setup. A manual review acknowledgement is not an automatic recognition result.

## Find the presentation files

The terminal prints the session folder under `vision/runs/`. Every run has a new timestamped folder, so earlier trials remain available.

| File | Use |
|---|---|
| `presentation.mp4` | H.264 video of the camera view, detection boxes, boundary guides, live counts, and status panel. Use this in the presentation. |
| `slide-*.png` | Annotated images saved with S. Use these as slide images. |
| `camera.avi` | Unannotated camera frames for analysis and replay. |
| `frame-*.jpg` | Unannotated images saved with S. |
| `events.csv`, `frame_times.csv`, `settings.json`, `summary.json` | Counts, timestamps, calibration, and results for checking the trial. |

The MP4 has no audio. It samples the displayed views at 30 frames per second using the session timestamps, so a mismatch between the camera's reported frame rate and its actual throughput does not speed up or slow down the presentation. This video export does not increase the rate of camera observations. If counting never starts, no presentation video is created.

Finish with Q before opening the video, and preview it before adding it to the presentation. Select `presentation.mp4` as the video and the `slide-*.png` files as images. These recordings stay local under the ignored `vision/runs/` folder.

Our presentation should describe the clip as a three-can prototype demonstration. It establishes the behavior visible in that trial; it does not establish paired-pick accuracy, physical carton placement, or production-speed performance. The `--demo` option uses synthetic shapes and should not be presented as camera test footage.
