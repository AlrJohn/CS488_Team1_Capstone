> Historical baseline note. For the current implementation, see the [vision overview](../../../README.md) and [development history](../../../docs/development-history.md).

# Camera test plan

We start with the three sample cans and a `1,1,1` recipe. We keep the camera fixed, calibrate the labels, and record each trial. After that works, we need twelve physical cans to validate the `4,4,4` recipe and normal packing motions.

Before each trial, write down the expected pick/return sequence. Afterward, compare that sequence with `events.csv`, the recording, and a manual count. Keep the session's `settings.json` with the footage so we can repeat the same processing settings. Use a new recording filename each time.

## Basic counting

| Trial | Expected behavior |
|---|---|
| Leave three cans still on the lane side for ten seconds | No picks and no READY result. |
| Pick red, then green, then blue across the boundary | One event per can; READY after the final count settles. |
| Hold a can near the line and move it slightly back and forth | No repeated events from movement inside the neutral band. |
| Pick a can, then return it while it remains visible | One pick and one return; net zero for that can. |
| Pick a can, let it leave the image, then bring it back through the exit strip | Return subtracts from that color's current total. |
| Bring in a return when that color's count is zero | Count stays zero and the program requests review. |
| Stop with one color missing | No READY result. |
| Pick more than the recipe requires | TOO MANY CANS, or REVIEW NEEDED if tracking became ambiguous. |
| Complete a carton, clear the exit area, and press Space | The next batch starts at zero. |

## Visibility and lighting

| Condition | What we check |
|---|---|
| Move an empty hand across the line | No pick. Repeat with sleeves and gloves used at the station. |
| Partly cover a label while picking | Does the same can remain tracked, and is there exactly one event? |
| Fully cover a can during the transfer | Record misses and false events even if no warning appears. This case may require a different view. |
| Move two separated cans together | Compare individual tracks and counts with the actual two cans. |
| Move two touching cans of the same color | Check for merged regions and undercounting. A warning is not guaranteed if they were already merged when first seen. |
| Rotate each can | Check whether artwork splits the label into multiple candidates or changes its detected color. |
| Add glare, shadows, and brighter/dimmer light | Check each color separately and note when calibration needs to change. |
| Put colored clothing or another colored object near the area | Check for false candidates and false picks. Tighten the inspection area where practical. |
| Repeat slow, normal, and fast picks | Check whether each side stays visible long enough to establish the crossing. |
| Pause during a batch and move a can | Resuming requires manual review. |
| Interrupt camera capture | The program stops counting and does not retain an approval. |

For staged mode, repeat the lighting and label-rotation trials with all cans separated in the inspection area. Move a hand through the area and confirm that the program waits for the image to settle before accepting the visible mix.

## Results to record

Record the trial name, camera position, lighting, recipe, expected events, observed events, manual final count, review messages, and session path. Count missed picks, extra picks, missed returns, extra returns, and any incorrect READY result. Also record how often review is needed and how long a result takes after the final movement.

Calculate event precision as correct logged events divided by all logged events, and event recall as correctly logged events divided by all actual events. Report picks and returns separately and match both direction and color when deciding whether an event is correct. Keep results separated by lighting, speed, and occlusion condition so an easy trial does not hide a difficult one.

We need to agree on acceptable error rates, delay, and review frequency with Yards before relying on this for production. Passing synthetic tests or a short camera trial does not establish those rates.

## Initial three-can trial, October 14, 2026

Our first recording showed why a stationary color check is not enough. Some cans left the bottom of the image during pickup, hands covered waiting inventory, and parts of the hand appeared in the red mask. We also saw one blue label produce multiple regions as it rotated near the image edge.

The second attempt contained visible blue, red, and green picks followed by a red return. The original processing reached the correct final counts of red 0, green 1, and blue 1, but required review. We tightened red calibration and added a transfer band so tracking focuses on the crossing. Replaying that same segment then produced the four expected events without review warnings. This recording was used for tuning; we still need a fresh trial to validate the changes independently. Fully hidden transfers remain outside what this camera view can establish.
