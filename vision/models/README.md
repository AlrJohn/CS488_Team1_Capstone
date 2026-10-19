# Shipped camera-v1 model

| File | Purpose |
| --- | --- |
| `can-camera-v1.pt` | PC one-class YOLOv8n segmentation checkpoint, about 3.39 million parameters |
| `can-camera-v1.json` | Checkpoint hash, class/task and training provenance identifiers |
| `can-camera-v1.hef` | The same source model compiled for Hailo-8 with DFC 3.34.0 |
| `can-camera-v1.hef.json` | HEF/source hashes, Hailo architecture, input/output contract and runtime version |

We include these two small runtime artifacts so a fresh checkout can run without our private experiment folder. Other downloaded checkpoints, ONNX/HAR intermediates, training data and trial files remain ignored. These are controlled-trial candidates with known limitations, not a production-certified model.

Verify the files with `python vision/tools/verify_models.py`. The published PC checkpoint SHA-256 is `f18f9ba44cd525a130f4d499ec937d8373ef80b3a257ab54c6407533b2b9c234`. The Hailo-8 HEF SHA-256 is `25e318efbd48132d9252c32dd8d83a5891fbe306350968ca3203aa6b2f40d309`.

The network predicts the class `can`, plus an instance mask. OpenCV determines label color afterward. It does not read a SKU name or verify carton placement. The Hailo input is RGB NHWC, 0–255, batch one, 320 high × 640 wide; normalization is compiled into the HEF. Do not divide the input by 255 again. Host output dequantization does not recover floating-point inference accuracy.

The architecture and tracker use Ultralytics components. Retain the [upstream notices and license](../THIRD_PARTY_NOTICES.md). Further fine-tuning needs separately managed private annotations. A new checkpoint must be exported, calibrated, compiled and independently evaluated before replacing this pair.

The PC publication copy removes six embedded local training-path strings. All 421 tensor archive entries remain byte-for-byte identical to the original checkpoint. Its sidecar retains the original `source_checkpoint_sha256`, which is the source used to compile the unchanged HEF. Model verification checks this lineage as well as each artifact hash. The runtime JSON identifies that original compiled source. These metadata edits do not constitute new fine-tuning.
