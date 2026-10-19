# Shared runtime modules

Both current programs import these modules. The five color/identity/counting files were promoted without algorithm changes from the frozen camera-v1 / V4 counter. `source-provenance.json` records their hashes. The original private experiment and Pi deployment remain intact.

| File | Role |
| --- | --- |
| `color_analysis.py` | HSV votes within each individual can mask, including interior sampling and unknown results |
| `instance_quality.py` | Remove nearly identical same-color mask predictions within an image |
| `instance_memory.py` | Reconnect physical instances across raw tracker-ID changes; confirm actual three-of-five observations |
| `observer.py` | ByteTrack observations, ROI membership and clearing of lost group identities |
| `pack_crossing.py` | One ROI admission per instance, context grace, observed left-defect exits and uncertainty reviews |
| `pack_ledger.py` | Persistent per-box quantities, event deduplication, undo, review and reset |
| `geometry.py` | NumPy box adapter, letterbox transformation and normalized ROI restoration |
| `camera.py` | Camera backend selection, blank-image checks and rotation helpers for Windows |
| `settings.py` | Current HSV settings validation and recipe parsing |
| `recording.py` | Bounded background image writer and timed trial-video finalization for Windows |
| `video.py` | FFmpeg lookup |
| `torch_support.py` | Restricted checkpoint loading and raw-head export; not needed for live Hailo inference |
| `vendor/` | Retained Ultralytics ByteTrack implementation and NumPy helpers; see `../licenses/` |

Geometry and bookkeeping adapters may differ from the old experiment imports, but the counting rules remain the same. A separate full-sequence comparison checks IDs, counts, review state and ordered events against the private reference logs. Public synthetic tests exercise the core rules without publishing that footage.
