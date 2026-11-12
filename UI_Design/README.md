Can Inspection System graphical user interface developed using Qt Designer.
This will include a home screen to start the program, a production run screen with pause/stop buttons, a screen to switch between recipes, a screen to add new recipes, and a pop-up window when the recipe is produced incorrectly.



With the Acer monitor connected to the Raspberry Pi, open the Raspberry Pi desktop and click the Terminal icon.
First, install the required software:
sudo apt update
sudo apt install -y python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtuitools python3-opencv python3-numpy unzip


Then run:
cd ~/Downloads

unzip -o FinalizedCanDetectionUISystem_Live_OpenCV.zip

cd FinalizedCanDetectionUISystem_Live_OpenCV


Check that the required Python libraries are installed:
python3 -c "import cv2, numpy, PySide6; from PySide6.QtUiTools import QUiLoader; print('All libraries working')"

Step 4: Run the HMI with the live camera
python3 main.py --camera 0
