# Shared runtime modules

Both current programs import these modules. The original color/identity/counting implementation came from the camera-v1 / V4 counter. Current updates include two-of-five confirmation, cropped color processing and a side-color fallback for white labels. The [architecture guide](../docs/architecture.md) describes the active rules. The original private experiment and Pi deployment remain intact.

| File | Role |
| --- | --- |
| `color_analysis.py` | HSV votes within each can mask, with interior sampling, white-label side fallback and unknown results |
| `color_calibration.py` | Labeled pixel collection, HSV fitting, fresh verification totals and new local profiles for Pi setup |
| `instance_quality.py` | Remove nearly identical same-color mask predictions within an image |
| `instance_memory.py` | Reconnect physical instances across raw tracker-ID changes; confirm actual two-of-five observations |
| `observer.py` | ByteTrack observations, ROI membership and clearing of lost group identities |
| `pack_crossing.py` | One ROI admission per instance, context grace, observed left-defect exits and uncertainty reviews |
| `pack_ledger.py` | Persistent per-box quantities, event deduplication, undo, review and reset |
| `geometry.py` | NumPy box adapter, letterbox transformation and normalized ROI restoration |
| `camera.py` | Camera backend selection, blank-image checks and rotation helpers for Windows |
| `settings.py` | HSV, ordinary-check and side-fallback settings validation, plus recipe parsing |
| `recording.py` | Bounded background image writer and timed trial-video finalization for Windows |
| `video.py` | FFmpeg lookup |
| `torch_support.py` | Restricted checkpoint loading and raw-head export; not needed for live Hailo inference |
| `vendor/` | Retained Ultralytics ByteTrack implementation and NumPy helpers; see `../licenses/` |

Geometry and bookkeeping adapters may differ from the old experiment imports, but the counting rules remain the same. A separate full-sequence comparison checks IDs, counts, review state and ordered events against the private reference logs. Public synthetic tests exercise the core rules without publishing that footage.
