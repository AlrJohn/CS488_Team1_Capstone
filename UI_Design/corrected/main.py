import sys
import json
import argparse
from pathlib import Path
from PySide6.QtCore import QDir, QFile, QTimer, Qt, QObject, Slot
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QColor, QPainter, QPixmap, QImage, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QPushButton, QLabel, QCheckBox,
                               QMessageBox, QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView, QMainWindow, QStackedWidget, QGraphicsView, QGraphicsScene, QFrame, QAbstractItemView)
from widget import InspectionHistory
from worker import CameraWorker
from history_store import save_box
from recipe_store import load_recipes, save_recipes, validate_recipe
from vision_runtime import VISION_ROOT, configuration_paths, display_colors, inspection_status

BASE = Path(__file__).resolve().parent


class FittedPage(QGraphicsView):
    """Keep Designer coordinates intact; fit the entire page to the display."""
    def __init__(self, content, width=800, height=600):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(QColor('#05253e'))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        content.setFixedSize(width, height)
        self.proxy = self.scene_obj.addWidget(content)
        self.content = content
        self.scene_obj.setSceneRect(0, 0, width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.scene_obj.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


def arrange_home(content):
    """Center the original buttons on the 800 x 600 Designer canvas."""
    title = content.findChild(QLabel, 'label')
    subtitle = content.findChild(QLabel, 'label_2')
    if title:
        title.setGeometry(80, 65, 640, 58)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet('color:white; font-size:32px; font-weight:bold; background:transparent;')
    if subtitle:
        subtitle.setGeometry(80, 126, 640, 28)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet('color:#bdd1e0; font-size:15px; background:transparent;')
    for i, (button_name, caption_name) in enumerate((
        ('ProductionRunButton', 'label_3'),
        ('ConfigureButton', 'label_4'),
        ('InspectionButton', 'label_5'),
    )):
        y = 187 + i * 116
        button = content.findChild(QPushButton, button_name)
        caption = content.findChild(QLabel, caption_name)
        if button:
            button.setGeometry(175, y, 450, 94)
            button.setStyleSheet(button.styleSheet() + 'QPushButton { font-size: 24px; font-weight: bold; border-radius: 12px; padding-bottom: 18px; }')
        if caption:
            caption.setGeometry(190, y + 57, 420, 24)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            caption.setStyleSheet('color:white; background:transparent; font-size:14px;')
            caption.raise_()


class StationWindow(QMainWindow):
    """Keep the camera worker alive until its hardware has closed safely."""
    def closeEvent(self, event):
        if self.shutdown_handler():
            event.accept()
        else:
            event.ignore()


class HMI(QObject):
    """Update widgets on Qt's main thread using snapshots from the camera worker."""
    def __init__(self, camera_source=None, vision_root=None, backend='hailo', model=None,
                 vision_options=None, camera_settings=None, data_dir=None, windowed=False):
        super().__init__()
        self.camera_settings = json.loads((BASE / 'station_settings.json').read_text())
        self.camera_settings.update(camera_settings or {})
        self.vision_root = Path(vision_root).expanduser().resolve() if vision_root else VISION_ROOT
        self.vision_options = dict(vision_options or {})
        self.local_dir = Path(data_dir) if data_dir else BASE / 'local'
        self.history_file = self.local_dir / 'inspection_history.csv'
        self.recipe_file = self.local_dir / 'recipes.json'
        self.windowed = windowed
        self.box_started = False
        self._finishing = False
        self._command_pending = False
        self.last_metadata = {}
        self.backend = backend
        self.model = model
        self.model_ready = False
        self.pipeline_recipe = None
        self.pipeline_status = ''
        self.framing_warning = ''
        self.detection_message = ''
        self.camera_source = camera_source if camera_source is not None else self.camera_settings["camera_source"]
        self.camera = None
        self.counts = {"Red": 0, "Green": 0, "Blue": 0}
        self.completed_packs = 0
        self.loader = QUiLoader()
        # Resolve Designer images beside the .ui files, regardless of launch folder.
        self.loader.setWorkingDirectory(QDir(str(BASE)))
        self.pages = {}
        self.views = {}
        self.designer_windows = {}
        self.window = StationWindow()
        self.window.shutdown_handler = self.shutdown
        self.window.setWindowTitle('Can Inspection System')
        self.window.resize(1066, 800)
        self.exit_shortcut = QShortcut(QKeySequence('Esc'), self.window)
        self.exit_shortcut.activated.connect(self.window.close)
        self.stack = QStackedWidget()
        self.window.setCentralWidget(self.stack)
        for key, filename in [('home', 'home.ui'), ('configure', 'configure.ui'),
                              ('recipes', 'recipeScreen.ui'), ('run', 'runScreen.ui')]:
            file = QFile(str(BASE / filename))
            if not file.open(QFile.ReadOnly):
                raise RuntimeError(f'Cannot open {filename}')
            designer_window = self.loader.load(file)
            file.close()
            if designer_window is None:
                raise RuntimeError(f'Cannot load {filename}: {self.loader.errorString()}')
            self.designer_windows[key] = designer_window
            content = designer_window.takeCentralWidget()
            if content is None:
                raise RuntimeError(f'{filename} has no central widget')
            content.setParent(None)
            self.pages[key] = content
            if key == 'home':
                arrange_home(content)
            view = FittedPage(content)
            self.views[key] = view
            self.stack.addWidget(view)
        self.history = InspectionHistory(history_file=self.history_file)
        self.history.setMinimumSize(0, 0)
        self.history.back_button.clicked.disconnect()
        self.history.back_button.clicked.connect(lambda: self.show('home'))
        self.history_view = FittedPage(self.history, 1200, 850)
        self.stack.addWidget(self.history_view)
        paths = configuration_paths(self.vision_root, **{key: self.vision_options.get(key)
                                    for key in ('config_dir', 'runtime', 'colors', 'view')})
        runtime = json.loads(paths['runtime'].read_text(encoding='utf-8'))
        self.config = display_colors(runtime['expected_recipe'])
        self.recipes = load_recipes(self.recipe_file, self.config)
        self.selected_recipe = 'Station Recipe'
        self.running = False
        self.elapsed = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)

        self.bind('home', 'ProductionRunButton', self.start_run)
        self.bind('home', 'ConfigureButton', lambda: self.show('recipes'))
        self.bind('home', 'InspectionButton', lambda: self.show('history'))

        for color in ('red', 'green', 'blue'):
            self.bind('configure', f'{color}PlusButton', lambda c=color: self.adjust(c, 1))
            self.bind('configure', f'{color}MinusButton', lambda c=color: self.adjust(c, -1))
            checkbox = self.find('configure', f'{color}Enabled', QCheckBox)
            if checkbox:
                checkbox.stateChanged.connect(self.update_total)
        self.bind('configure', 'cancelButton', lambda: self.show('recipes'))
        self.bind('configure', 'saveButton', self.save_config)
        self.bind('recipes', 'cancelButton', lambda: self.show('home'))
        self.bind('recipes', 'runButton', self.start_run)
        self.bind('recipes', 'createNewButton', lambda: self.show('configure'))
        self.bind('run', 'StopButton', self.stop_run)
        self.bind('run', 'PauseButton', self.pause_run)
        self.bind('run', 'WrongCanPopupButton', self.wrong_can)

        self.recipe_table = self.find('recipes', 'recipeTable', QTableWidget)
        if self.recipe_table:
            self.recipe_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.recipe_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.recipe_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.recipe_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.recipe_table.verticalHeader().setVisible(False)
            self.recipe_table.setStyleSheet('QTableWidget {background:#F2F6FA;color:#172B42;'
                                           'selection-background-color:#3478B8;selection-color:white;}'
                                           'QHeaderView::section {background:#C9D8E6;color:#102B45;padding:6px;}')
            self.recipe_table.itemSelectionChanged.connect(self.select_recipe)
        if self.find('configure', 'recipeNameInput', QLineEdit) is None:
            recipe_name = QLineEdit(self.pages['configure'])
            recipe_name.setObjectName('recipeNameInput')
            recipe_name.setPlaceholderText('Recipe name (optional)')
            recipe_name.setGeometry(72, 421, 546, 43)
            recipe_name.setStyleSheet('background:#DCE6F0;color:#172B42;border-radius:6px;'
                                     'padding:8px;font-size:16px;')
            recipe_name.show()
        self.add_back_button('configure', 'Back to Home', 'home')
        self.add_back_button('recipes', 'Back to Home', 'home')
        self.add_back_button('run', 'Back to Home', 'home')
        self.setup_camera_panel()
        self.update_total()
        self.load_can_images()
        self.populate_recipes()
        self.show('home')

    def find(self, page, name, kind=QWidget):
        return self.pages[page].findChild(kind, name)

    def bind(self, page, name, callback):
        button = self.find(page, name, QPushButton)
        if button:
            button.clicked.connect(lambda checked=False, action=callback: action())

    def add_back_button(self, page, title, destination):
        content = self.pages[page]
        button = QPushButton(title, content)
        button.setObjectName('navigationBackButton')
        button.setGeometry(625, 12, 163, 47)
        button.setStyleSheet('QPushButton {background:#526D86;color:white;border-radius:8px;font-size:14px;font-weight:bold;} QPushButton:hover {background:#6986A1;}')
        button.raise_()
        button.show()
        button.clicked.connect(lambda checked=False, target=destination: self.navigate_back(target))

    def navigate_back(self, destination):
        if self.current == 'run':
            if not self.confirm_discard_box():
                return
            if not self.stop_camera():
                return
            self.timer.stop()
            self.running = False
        self.show(destination)

    def show(self, name):
        if name == 'history':
            self.history.load_history()
            destination = self.history_view
        else:
            if name == 'recipes':
                self.populate_recipes()
            if name == 'run':
                self.update_target()
            destination = self.views[name]
        self.current = name
        self.stack.setCurrentWidget(destination)
        if not self.window.isVisible():
            self.window.show() if self.windowed else self.window.showFullScreen()

    def adjust(self, color, delta):
        label = self.find('configure', f'{color}QtyLabel', QLabel)
        if label:
            label.setText(str(max(0, int(label.text()) + delta)))
        self.update_total()

    def get_config(self):
        config = {}
        for color in ('red', 'green', 'blue'):
            label = self.find('configure', f'{color}QtyLabel', QLabel)
            enabled = self.find('configure', f'{color}Enabled', QCheckBox)
            config[color.capitalize()] = int(label.text()) if label and (enabled is None or enabled.isChecked()) else 0
        return config

    def update_total(self, *_):
        total = sum(self.get_config().values())
        label = self.find('configure', 'totalLabel', QLabel)
        if label:
            label.setText(f'Total Expected Cans: {total}')
    def load_can_images(self):

        red = self.find('configure', 'redCanImage', QLabel)
        green = self.find('configure', 'greenCanImage', QLabel)
        blue = self.find('configure', 'blueCanImage', QLabel)
        if red:
            red.setPixmap(QPixmap(str(BASE / "YardsRedCan.webp")))
            red.setScaledContents(True)
        if green:
            green.setPixmap(QPixmap(str(BASE / "YardsGreenCan.webp")))
            green.setScaledContents(True)
        if blue:
            blue.setPixmap(QPixmap(str(BASE / "YardsBlueCan.webp")))
            blue.setScaledContents(True)
    def save_config(self):
        config = self.get_config()
        if sum(config.values()) == 0:
            QMessageBox.warning(self.pages['configure'], 'Invalid Configuration', 'Enable at least one can type with a positive quantity.')
            return
        name_field = self.find('configure', 'recipeNameInput', QLineEdit)
        name = name_field.text().strip() if name_field else ''
        if not name:
            name = f'Custom Recipe {len(self.recipes)}'
        if name in self.recipes:
            QMessageBox.warning(self.pages['configure'], 'Duplicate Recipe', 'Please choose a unique recipe name.')
            return
        try:
            validate_recipe(config)
            recipes = dict(self.recipes, **{name: config.copy()})
            save_recipes(self.recipe_file, recipes)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.window, 'Recipe Not Saved', str(error))
            return
        self.recipes = recipes
        self.config = config.copy()
        self.selected_recipe = name
        if name_field:
            name_field.clear()
        self.show('recipes')

    def populate_recipes(self):
        if not self.recipe_table:
            return
        table = self.recipe_table
        table.blockSignals(True)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['Recipe', 'Red', 'Green', 'Blue'])
        table.setRowCount(len(self.recipes))
        selected_row = 0
        for row, (name, config) in enumerate(self.recipes.items()):
            for col, value in enumerate([name, config['Red'], config['Green'], config['Blue']]):
                table.setItem(row, col, QTableWidgetItem(str(value)))
            if name == self.selected_recipe:
                selected_row = row
        table.selectRow(selected_row)
        table.blockSignals(False)
        self.update_recipe_labels()

    def select_recipe(self):
        row = self.recipe_table.currentRow()
        if row >= 0 and self.recipe_table.item(row, 0):
            self.selected_recipe = self.recipe_table.item(row, 0).text()
            self.update_recipe_labels()

    def update_recipe_labels(self):
        config = self.recipes[self.selected_recipe]
        label = self.find('recipes', 'selectedRecipeLabel', QLabel)
        if label:
            label.setText(f'Selected Recipe: {self.selected_recipe}')
        breakdown = self.find('recipes', 'recipeBreakdownLabel', QLabel)
        if breakdown:
            breakdown.setText(f"Red: {config['Red']}  Green: {config['Green']}  Blue: {config['Blue']}")

    def update_target(self):
        label = self.find('run', 'TargetQuantityLabel', QLabel)
        if label:
            label.setText(f'Target Quantity: {sum(self.config.values())}')

    def setup_camera_panel(self):
        """Keep original Qt Designer page, but show an actual large camera feed."""
        page = self.pages['run']
        panel = self.find('run', 'ProductionPanel', QFrame)
        panel.setGeometry(18, 95, 764, 386)
        panel.setStyleSheet('QFrame#ProductionPanel {background:#163759; border-radius:12px;}')
        geometry = {
            'varietyTitle': (18, 8, 450, 35),
            'TargetQuantityLabel': (485, 50, 255, 30),
            'currentCount': (485, 87, 255, 30),
            'countLabel1': (485, 130, 255, 36),
            'countLabel2': (485, 173, 255, 36),
            'countLabel3': (485, 216, 255, 36),
            'StatusLabel': (480, 260, 268, 46),
            'RunTimerLabel': (485, 318, 260, 24),
            'PackCountLabel': (485, 351, 260, 24),
        }
        for name, rect in geometry.items():
            label = self.find('run', name, QLabel)
            if label:
                label.setGeometry(*rect)
        for name in ('countLabel1', 'countLabel2', 'countLabel3'):
            label = self.find('run', name, QLabel)
            label.setStyleSheet('font-size:22px; font-weight:bold; color:#FFFFFF;')
        self.preview = QLabel('CAMERA NOT STARTED', panel)
        self.preview.setObjectName('LiveCameraPreview')
        self.preview.setGeometry(16, 51, 451, 298)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet('background:#071724; border:2px solid #487496; border-radius:8px; color:#cbd5e1; font-size:20px;')
        self.preview.show()
        self.camera_note = QLabel('LIVE ELP USB  |  Yards trained vision pipeline', panel)
        self.camera_note.setGeometry(16, 352, 451, 24)
        self.camera_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_note.setStyleSheet('color:#D4DFEC; font-size:12px; background:transparent;')
        self.camera_note.show()
        pause = self.find('run', 'PauseButton', QPushButton)
        pause.setGeometry(25, 505, 190, 61)
        pause.setStyleSheet('QPushButton {background:#F57C00; color:white; border-radius:12px; font-size:22px; font-weight:bold;}')
        stop = self.find('run', 'StopButton', QPushButton)
        stop.setGeometry(545, 505, 190, 61)
        stop.setStyleSheet('QPushButton {background:#D32F2F; color:white; border-radius:12px; font-size:22px; font-weight:bold;}')
        self.finish_button = QPushButton('FINISH BOX', page)
        self.finish_button.setGeometry(277, 505, 210, 61)
        self.finish_button.setStyleSheet('QPushButton {background:#159447; color:white; border-radius:12px; font-size:22px; font-weight:bold;} QPushButton:hover {background:#20B455;}')
        self.finish_button.clicked.connect(self.finish_box)
        self.finish_button.show()
        self.finish_button.setEnabled(False)
        self.undo_button = QPushButton('UNDO', panel)
        self.undo_button.setGeometry(485, 8, 110, 32)
        self.undo_button.clicked.connect(self.undo)
        self.verify_button = QPushButton('REVIEW', panel)
        self.verify_button.setGeometry(610, 8, 125, 32)
        self.verify_button.clicked.connect(self.verify_box)
        for button in (self.undo_button, self.verify_button):
            button.setStyleSheet('QPushButton {background:#526D86;color:white;border-radius:6px;font-size:14px;font-weight:bold;}')
            button.setEnabled(False)
            button.show()
        self.refresh_counts()

    def refresh_counts(self):
        for color, name in [('Green','countLabel1'),('Red','countLabel2'),('Blue','countLabel3')]:
            label = self.find('run', name, QLabel)
            if label:
                label.setText(f'{color}: {self.counts[color]} / {self.config[color]}')
        total = sum(self.counts.values())
        label = self.find('run', 'currentCount', QLabel)
        if label:
            label.setText(f'Detected: {total} / {sum(self.config.values())}')
        label = self.find('run', 'PackCountLabel', QLabel)
        if label:
            label.setText(f'Boxes Passed: {self.completed_packs}')

    def start_run(self):
        """Open a preview first; count only after the operator clears the ROI."""
        if not self.stop_camera():
            return
        self.config = self.recipes[self.selected_recipe].copy()
        self.counts = {'Red': 0, 'Green': 0, 'Blue': 0}
        self.model_ready = self.box_started = self.running = False
        self._finishing = self._command_pending = False
        self.last_metadata = {}
        self.elapsed = 0
        self.timer.stop()
        self.show('run')
        self.refresh_counts()
        self.finish_button.setText('START BOX')
        self.finish_button.setEnabled(False)
        self.undo_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.find('run', 'PauseButton', QPushButton).setEnabled(False)
        self.set_run_status('LOADING MODEL')
        self.preview.setText('OPENING CAMERA...')
        self.camera_note.setText('Opening the station camera and model...')
        self.camera = CameraWorker(self.camera_settings, source=self.camera_source,
                                   vision_root=self.vision_root, backend=self.backend,
                                   model=self.model, recipe=self.config,
                                   vision_options=self.vision_options)
        self.camera.frame_ready.connect(self.on_camera_frame)
        self.camera.camera_error.connect(self.on_camera_error)
        self.camera.command_done.connect(self.on_worker_command)
        self.camera.start()

    @Slot(object, object, object, object)
    def on_camera_frame(self, frame, events, counts, metadata):
        """Consume one preview; all model frames are processed in the worker."""
        worker = self.sender()
        if worker is not None:
            worker.preview_consumed()
        if worker is not None and worker is not self.camera:
            return
        if self.current != 'run':
            return
        rgb = frame[:, :, ::-1].copy()
        height, width = rgb.shape[:2]
        image = QImage(rgb.data, width, height, rgb.strides[0],
                       QImage.Format.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        if self._finishing:
            return
        self.apply_snapshot(counts, metadata)
        self.update_run_state()

    def apply_snapshot(self, counts, metadata):
        """Keep the labels tied to the shared counter's snapshot."""
        self.counts = dict(counts)
        self.last_metadata = dict(metadata)
        self.model_ready = bool(metadata.get('ready'))
        self.pipeline_recipe = metadata.get('recipe')
        self.refresh_counts()

    def update_run_state(self):
        """Show the same ready/review state that controls the stack light."""
        metadata = self.last_metadata
        recipe_matches = metadata.get('recipe') == self.config
        usable = self.model_ready and recipe_matches and not self._command_pending
        self.finish_button.setEnabled(usable)
        self.undo_button.setEnabled(usable and self.box_started)
        self.verify_button.setEnabled(usable and self.box_started and bool(metadata.get('reviews')))
        pause = self.find('run', 'PauseButton', QPushButton)
        pause.setEnabled(usable and self.box_started)
        if not self.model_ready:
            self.set_run_status('MODEL NOT READY')
        elif not recipe_matches:
            self.set_run_status('RECIPE MISMATCH')
        elif not self.box_started:
            self.set_run_status('READY TO START')
            self.camera_note.setText('Clear the yellow count area, then press START BOX.')
        elif not self.running:
            self.set_run_status('PAUSED', 'RESUME')
            self.camera_note.setText('Counting paused. Keep cans still until RESUME.')
        else:
            status = metadata.get('status', 'IN PROGRESS')
            if metadata.get('framing_warning'):
                status = 'FRAMING WARNING'
            self.set_run_status(status, 'PAUSE')
            fps = metadata.get('processed_fps', 0.)
            self.camera_note.setText(
                f'{str(metadata.get("backend", "?")).upper()} | {fps:.1f} analyzed FPS | Yellow: count | Pink: defect')

    @Slot(str)
    def on_camera_error(self, message):
        """Stop accepting boxes when camera, model or GPIO startup fails."""
        if self.sender() is not None and self.sender() is not self.camera:
            return
        self.timer.stop()
        self.running = self.model_ready = False
        self._finishing = self._command_pending = False
        self.finish_button.setEnabled(False)
        self.undo_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.find('run', 'PauseButton', QPushButton).setEnabled(False)
        self.set_run_status('STATION ERROR')
        self.preview.setText('STATION ERROR')
        self.camera_note.setText(message[:90])
        QMessageBox.warning(self.window, 'Station Could Not Run',
                            message + '\n\nClose other camera/counting programs, check the connections, '
                            'then restart Production Run.')

    def tick(self):
        """Advance the displayed timer only while counting is active."""
        self.elapsed += 1
        hours, remainder = divmod(self.elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.find('run', 'RunTimerLabel', QLabel).setText(
            f'Run Time: {hours:02}:{minutes:02}:{seconds:02}')

    def set_run_status(self, text, button_text='PAUSE'):
        """Green requires a ready recipe; setup, pauses and pending checks are yellow."""
        status = self.find('run', 'StatusLabel', QLabel)
        status.setText(text)
        green = text == 'RECIPE REACHED' and self.last_metadata.get('pack_ready')
        red = any(term in text for term in ('REVIEW', 'OVER TARGET', 'ERROR', 'MISMATCH', 'NOT READY'))
        background = '#159447' if green else '#D32F2F' if red else '#B45309'
        status.setStyleSheet(f'background:{background};color:white;font-size:14px;'
                            'font-weight:bold;border-radius:8px;')
        self.find('run', 'PauseButton', QPushButton).setText(button_text)

    def queue_command(self, action):
        """Disable duplicate clicks until the worker acknowledges the command."""
        if not self.camera or not self.camera.isRunning() or self._command_pending:
            return False
        self._command_pending = True
        self.update_run_state()
        action()
        return True

    def pause_run(self):
        """Pause/resume on the processing thread, retaining the current box."""
        if self.box_started:
            self.queue_command(lambda: self.camera.set_active(not self.running))

    def undo(self):
        """Undo the last count action using the terminal program's ledger."""
        if self.box_started:
            self.queue_command(self.camera.undo)

    def verify_box(self):
        """Acknowledge a review only after checking the actual carton."""
        answer = QMessageBox.question(self.window, 'Review Box',
            'Have you checked the physical carton? This clears review flags; it does not change counts.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.queue_command(self.camera.acknowledge_review)

    def finish_box(self):
        """Freeze the worker before reading and saving its final counts."""
        if not self.model_ready or self.pipeline_recipe != self.config:
            return
        if not self.box_started:
            self.queue_command(self.camera.start_box)
        elif self.queue_command(self.camera.freeze_box):
            self._finishing = True
            self.set_run_status('FINISHING BOX')

    @Slot(str, object)
    def on_worker_command(self, command, result):
        """Use the worker's final snapshot, never a cached preview count."""
        if self.sender() is not None and self.sender() is not self.camera:
            return
        self._command_pending = False
        self.apply_snapshot(result['counts'], result['metadata'])
        self.running = result['active']
        if command == 'start':
            self.box_started = True
            self.elapsed = 0
            self.find('run', 'RunTimerLabel', QLabel).setText('Run Time: 00:00:00')
            self.finish_button.setText('FINISH BOX')
        if self.running:
            self.timer.start(1000)
        else:
            self.timer.stop()
        if command == 'finish':
            self.save_finished_box()
        self.update_run_state()

    def save_finished_box(self):
        """Save a frozen carton and wait for an explicit Start Next Box action."""
        try:
            if not sum(self.counts.values()):
                answer = QMessageBox.question(self.window, 'No Cans Counted',
                    'No cans were counted. Save this box as FAIL?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            status = inspection_status(self.config, self.counts, self.last_metadata)
            record = save_box(self.history_file, self.selected_recipe, self.config,
                              self.counts, mode='PI-VISION-ROI', status_override=status)
            self.completed_packs += int(record['Status'] == 'PASS')
            self.box_started = False
            self.finish_button.setText('START NEXT BOX')
            self.refresh_counts()
            QMessageBox.information(self.window, 'Box Saved',
                f'Status: {status}\nRed: {self.counts["Red"]}  Green: {self.counts["Green"]}  '
                f'Blue: {self.counts["Blue"]}\n\nPosition the next carton and clear the count area. '
                'Press START NEXT BOX when ready.')
        except OSError as error:
            QMessageBox.warning(self.window, 'Box Not Saved',
                                str(error) + '\nThe box is paused. Retry FINISH BOX after fixing the save location.')
        finally:
            self._finishing = False

    def confirm_discard_box(self):
        """Ask before leaving an unsaved box with counted cans."""
        if not self.box_started or not sum(self.counts.values()):
            return True
        answer = QMessageBox.question(self.window, 'Discard Current Box?',
            'This box has not been saved. Leave and discard its counts?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def stop_camera(self):
        """Wait for worker cleanup; retain its reference if hardware is still busy."""
        if self.camera is not None:
            if not self.camera.stop():
                QMessageBox.warning(self.window, 'Station Is Still Closing',
                    'The camera/model has not finished closing. Wait a moment and try again.')
                return False
            self.camera = None
        return True

    def stop_run(self):
        """Release camera, Hailo and GPIO before returning to the home screen."""
        if not self.confirm_discard_box() or not self.stop_camera():
            return
        self.timer.stop()
        self.running = False
        self.show('home')

    def wrong_can(self):
        """Explain the current count policy when the inspection help is opened."""
        QMessageBox.information(self.window, 'Counting',
            'Confirmed cans in the yellow area are counted as packed. '
            'The left defect line subtracts removed cans. Check the actual carton if a review is shown.')

    def shutdown(self):
        """Close the hardware before Qt destroys the application."""
        if self.current == 'run' and not self.confirm_discard_box():
            return False
        if not self.stop_camera():
            return False
        self.timer.stop()
        return True


def parse_arguments(argv=None):
    """Use the same station/config/GPIO options as the terminal Pi runner."""
    parser = argparse.ArgumentParser(description='Yards Pi touchscreen and shared vision counter')
    parser.add_argument('--source', '--camera', type=int, default=None, help='USB camera index')
    parser.add_argument('--vision-root', type=Path, default=VISION_ROOT)
    parser.add_argument('--backend', choices=['hailo', 'onnx', 'auto'], default='hailo')
    parser.add_argument('--model', type=Path)
    parser.add_argument('--config-dir', type=Path)
    parser.add_argument('--runtime-config', type=Path)
    parser.add_argument('--color-config', type=Path)
    parser.add_argument('--view-config', type=Path)
    parser.add_argument('--gpio', action='store_true')
    parser.add_argument('--gpio-active-low', action='store_true')
    parser.add_argument('--gpio-chip', type=int)
    parser.add_argument('--camera-format', choices=['MJPG', 'YUYV'])
    parser.add_argument('--camera-width', type=int)
    parser.add_argument('--camera-height', type=int)
    parser.add_argument('--camera-fps', type=float)
    parser.add_argument('--preview-fps', type=float)
    parser.add_argument('--output', type=Path, help='Private observations/timing folder')
    parser.add_argument('--windowed', action='store_true', help='Open a resizable window instead of fullscreen')
    args = parser.parse_args(argv)
    if (args.gpio_active_low or args.gpio_chip is not None) and not args.gpio:
        parser.error('--gpio-active-low and --gpio-chip require --gpio')
    for name in ('camera_width', 'camera_height', 'camera_fps'):
        if getattr(args, name) is not None and getattr(args, name) <= 0:
            parser.error('--' + name.replace('_', '-') + ' must be positive')
    if args.preview_fps is not None and args.preview_fps < 0:
        parser.error('--preview-fps must be zero or positive')
    return args


def main(argv=None):
    """Launch on the Pi desktop using its existing Hailo Python environment."""
    args = parse_arguments(argv)
    app = QApplication(sys.argv[:1])
    options = dict(config_dir=args.config_dir, runtime=args.runtime_config,
                   colors=args.color_config, view=args.view_config, gpio=args.gpio,
                   gpio_active_low=args.gpio_active_low, gpio_chip=args.gpio_chip,
                   output=args.output)
    camera = {key: value for key, value in
              dict(camera_format=args.camera_format, frame_width=args.camera_width,
                   frame_height=args.camera_height, camera_fps=args.camera_fps,
                   preview_fps=args.preview_fps).items() if value is not None}
    try:
        hmi = HMI(camera_source=args.source, vision_root=args.vision_root,
                  backend=args.backend, model=args.model, vision_options=options,
                  camera_settings=camera, windowed=args.windowed)
    except (OSError, ValueError, RuntimeError) as error:
        QMessageBox.critical(None, 'Station Setup', str(error))
        return 1
    # Holding hmi here keeps its QObject and windows alive for the event loop.
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
