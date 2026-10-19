# Lane mockup and camera testing direction

October 15, 2026

> Historical direction. We subsequently trained a can-instance model and added a Pi/Hailo runtime. The [software development history](../../vision/docs/development-history.md) records those later changes; this note retains the observations that guided the mockup.

We will build a wooden mockup of the pickup area and test the camera view at home before taking the setup to Yards. We will get enough cans to assemble a complete twelve-pack, with four red, four green, and four blue cans. The supplied recording already demonstrates that the current color-region counter does not reliably handle grouped picks. We will investigate individual-can detection and segmentation on that footage while the mockup is being built. Custom training has not started and is a proposed step if the first model trial is inadequate.

## Workflow we are trying to reproduce

In the layout we observed, cans flow toward the pickup plate through four lanes, with three lanes in use. The employee stands to the left of the plate and reaches across the lanes. The reference frame and follow-up clarification establish that the employee picks two cans in each hand, for four cans in one transfer, usually from the same lane. The receiving carton is just behind the lifted cans, near the employee. This is an observation of one employee's workflow; we still need to establish how other employees work and how often the grab size varies.

For the mockup, we can arrange blue nearest the employee, then green, then red. These are example lane assignments, not a requirement that the products always occupy those positions. We will use wooden or marked dividers to reproduce the lane spacing and pickup area as closely as practical, and include a carton in the scene.

## Camera position to test

Our first proposed position is opposite the employee, looking across the pickup area toward the hands and transfer path, approximately matching the reference footage. We will compare a directly opposite view with an elevated, diagonal view. The goal is to distinguish all four cans during a four-can pick, including the two within each hand, with enough visible label area to establish each color. Separation between the hands alone is insufficient.

The nearer lanes may hide the farther ones from a low camera position. A higher angle may improve separation, but we still need to see the colored sides rather than only the silver tops. We will include the carton opening where practical and check whether placement and release are actually visible. Seeing a can move behind the carton wall does not establish that it was loaded.

The reference frame shows a short transfer path near the receiving carton. Hands, stock in front, and carton walls may obscure the final placement. The pickup, transfer, and carton-entry areas may overlap in the image, so we need to evaluate the full movement before choosing the boundary or zone shapes. A horizontal or angled boundary may fit this movement better than the vertical boundary used in the bench setup. The current program already allows those line orientations. We will also keep unrelated stock and colored clothing outside the inspection area where practical.

## Home testing before a Yards trial

We will first record individual, two-can, and four-can picks from each lane, one-can returns from a group, and full twelve-can packing cycles. The main representative case is four same-color cans moving at once, with two in each hand. We will include normal hand coverage, label rotation, touching cans, and different picking speeds. We will compare the videos with the logged events and the actual contents of the carton, keeping the camera settings with each trial.

The mockup will help establish whether all four cans remain observable during the transfer, whether their colors are readable, and whether their movement crosses a visible inspection area. A short sequence with the same four cans identifiable across several frames is more useful than a single favorable frame. We also need to check whether waiting stock advances through that area without being picked. Lighting, camera angle, and zone placement will support testing a new detector; we should not assume that they will make the existing color-region method reliable.

The current program detects colored regions. Two touching cans of the same color may appear as one region, and one label can split into several regions. We must not assume that a grab always contains four cans or that a larger colored region establishes its quantity. Completely hidden movement may still be missed without a warning.

## V2 direction from the recorded-clip test

V2 should investigate a model that detects individual can bodies, preferably with separate instance masks, followed by color classification within each can. It could use separate pickup, transfer, and optional carton-entry zones. It should maintain separate can identities during simultaneous picks, support partial returns, and assign events to one active carton. Lane-specific product expectations could provide a supporting check.

The existing recording already contains the repeated merging and missed-label failures that justify a detector change. Our [research and next experiment](../../vision/docs/history/instance-detection-20261015.md) propose an initial prompted segmentation trial on this clip, followed by a compact fine-tuned can model if needed. Better tracking is a subsequent step once individual cans can be established. Neither change can verify an unobserved transfer on its own. The model trial does not need to wait for the mockup, which will provide fresh footage and installation testing.

Our three-can presentation demonstration remains a demonstration of the current visible pick/return counter. It does not validate grouped picks, carton placement, full twelve-pack accuracy, or production speed.

The working [camera approach](../../vision/docs/approach.md) and [test plan](../../vision/docs/testing.md) describe the current implementation and checks.

Our [first recorded-clip experiment](../../vision/legacy/color_baseline/docs/recorded-clip-test.md) provides an initial check before the mockup. Separate calibration recovers red, green, and blue label regions in the supplied Yards footage, but merged cans, missed label strips, unrelated colored objects, and camera movement prevent reliable grouped-pick counting. Those failures now guide the detector research and the fixed-camera mockup together.
