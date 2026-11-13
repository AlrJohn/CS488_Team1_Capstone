# Inspection design

Our current prototype uses a learned can-instance model and OpenCV to check the selected varieties and quantities during manual picking. It assumes carton placement from confirmed ROI observations and handles observed left-side defects separately. The red, yellow and green stack lights have been tested; the buzzer remains disconnected.

We are still confirming station components and costs and evaluating uncertain images and grouped picks. The [software history](../../vision/docs/development-history.md), [architecture](../../vision/docs/architecture.md) and [measured timing](../../vision/docs/validation.md) describe the current Windows and Pi programs.

| File | What it covers |
|---|---|
| [demo-station-parts.md](demo-station-parts.md) | Five-item VIVO pole order ($128.85 before tax/shipping), with wood, fasteners, spacers and light mounting supplied locally. The Keyence housing still needs confirmation. |
| [demo-station-layout.svg](demo-station-layout.svg) | Editable VIVO pole sketch with the camera, screen arm, table-supported enclosure and an example clearance detail. Adapters and the final light mount are fabricated locally. |
| [prototype-direction.md](prototype-direction.md) | Our October 15 plan for a wooden lane mockup, twelve-can home tests, camera placement opposite the employee, and possible V2 changes after testing. |
| [Bill of Materials.docx](Bill%20of%20Materials.docx) | Our draft component list, quantities, and cost estimates. We still need to confirm several prices and vendors. |
| [Software and Defect Requirements.docx](Software%20and%20Defect%20Requirements.docx) | Our image-processing approach, pass/fail conditions, and operator alerts, with open questions about unclear images. |
| [Timing + Performance Design.docx](Timing%20%2B%20Performance%20Design.docx) | Our timing and performance document. We still need to fill in the calculations and test results. |
