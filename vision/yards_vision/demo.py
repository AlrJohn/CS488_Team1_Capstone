"""Deterministic artificial motion for exercising the app without a camera."""

import cv2
import numpy as np


def _move(index, start, stop, left, right):
    return left + (right - left) * min(max((index - start) / (stop - start), 0), 1)


def demo_frame(index, width=640, height=480):
    frame = np.full((height, width, 3), 32, np.uint8)
    red = 0.22
    if 25 <= index < 76:
        red = _move(index, 25, 65, 0.22, 1.13)
    elif 76 <= index < 116:
        red = _move(index, 76, 106, 1.13, 0.22)
    elif index >= 116:
        red = _move(index, 116, 151, 0.22, 1.13)
    green = _move(index, 155, 190, 0.22, 1.13)
    blue = _move(index, 195, 230, 0.22, 1.13)
    for name, x, y, color in [("red", red, 0.25, (0, 0, 220)), ("green", green, 0.5, (0, 190, 0)), ("blue", blue, 0.75, (220, 0, 0))]:
        if x < 1.1:
            center = (round(x * width), round(y * height))
            cv2.ellipse(frame, center, (18, 29), 0, 0, 360, color, -1)
    return frame


DEMO_FRAMES = 270
