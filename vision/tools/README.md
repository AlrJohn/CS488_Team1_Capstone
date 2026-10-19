# Model maintenance tools

These entry points use repository-relative paths and explicit private dataset inputs. They are parameterized versions of the training/export/build work. They do not depend on the unpublished experiment tree or automatically replace the shipped models. Run commands from the repository root.

| Script | Purpose |
| --- | --- |
| `verify_models.py` | Check the shipped PT/HEF hashes and their shared source identity; no framework or hardware required |
| `train_segmenter.py` | Further fine-tuning on a private one-class YOLO segmentation dataset |
| `export_onnx.py` | Export a checkpoint to fixed 320×640, batch-one raw segmentation heads |
| `prepare_calibration.py` | Letterbox training images into an RGB uint8 Hailo calibration tensor |
| `compile_hailo.py` | Parse, quantize and compile with Linux x86-64 DFC 3.34.0; without `--run`, report prerequisites only |

## Training

Install the Windows/workstation requirements. Prepare a private YOLO segmentation YAML with a single `can` class and separate train/validation/test recording groups. The helper rejects identical split locations, but you must also check for duplicate images and correlated pickup cycles; different folder names do not prove independence.

```bash
python vision/tools/train_segmenter.py --data /path/to/private/data.yaml \
  --output vision/runs/training/camera-v2 --device 0
```

The default base is the shipped camera-v1 checkpoint, so this command performs further adaptation. `configs/training-camera-v1.json` records the preceding camera-adaptation hyperparameters; the original prior checkpoint/dataset are not bundled. This helper is not a claim that a public clone can reconstruct the original private training split exactly. Validation selects the checkpoint; the test split is not used for training selection. A new candidate and sidecar are saved inside the new run folder.

## Export and calibration

Add `requirements-export.txt` to the workstation environment. Start with the shipped model or pass `--model` for a new candidate:

```bash
python vision/tools/export_onnx.py
python vision/tools/prepare_calibration.py --train-images /path/to/private/images/train
```

Default outputs go under ignored `vision/runs/build/`. Existing outputs are preserved; choose a new `--output` path for another build. The calibration folder must contain training images prepared for the intended runtime crop. Never point it at held-out validation/test images. The initial shipped HEF used 43 locked training images; a different calibration input is a new build and needs new comparison tests.

## Hailo compilation

Use a separate Linux x86-64 environment with official Hailo Dataflow Compiler **3.34.0**. Our original build used Ubuntu 22.04 under WSL and Python 3.10. Follow the compiler's own dependency requirements; do not install it in the Pi runtime environment. Obtain it through [Hailo Developer Zone](https://hailo.ai/developer-zone/software-downloads/).

```bash
python vision/tools/compile_hailo.py
python vision/tools/compile_hailo.py --run
```

The first command reports prerequisites. The second reads the exported ONNX and training-only calibration, inserts the input normalization, retains raw segmentation outputs, saves intermediate HARs and produces an Hailo-8 HEF plus its identity JSON. No COCO/80-class NMS configuration is imported. HailoRT 4.24.0 is the checked runtime for this build.

## Replace a candidate deliberately

Compare the original floating-point predictions, exported predictions and quantized outputs on held-out images and complete pickup sequences. Measure actual hardware inference and pack events separately. The known conversion failure shows why similar single-frame masks do not establish equal counts.

A new HEF sidecar's source checkpoint hash must match the candidate runtime JSON `model_sha256`. Keep a local runtime copy, pass it with `--runtime-config`, and use `--model` for the candidate HEF. Do not change network dimensions only in JSON; export, compilation and the decoder contract must agree. Replace the shipped model/metadata/config only after the new candidate is reviewed.
