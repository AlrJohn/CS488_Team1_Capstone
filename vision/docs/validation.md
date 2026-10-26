# Validation and timing record

Status as of October 19, 2026. These results describe controlled development checks. They do not establish a production error rate or verify physical placement in the carton. Raw footage, trial identifiers and per-frame evidence stay in private runs.

## Repository organization checks

| Check | Result | Meaning |
| --- | --- | --- |
| Shared V4 observer/counter versus eight reference sequences | 2,697 frames: zero identity/count/review-state mismatches; ordered count events equal | Moving to shared modules preserved the reference behavior, including known errors |
| Current synthetic runtime tests | 9 passed | Core color/mask, identity, admission, defect and ledger behavior |
| Earlier color-only prototype tests | 47 passed after relocation | The historical implementation and its recording/demo behavior remain available |
| Original versus published Windows GPU adapter/checkpoint | Eight selected images: identical masks, boxes and color labels | The extracted PC adapter retained the original predictions on these images |
| Portable ONNX export helper | Export completed; three four-can color images matched the PC model, with identical decoded masks | The publication checkpoint exports through the documented raw-head contract |
| Reorganized Pi source on the real Hailo-8 | All 198 images of the saved full-pack trial replayed with actual inference: zero per-frame identity/color/count/status mismatches; final 4/4/4, no reviews | The source layout and shared imports work on ARM64/Hailo, without replacing the working deployment |

The full-sequence comparison uses saved detections for the observer/counter check. It is not another neural-network accuracy evaluation. The Pi replay performs actual network inference on saved raw frames with their original timestamps; its processing speed is not live camera FPS.

The PC publication checkpoint removes six embedded local training-path strings. All 421 tensor archive entries remain byte-for-byte identical to the original. The published artifact has a new file hash; its sidecar preserves the original source identity used for the unchanged HEF.

The Windows counter also reached model warmup/camera-open startup from a clean source copy with no private experiment folders available. The camera was deliberately not opened during this check. Fine-tuning and Hailo recompilation were not rerun during repository organization.

## Conversion evidence

The floating-point ONNX path preserved the original eight sequence counts. The shipped INT8 model changed one known sequence from 4 red / 4 green / 4 blue to 4 / 4 / 5. Investigation traced a confidence drop below the 0.50 cutoff, followed by an identity switch and duplicate admission. A same-image duplicate-mask filter does not resolve that across-frame identity failure. It remains open.

Four selected images on the actual HAT matched the saved quantized emulator's color quantities. That verified the hardware adapter and selected outputs, not complete production correctness. Calibration used training images only; neither hardware check footage nor the reference test recordings were added to the calibration set during this work.

## Controlled live Pi trials

The first trial expected 3 red / 2 green / 2 blue under the admission rules, including an initial red that was put back without a left-defect crossing. It recorded 3 / 3 / 2 and raised a color/identity review during a blue pickup. The cans were lifted partly beyond the top of the image.

The next trial picked a full twelve-pack as six pairs: red, red, blue, blue, green, green. All intermediate increments matched the observed groups and the final count was **4 / 4 / 4**, with twelve admissions and no count-review events. There were two same-image duplicate-mask suppressions, and brief lower-edge framing warnings during entry/exit. The earlier failure did not recur in this trial; it is still a known case.

Four-at-once pickups, observed left-defect subtraction on hardware, multiple operators, production lighting and repeated normal-speed packs still need dedicated trials. The absence of an error in one pack does not establish reliability across those conditions.

## Timing measurements

| Mode | Analyzed FPS | Median complete analysis | Median Hailo inference |
| --- | ---: | ---: | ---: |
| Historical RTX 4080 laptop recorded baseline | about 18 | Timing stages differ from Pi | CUDA rather than Hailo |
| Pi 5 / Hailo-8, GUI and JPEG preview saving | 10.02 | 54.45 ms | 11.52 ms |
| Pi 5 / Hailo-8, GUI, JPEG and lossless PNG saving | 6.31 | 52.17 ms | 8.41 ms |

The Pi trial with both image formats had a 152.95 ms median complete loop and a 208.55 ms 95th percentile. Median camera-read-through-count time was 64.32 ms. First matching-color observation through admission was 352–517 ms in that trial; that is a log-based confirmation interval, not time since the physical pickup began.

Camera-only MJPEG capture delivered 14.99 FPS in the probe. The default uncompressed YUYV mode delivered about 5 FPS; explicit MJPEG corrected that capture bottleneck. The requested/reported camera setting was 30 FPS. Actual delivery and analyzed throughput are separate measurements.

These are different motions and recording workloads, not an isolated comparison of PNG cost. Sensor exposure, existing driver queue age and physical display delay were not measured. Sustained four-can load and live operation without image saving remain unmeasured. Do not present Hailo inference time, emulator speed or requested camera FPS as complete system performance.

## Repository runtime update on October 22

The PC checkout was brought forward to GitHub commits `fe4edee` and `2ae8232`, retaining two-of-five color confirmation and the wider red range. The previously local GPIO implementation is included with the current source. Additional campus Python/configuration edits exist only on the Pi and have not been compared because it was unreachable at its last known address.

Color processing now crops each mask before erosion and HSV conversion, and votes only on selected pixels. On this Windows CPU, a synthetic 1280×720 image with four 100×270 masks measured median color-stage time of 72.1 ms before and 5.3 ms after, across 60 alternating comparisons after warmup. Labels and all pixel diagnostics matched. This is about 13.6 times faster for that stage and workload; it is not a Pi measurement, model benchmark or end-to-end speed claim.

The Pi preview has a separate 10 FPS drawing limit, while analysis remains active on every read image. Explicit preview image saving still keeps every analyzed frame. The new camera-only probe measures delivery without inference, GUI, GPIO or image saving. The source path and actual loaded settings are recorded in run metadata. These changes still require live camera/Hailo throughput tests on the Pi.

All 36 software tests passed in the PC development environment and in a separate Windows environment using the Pi dependency versions: NumPy 1.26.4, OpenCV 4.11.0.86 and lap 0.5.12. They also passed from a copy containing only public source and selected model files, without private experiment folders. The model identity checks passed. These checks cover simulated delivery, color equivalence, counting, GPIO decisions and preview saving; they do not execute the ARM driver, physical pins or Hailo hardware.

## White-label side fallback on October 22

The campus report identified a separate color failure: white front printing can leave narrow colored strips near the mask edges. A new fallback checks the left and right body bands after an insufficient interior result. This intentionally changes some unknown decisions into known colors. The earlier cropped-calculation equivalence check remains applicable with the fallback disabled; it is not an assertion that every decision is unchanged when the new fallback is enabled.

Synthetic cases recovered red, green and blue from narrow strips on both sides and recovered a color from one side with the opposite side white. Conflicting sides, small colored patches, color outside the mask, low saturation and rim-only color remained unknown. A Pi pipeline test confirmed that recovered colors still require two observed frames before admission. All 48 software tests passed in both Windows environments described above, and model identity checks passed. No trained weights or HEF were changed.

A separate 60-iteration alternating benchmark used four 100×270 masks in a 1280×720 synthetic image with NumPy 1.26.4 and OpenCV 4.11.0.86. Solid-label color processing measured 4.8 ms before and 4.7 ms after this fallback addition. White labels with narrow side strips measured 4.7 ms before, returning four unknowns, and 10.1 ms after, returning the four intended colors. This is a Windows CPU color-stage comparison without model inference, camera capture, drawing or saving. It shows the extra work when fallback is needed; the earlier approximately 5 ms crop benchmark is not a promise for every color case.

Actual label artwork, hands, tilted cans, campus lighting and Pi throughput remain untested for this fallback. The current left/right bands assume an approximately upright can. The campus-only calibration and Python changes still need retrieval before the Pi is updated.

The ordinary color evidence limits were subsequently made configurable under `interior_sampling` in the same color JSON. Published values remain 25 pixels, 0.1 coverage and 0.6 dominance, with compatibility defaults for older profiles. All 54 software tests passed in both Windows environments, including separate acceptance checks for each JSON limit, invalid-value checks and a Pi pipeline count check. This moves configuration into the profile without changing the shipped thresholds or trained model.

## Live Pi color setup on October 22

The Pi runner now has `--calibrate` for collecting labeled can pixels, fitting session HSV ranges and verifying fresh examples before normal counting. It reuses the open camera/model and creates a new ignored profile rather than overwriting station settings. The ordinary/side evidence limits and counting rules are retained, and old profiles receive explicit effective color limits in the saved file. Calibration does not feed observations into the carton ledger. Save & Test starts the normal counter in setup; P is required to count.

All 70 software tests passed in both Windows environments described above, and the selected model identity checks passed. New checks include supervised pixel selection, red wrap, distinct color ranges, unchanged evidence limits, failed verification observations, exclusive profile creation, a simulated mouse/keyboard setup sequence, setup cancellation and the counter's actual use of the selected profile. The collection, verification and ready screens were rendered and visually inspected. These checks use simulated cameras/models and do not execute a Pi camera, HailoRT or a physical touchscreen. The live Pi trial and campus-only source/configuration comparison remain pending.

The setup's default 30 collection views and 24 fresh verification observations per color are session checks. They do not establish production accuracy, normal-speed four-can counting or a new Pi throughput result. The model-free camera delivery measurement runs while the backend is loaded but idle; its metadata distinguishes that from inference being executed.

## Relay polarity and connection plan on October 26

The Pi runner and output-cycle tool now accept `--gpio-active-low` for a checked low-trigger relay interface. Default active-high LED operation is retained. Libgpiod requests the three lines initially inactive with the selected polarity, and cleanup writes them inactive before release. The selected polarity is recorded in session metadata.

All 75 software tests passed in both Windows environments described above. New checks cover active-low line settings, initial/off requests, exception cleanup, entry-point argument validation, output-cycle selection and metadata. These checks do not drive a physical relay or prove electrical input compatibility. The photographed board still needs the staged 3.3 V input / 5 V coil and lamp checks in the [connection plan](../pi/STACK-LIGHT-WIRING.md). Its drawing was rendered and visually inspected. No model weights, color thresholds or counting rules were changed by this update.
