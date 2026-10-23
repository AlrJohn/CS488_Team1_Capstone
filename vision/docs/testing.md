# Test plan

We test recognition, color, identity and pack events separately because a final total of twelve can hide a missed can and a duplicate that cancel each other out. Keep physical quantities or independently reviewed footage as ground truth.

## Software checks

From the repository root, with either current environment installed:

```bash
python vision/tools/verify_models.py
python -m unittest discover -s vision/tests -v
```

These tests cover mask-limited color sampling, touching versus duplicate masks, observed-frame confirmation, ID reconnection, one admission per identity, ordinary disappearance, left defects and over-target totals. The [legacy prototype](../legacy/color_baseline/README.md) has a separate 47-test suite; its crossing rules are not the current pack policy.

Color tests compare the original check's labels, sampled-pixel counts, votes, coverage, dominance and failure reasons with the full-image calculation while the side fallback is disabled. Cases include hue wrap, image edges, hand-shaped holes, empty/small masks and 0/255 masks. Side-fallback cases cover white centers with narrow red/green/blue strips, one visible side, conflicting sides, small colored patches, background exclusion, glare and rim exclusion, plus the disable control. A Pi pipeline check verifies that recovered side color still needs two observations before counting. Camera tests use a simulated device whose reported FPS differs from delivery. Runner tests verify station settings, cleanup and continued analysis/counting while GUI draws are skipped. These checks do not establish hardware frame rates.

The optional Pi indicator tests use fake outputs to check status mapping, atomic three-line commands, exclusive access and shutdown cleanup. They never drive GPIO. After wiring the LEDs, follow the separate [GPIO cycle and camera checks](../pi/GPIO-WIRING.md).

Ordinary color-limit tests load edited JSON and show that each `interior_sampling` value changes acceptance independently. They also check invalid limits and older profiles without the section. The Pi pipeline has an additional check that a JSON pixel limit affects the actual count decision, with the side fallback disabled to isolate the ordinary check.

Calibration tests cover clicked-mask boundaries, white printing/background rejection, bounded pixel storage, red hue wrap, range separation, unchanged counting thresholds, verification unknowns/wrong colors, guarded saves and unique profile names. A simulated camera/model drives the real screen workflow through collection, fitting, fresh verification and saving. Runner checks verify that the same open camera/backend continue with the saved profile, counting still waits for P, and cancellation creates no recording. Rendered screens are inspected separately. These are software checks without ARM/Hailo hardware or a physical touch display.

## Controlled camera sequence

1. Check complete label visibility across the intended movement, ROI, defect line and orientation. Start with an empty count area and carton.
2. Pick singles, pairs and four-can groups. Vary the color order. For every group, compare the count increment with the actual number, not just the final total.
3. Complete repeated 4/4/4 packs at normal speed. Include brief hand coverage, touching cans, label rotation, glare and different operators.
   For white-label cases, face the label toward the camera and test both colored sides visible, then one side obscured. Check `color_analysis.sampling_method` and side votes in the log. Include green artwork on blue cans and cans tilted sideways; the side fallback has not been validated for those physical cases.
4. After admitting a known can, move it visibly from right to left across the defect line. Confirm one subtraction of the correct color. An uncounted can first appearing on the defect side must not subtract someone else's can.
5. Test an ordinary return through another edge: under the current assumption it stays counted. Test lost crossing evidence and verify that the program requests review rather than inventing a removal.
6. Clear the area before a new box. Windows N saves/prepares and requires P again; Pi N immediately resets the active counter. Confirm no previous-box identities or counts carry over.

Do not hide errors by capping quantities at four, forcing a color or assuming every grab contains four cans. A REVIEW result requires an independent count check. Acknowledging it does not repair the ledger.

## Recording and metrics

Keep raw/annotated footage and per-frame logs under ignored `vision/runs/`. On the Pi, use `--save-source --save-preview` for an error investigation. For operating-throughput measurements, omit image-saving flags and measure that mode separately.

Record the model hash, settings, camera view and requested versus delivered frame rate. Report exact group count, color errors/unknowns, missed/duplicate admissions, defects, review frequency, processed FPS and latency distribution. In particular, distinguish Hailo inference from the complete processing and recording loop. Host timing is not a measurement of sensor-to-display delay.

## Training and evaluation separation

Keep entire pickup cycles or recordings in one split. Adjacent frames from the same motion must not be divided randomly between training and test. Reserve untouched recordings before selecting training frames. Hailo calibration uses training images only. Reviewed failure recordings can become regression material, but no longer count as fresh independent evaluation once they guide a change.

The raw dataset and split manifests remain private. Public documentation records the method and aggregate findings. Publishing a new performance figure should identify the hardware, recording mode, grab size and whether that footage was already used for development.
