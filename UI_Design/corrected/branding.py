"""Load the same Yards logo for Designer pages and the history screen."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

LOGO = Path(__file__).resolve().with_name('yards_logo.png')


def logo_label(parent, width=150, height=51):
    """Reuse an existing Designer label or create one, preserving image proportions."""
    label = parent.findChild(QLabel, 'yardsLogoLabel')
    if label is None:
        label = QLabel(parent)
        label.setObjectName('yardsLogoLabel')
    pixmap = QPixmap(str(LOGO))
    if pixmap.isNull():
        raise RuntimeError('Cannot load Yards logo: ' + str(LOGO))
    label.setFixedSize(width, height)
    label.setScaledContents(False)
    label.setPixmap(pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet('background:transparent;border:none;')
    label.setAccessibleName('Yards Brewing Company logo')
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return label
