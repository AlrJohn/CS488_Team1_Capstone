# Application assets and screens

CS488 · Team 1 · Module 3 development

The touchscreen loads its assets from `UI_Design/corrected/`, independently of the terminal's working folder.

| Asset | Use |
| --- | --- |
| `home.ui` | Home screen and navigation |
| `configure.ui` | Recipe quantities and enabled colors |
| `recipeScreen.ui` | Saved recipe selection |
| `runScreen.ui` | Production controls and count display |
| `widget.py` | Inspection-history screen and CSV export |
| `yards_logo.png` | Shared Yards branding loaded through `branding.py` |
| `YardsRedCan.webp`, `YardsGreenCan.webp`, `YardsBlueCan.webp` | Recipe-screen can images |
| `vision/pi/*WIRING.svg`, `PI-RELAY-CONTROL.svg` | Hardware connection diagrams, with supporting photographs |
| `docs/design/` | Station and mounting drawings |
| `vision/models/can-camera-v1.pt`, `can-camera-v1.hef` and identity JSON | Selected Windows and Pi model assets; see [model details](../models/README.md) |
| `media/` | Project research photographs, visit audio and the video index |

`main.py` adjusts some Designer positions and adds production controls. Editing a `.ui` file alone may therefore not change the final position of every widget. Camera masks, tracking labels, counts and the ROI are drawn at runtime; they are not image assets.

For the presentation, capture Home, Configure Batch, Recipe Selection, Production Run and Inspection History. Include the calibration screen separately. A staged screen should be labeled as a layout example. Camera results should show actual cans and their known quantities, with private recordings shared separately.

Save selected presentation images with date, platform, screen and sequence, such as `2026-11-13_pi_production_run_01.png`. Keep original recording filenames unchanged so their logs still match.

## Current screen layouts

These November 13 captures load the actual Qt pages on Windows with the camera and model stopped. They show the layout, rather than a packing trial. The production page therefore shows the model-not-ready state, and inspection history is empty. The Pi uses the same screen source.

| Screen | Capture |
| --- | --- |
| Home | [Home layout](images/ui/2026-11-13_windows_home_01.png) |
| Configure Batch | [Configuration layout](images/ui/2026-11-13_windows_configure_01.png) |
| Recipe Selection | [Recipe layout](images/ui/2026-11-13_windows_recipes_01.png) |
| Production Run | [Production layout, camera stopped](images/ui/2026-11-13_windows_run_01.png) |
| Inspection History | [History layout](images/ui/2026-11-13_windows_history_01.png) |

The calibration-screen and actual packing-result captures will come from the next hardware test session.
