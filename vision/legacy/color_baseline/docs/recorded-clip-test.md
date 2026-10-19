> Historical baseline note. For the current implementation, see the [vision overview](../../../README.md) and [development history](../../../docs/development-history.md).

# Yards packaging recording: first OpenCV check

October 15, 2026

We tested the supplied 58-second packaging recording with the existing HSV detection, contour filtering, tracking, and counting code. After separate calibration, the program detects colored parts of red, green, and blue labels. It does not reliably establish the number of cans in a grouped pick. These failures justify investigating individual-can detection and segmentation on this footage now, alongside the physical mockup.

## Recording and method

The source is `vision/Yards_Packaging_Video/1792096201731/screen_1792096201736.mp4`, a 620 by 1080 screen recording. OpenCV decoded 1,651 frames. The source reports an average frame rate of about 28.48 fps; we used the decoded presentation timestamps rather than assuming every frame had the same interval. The exported viewing copy has 1,740 frames at 30 fps and a duration of 58 seconds.

The camera moves during the recording, and waiting inventory, printed packaging, the employee's shirt, and hands share the view with the selected cans. These conditions differ from our fixed-camera bench test. This recording cannot establish the timing or accuracy of a production installation.

We compared two settings files with the same inspection geometry:

- **Baseline:** the generic default color ranges and area limits, with a recording-specific inspection area and counting boundary.
- **Clip calibration:** color ranges sampled from visible stock labels, smaller candidate-area limits for this view, and the same inspection geometry. The current webcam settings were preserved; their file hash was unchanged after the experiment.

The experimental [yards-recording.json](../configs/yards-recording.json) contains the clip calibration. It is not a replacement for the webcam calibration. The detection, tracking, counting, and pipeline modules were unchanged for this experiment. No model was trained.

| Setting | Clip calibration |
|---|---|
| Red hue center / tolerance; minimum saturation / brightness | 7 / 11; 110 / 55 |
| Green hue center / tolerance; minimum saturation / brightness | 43 / 12; 75 / 55 |
| Blue hue center / tolerance; minimum saturation / brightness | 108 / 14; 65 / 55 |
| Candidate colored area as a fraction of the full image | 0.00045 to 0.018 |
| Morphology kernel | 3 pixels |
| Inspection area: x, y, width, height | 0.12, 0.13, 0.87, 0.29 |
| Horizontal counting boundary | y = 0.265; exit above the line |

Hue uses OpenCV's 0–179 scale. Saturation and brightness use 0–255. This boundary is an experimental choice for the recording, not a validated station layout. Camera movement changes where the physical pickup area falls relative to the fixed line.

## What the images show

At sequential decoded frame 425, around 16.87 seconds, the four lifted blue cans produce two blue candidate regions in the calibrated image. Another blue candidate belongs to printed packaging at the right edge. Detecting blue pixels therefore does not establish four separate cans.

At sequential decoded frame 605, around 22.87 seconds, the red cans held together form merged candidate regions. The red shirt also produces candidates. A threshold that accepts the label color can accept unrelated objects with similar color.

At sequential decoded frame 667, around 24.93 seconds, some green label portions are detected, but other visible strips on the lifted cans are missed or are too small to become candidates. Waiting green stock is detected too. A total of four green regions anywhere in the inspection area would not mean the four selected cans were correctly identified.

These frames were used to inspect and tune this recording. They are development examples, not an independent validation set. A brief check with less morphology and a smaller area threshold produced additional regions and fragments; it did not establish a reliable physical can count.

## Counting results

| Diagnostic | Baseline | Clip calibration |
|---|---:|---:|
| Frames processed | 1,651 | 1,651 |
| Frames with REVIEW NEEDED | 1,611 | 1,622 |
| Unique review messages | 55 | 165 |
| Logged picks: red / green / blue | 0 / 0 / 0 | 1 / 2 / 0 |
| Logged returns: red / green / blue | 0 / 0 / 0 | 1 / 0 / 0 |
| Final unverified net count: red / green / blue | 0 / 0 / 0 | 0 / 2 / 0 |

These totals are continuous diagnostic output. We did not reset the counter between cartons, and they must not be described as carton contents or an event-accuracy measurement. Review messages include track IDs, so 165 unique messages do not represent 165 independently verified errors. Neither run reached READY.

The calibrated tracker logged a red return around 28.53 seconds while the visible action was a green group lift. It also logged only one green pick around 24.90 seconds during the grouped green transfer. The warnings include merged tracks, ambiguous matches, lost tracks, and unconfirmed origins. Recovering more colored label pixels did not make the counter reliable.

## Green transfer and processing time

We examined the 26–30 second section more closely. The green transfer between 28.40 and 28.80 seconds spans 13 decoded frames. The cans are observable across multiple images, although hand coverage and the visibility of each can change during the movement. The offline run processed all these frames, so its counting failure cannot be explained by dropping them to keep up with playback.

We also timed the existing calibrated `Pipeline.process` on the desktop computer, replaying the preceding footage to retain the same tracking history. Across the 118 frames from 26 through 30 seconds, processing averaged 15.13 milliseconds per frame; the median was 15.04 milliseconds, the 95th percentile was 16.41 milliseconds, and the maximum was 16.98 milliseconds in this run. These measurements include color detection, contour filtering, tracking, and counting. They exclude camera capture, video decoding, drawing, display, and encoding, and they do not measure Raspberry Pi performance or complete response latency.

At approximately 30 incoming frames per second, the average interval is about 33 milliseconds. The current processing stage can keep pace with that input on the tested desktop, while its detections remain unreliable. A future can detector would need its own speed and accuracy measurements. The recorded failures support testing a different representation of individual cans, rather than assuming that faster execution or color-threshold tuning alone will resolve grouped picks.

## What we will test next

Our wooden mockup should reproduce four-can transfers, with two cans in each hand, using a fixed camera and consistent lighting. We need to keep the individual can bodies distinguishable and establish a visible path from pickup to the receiving carton. We should evaluate a clearer background and zone placement, since the hand positions overlap the shirt in this view.

The visible merging and fragmentation in this recording already justify a detector change. Our [research and next experiment](../../../docs/history/instance-detection-20261015.md) propose an offline prompted segmentation trial, with custom can-model fine-tuning if needed. The mockup is a source of controlled installation tests and independent footage, not a prerequisite for beginning that investigation. Better tracking may help association failures, but it cannot verify a completely hidden transfer. No learned model has been tested or trained on our footage yet.

## Reproduce the experiment

The helper calls our existing `Pipeline` and exports candidate boxes, HSV masks, diagnostic counts, and review messages. Its video displays the upper part of this portrait recording so the transfer area is readable; detection still uses the full-frame inspection area.

From the repository terminal:

```powershell
python vision\legacy\color_baseline\evaluate_clip.py --source vision\Yards_Packaging_Video\1792096201731\screen_1792096201736.mp4 --config vision\legacy\color_baseline\configs\yards-recording.json --label "Clip-specific calibration" --snapshots 16.87,22.87,24.93
```

Each run writes to a new folder under `vision/runs/`, including `analysis.mp4`, selected PNG images, detection and event CSVs, settings, and a summary. `--no-video` skips encoding when we only need logs or selected images. `--start` and `--end` select a source interval in seconds. Presentation export requires the optional dependencies in `requirements-presentation.txt`.

The first experiment's local folder is `vision/runs/yards-clip-20261015-163138/`. It contains `baseline/` and `calibrated/`, with a smaller H.264 viewing copy at `calibrated/analysis-view.mp4`. The `blue-comparison.png`, `red-comparison.png`, and `green-comparison.png` images compare default thresholds with clip calibration at the same source frames. Local recordings and generated outputs remain under the ignored runs folder.
