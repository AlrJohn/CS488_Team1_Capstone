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
