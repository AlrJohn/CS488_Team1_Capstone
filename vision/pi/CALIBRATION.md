# Live color setup on the Pi

Color setup uses the current can model to find masks, then fits session HSV ranges from labeled pixels. It changes hue, tolerance, saturation minimum and brightness minimum. It keeps the ordinary check, side fallback, tracking, counting and model weights as configured. It does not train or compile a model.

Run from the repository root on the Pi desktop:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 --calibrate
```

If the station uses a local configuration folder, keep that selection:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --config-dir vision/configs/local/pi --calibrate
```

The second command requires that folder's runtime, color and view JSON files to exist. The setup uses the same camera format, resolution, source orientation and ROI as the counter. The count area must exclude waiting stock. Preserve the campus-only edits before the first repository update; see [UPDATING.md](UPDATING.md).

## Collect the three colors

1. The window opens, then the camera warms up and runs a short delivery measurement without model inference or image saving. This normally takes four seconds. The measured camera rate and setup processing rate are shown separately. Inspect the feed for blur and glare. Camera exposure and white balance are not changed or locked automatically; keep the camera and lighting steady.
2. Show exactly one can inside the yellow area. Other stock can remain outside it. Select **Red**, **Green** or **Blue** with the buttons or keys **1**, **2** and **3**.
3. Click a visibly colored part of that can. Avoid the white printing, silver rim and hand. A click outside its detected mask or on a neutral/dark patch is rejected. If there is no can mask, reposition the can; color fitting cannot create a missing model detection.
4. Press **Collect** or **C**. Turn the can slowly to expose different label orientations and colored sides while keeping it visible. The default is 30 accepted, spaced observations, generally taking at least 3.5 seconds. Sparse or unusable color samples are reported; collection times out after 20 seconds rather than waiting indefinitely. Completed samples stay in memory until this setup ends.
5. Repeat for the other two colors, then press **Fit** or **F**.

Fitting uses the clicked hue to select actual colored pixels within each mask. White printing and unrelated hues are excluded. Each frame contributes a bounded number of pixels so one close view does not dominate. The fitter handles red's hue wrap, finds compact ranges and prevents overlap among the three colors. A large unexpected hue shift or inseparable samples requires recollection instead of unlimited widening.

The screen shows **Original** and **Proposed** color results for the current can. Proposed means the complete shared color sampler, including its configured ordinary and side checks, is using the fitted ranges.

## Verify fresh views, then test counting

1. Select a color and show that can again. Use new turns/movements that were not part of collection. Keep the can inside the yellow area for this color check.
2. Press **Verify** or **V**. The default sequence has 24 spaced observations. Unknown colors and missing/ambiguous can detections are counted as failures, not discarded. By default at least 90% must match the selected color and there must be no wrong known-color observations. With 24 observations, at least 22 must be correct.
3. Repeat for all three colors. A failed color can be verified again with the same profile. **Recollect** or **T** clears the selected color's samples and invalidates the fitted profile and all verification results. Collect that color again, Fit, then repeat all three verifications. Completed failed verification attempts remain in the saved metrics if a later attempt passes.
4. After all three pass, press **Save & Test** or **S**. A new profile is saved and the normal counter opens using it, with the camera and model already loaded.
5. Clear the count area, begin with an empty carton and press **P**. Perform ordinary singles, pairs and full-pack trials, including white labels facing the camera. Calibration verification checks color continuity while the can is visible; it does not establish fast group counting or production reliability.

**Cancel**, **Q**, Escape or the window close button exits without starting pack counting or writing a new profile. Pack counts are never advanced by calibration samples. The GPIO status remains in setup rather than turning green for a calibration pass.

## Saved profiles and controls

Profiles are saved under ignored `vision/configs/local/color-profiles/` with unique timestamped names. Existing files and the published `colors.json` are not overwritten. Each profile includes the fitted ranges, effective ordinary/side settings, camera mode/delivery results, fitting metrics and verification attempts. Pixel arrays and camera images are not saved by this screen. Normal recording flags apply to the counter after setup, not to the collection stage.

The selected path is printed in the terminal and appears in the counter's metadata under `configurations.colors.path`. To reuse it later:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 \
  --config-dir vision/configs/local/pi \
  --color-config vision/configs/local/color-profiles/colors-YOUR-SAVED-NAME.json
```

Replace the final filename with the actual saved path. A calibration is not automatically selected on a later launch. Recalibrate when the lighting or camera controls change. The profile records the Pi source orientation; review rotation separately before reusing it with the Windows program.

Capture and fitting controls are in `vision/configs/calibration.json`. A station copy can be selected with `--calibration-config PATH`; `--calibration-output FOLDER` chooses another profile directory. Change controls in JSON and restart setup.

| Controls | Purpose |
| --- | --- |
| `warmup_seconds`, `probe_seconds` | Camera settling and model-free delivery measurement |
| `collection_frames`, `verification_frames` | Required observations per color in each separate phase |
| `sample_interval_seconds`, `collection_timeout_seconds` | Observation spacing and bounded collection time |
| `min_pixels_per_frame`, `max_pixels_per_frame` | Usable color evidence and bounded per-frame sample size |
| `seed_radius`, `seed_hue_window`, `seed_saturation_fraction` | Clicked-patch size and selection of related colored pixels |
| `saturation_floor`, `value_floor` | Lowest allowed saturation/brightness for fitting pixels and fitted ranges |
| `max_hue_shift` | Largest permitted center shift from the input profile |
| `min_hue_tolerance`, `max_hue_tolerance`, `hue_margin` | Hue-range bounds and margin; color separation may impose a tighter cap |
| `lower_percentile`, `hue_percentile`, `sv_margin` | Robust range fitting from collected pixel distributions |
| `minimum_fit_recall` | Minimum fraction of selected collection pixels retained by a fitted range |
| `minimum_verification_accuracy`, `maximum_wrong_frames` | Fresh verification pass requirements |

## Code map

| File | Responsibility |
| --- | --- |
| `pi/run.py` | Validates the calibration option and transfers the saved profile into a fresh counter |
| `pi/yardspi/calibration.py` | Live screen, buttons, camera/model loop and separate collection/verification state |
| `common/color_calibration.py` | Seed selection, bounded pixel collection, range fitting, verification totals and safe profile creation |
| `common/color_analysis.py` | The unchanged shared classifier used to evaluate proposed ranges |
| `configs/calibration.json` | Adjustable setup controls; no Hailo recompilation needed |

The extra fitting, original/proposed comparison and UI work runs only in setup. The normal counter resumes its usual path afterward. Software tests use simulated camera/model inputs; the first Pi/Hailo camera trial is still required.
