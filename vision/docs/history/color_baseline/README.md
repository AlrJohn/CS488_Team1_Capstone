# Earlier color-only prototype

The October 14 prototype used HSV regions and visible boundary crossings. Testing on the Yards footage showed that nearby cans could merge into one region and label printing could split one can into several regions. We moved to individual can masks while keeping OpenCV for color analysis.

The [approach note](approach.md) and [recorded-clip findings](recorded-clip-test.md) preserve that research. They describe the earlier experiment. Use the [current vision overview](../../../README.md) to run the maintained application.

The retired executable, configuration, tests and presentation recorder remain in Git history. The November 13 cleanup removed those launch options from the working tree so they cannot be confused with the trained model.
