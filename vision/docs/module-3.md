# Module 3 development

CS488 · Team 1 · November 13, 2026

Our prototype now connects the camera, trained can detector, OpenCV color analysis, carton counter, touchscreen and stack light. We are moving into verification and testing next week. This checklist links the development work to the presentation requirements in the October 18 announcement and the November 9 reminder.

## Development requirements

| Requirement | Current material | Remaining presentation work |
| --- | --- | --- |
| Programmer pairings and lessons | Jonathan and Faahil: model, OpenCV and the remaining vision/runtime work. Sabrina, Liya and Margaret: UI development. | Describe these two working groups and the lessons below. Add any specific sessions the team wants to discuss. |
| Coding conventions | [Agreed standard and examples](coding-conventions.md); root `pyproject.toml`; maintained source and tests | Show a short real code example with names, docstrings and comments. |
| Software, versions and sources | [Software inventory](software.md) and platform requirements files | Show the application dependencies separately from the workstation compiler tools. |
| Build/deployment details | [Deployment guide](deployment.md), platform READMEs and model identity checks | Show the Pi hardware/software stack, entry point and configuration files. |
| Assets and UI screenshots | [Asset inventory](assets.md), Qt screens and images | Use current page captures; identify the production controls and displayed counts. |
| Unit tests for all functions | [Software test guide](testing.md) and [function execution inventory](function-coverage.csv) | Show passing results and the remaining untested functions/branches. Full function coverage is still open. |
| AI-generated code, why and source | Existing local AI-use working register | Hold this slide for the team's review. |
| Weekly GitHub graphs and check-ins | Git history and weekly scrum reports | Capture the repository graphs after the team pushes. Keep author counts tied to the relevant week. |
| Weekly Kanban activity | Team's existing Microsoft Planner board and scrum reports | Capture Backlog, In-Process and Completed with task owners for each week. |
| Weekly burndown and acceleration | Local Module 3 progress templates and scrum reports | Use actual task estimates/completions. Confirm the acceleration calculation with the professor. |

## Development groups and lessons

Jonathan and Faahil worked together on the model and computer-vision side. Our early color-region detector could recognize red, green and blue, but it could merge nearby cans into one region. This led us to separate the jobs: the trained model finds each can, OpenCV reads the label color within its mask, and the tracker/ledger handles counting across frames. A clear detection in one image is different from enough observations to count the can during a fast pickup.

The Pi work also showed why we need to time the whole application. The HAT runs the model, while the Pi still handles masks, colors, tracking, previews and recording. Camera delivery, inference, analysis and screen refresh therefore need separate measurements. Lighting and label orientation need their own checks because a good can mask can still have too little usable color.

Sabrina, Liya and Margaret worked together on the UI. Bringing the screens into the application required more than displaying a camera feed. Start, Pause, Finish and New Box needed to follow the counter's state, and the saved history needed to use the worker's final result. We also needed the same recipe, color configuration and ready decision in the UI and terminal program, so changing screens would not create a second set of inspection rules.

These lessons summarize the work completed by the groups. Specific driver/navigator rotations and session dates have not been recorded here.

## Next phase

Use assigned test cases for complete cartons, different grab sizes, label directions, lighting, pauses, resets and defect removal. Record the actual quantities, station profile, model identity, requested/delivered camera rate, analyzed FPS, missed/duplicate counts and physical light result. Use failed cases to make focused changes and rerun the relevant software and camera checks.

The presentation remains a separate shared file. Repository cleanup and software checks come first; its technical slides will be updated after the source is reviewed and pushed.
