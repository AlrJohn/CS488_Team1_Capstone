Can Inspection System graphical user interface developed using Qt Designer.
This will include a home screen to start the program, a production run screen with pause/stop buttons, a screen to switch between recipes, a screen to add new recipes, and a pop-up window when the recipe is produced incorrectly.


Run it on the Raspberry Pi
After downloading the new ZIP onto the Raspberry Pi, open Terminal:
cd ~/Downloads
unzip -o FinalizedCanDetectionUISystem_Yards_Vision_Integrated.zip
cd FinalizedCanDetectionUISystem_Yards_Vision_Integrated
python3 check_setup.py --camera 0


Then launch the HMI:
python3 main.py --camera 0 --backend auto

