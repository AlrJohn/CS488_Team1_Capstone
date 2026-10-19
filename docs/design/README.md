# Inspection design

Our current prototype uses a learned can-instance model and OpenCV to check the selected varieties and quantities during manual picking. It assumes carton placement from confirmed ROI observations and handles observed left-side defects separately. Stack-light and alarm integration remain planned.

We are still confirming station components and costs and evaluating uncertain images and grouped picks. The [software history](../../vision/docs/development-history.md), [architecture](../../vision/docs/architecture.md) and [measured timing](../../vision/docs/validation.md) describe the current Windows and Pi programs.

| File | What it covers |
|---|---|
| [prototype-direction.md](prototype-direction.md) | Our October 15 plan for a wooden lane mockup, twelve-can home tests, camera placement opposite the employee, and possible V2 changes after testing. |
| [Bill of Materials.docx](Bill%20of%20Materials.docx) | Our draft component list, quantities, and cost estimates. We still need to confirm several prices and vendors. |
| [Software and Defect Requirements.docx](Software%20and%20Defect%20Requirements.docx) | Our image-processing approach, pass/fail conditions, and operator alerts, with open questions about unclear images. |
| [Timing + Performance Design.docx](Timing%20%2B%20Performance%20Design.docx) | Our timing and performance document. We still need to fill in the calculations and test results. |
