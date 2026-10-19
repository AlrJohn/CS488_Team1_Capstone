# Current camera approach

We detect individual can instances, classify HSV color within each mask and confirm identities across several observations. Confirmed cans in the active ROI are assumed packed; only an observed left defect crossing subtracts. This avoids requiring a separate visible packaging boundary, while leaving carton placement unverified.

Keep waiting stock outside the count area and complete labels visible through the lift. Use a tracking margin around the ROI, leave space to observe the left defect exit, and check geometry whenever the camera mounting changes. Better lighting supports this process but does not guarantee that touching or heavily hidden cans will be separated.

See the [architecture](architecture.md), [current tests](testing.md), [development history](development-history.md) and [measured validation](validation.md). The [earlier approach note](../legacy/color_baseline/docs/approach.md) explains the original color-region boundary counter and is retained as historical context.
