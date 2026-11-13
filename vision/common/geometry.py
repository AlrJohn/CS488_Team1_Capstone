"""Image and box coordinates shared by ONNX and Hailo inference.

CS488 Capstone, Team 1.
"""

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class Transform:
    """Store source size, network size, resize gain and letterbox padding."""

    original: tuple
    network: tuple
    gain: float
    padding: tuple


def letterbox(bgr, shape=(320, 640)):
    """Resize and pad a BGR image; return RGB pixels and the coordinate transform."""
    source_height, source_width = bgr.shape[:2]
    network_height, network_width = shape
    gain = min(network_height / source_height, network_width / source_width)
    resized_height, resized_width = round(source_height * gain), round(source_width * gain)
    left, top = (
        round((network_width - resized_width) / 2 - 0.1),
        round((network_height - resized_height) / 2 - 0.1),
    )
    resized = (
        cv2.resize(bgr, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        if (resized_width, resized_height) != (source_width, source_height)
        else bgr
    )
    padded = cv2.copyMakeBorder(
        resized,
        top,
        network_height - resized_height - top,
        left,
        network_width - resized_width - left,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    return cv2.cvtColor(padded, cv2.COLOR_BGR2RGB), Transform(
        (source_height, source_width), shape, gain, (left, top)
    )


class Boxes:
    """NumPy-only subset of Ultralytics Boxes used by the frozen ByteTracker."""

    def __init__(self, data, shape):
        """Store detection rows as x0, y0, x1, y1, confidence and class."""
        self.data = np.asarray(data, dtype=np.float32).reshape(-1, 6)
        self.orig_shape = tuple(shape)

    def __len__(self):
        """Return the number of detections."""
        return len(self.data)

    def __getitem__(self, index):
        """Return a Boxes object containing the selected detection rows."""
        return Boxes(self.data[index], self.orig_shape)

    @property
    def xyxy(self):
        """Return detection corners in source-image pixels."""
        return self.data[:, :4]

    @property
    def xywh(self):
        """Return centers, widths and heights in source-image pixels."""
        x = self.xyxy
        y = np.empty_like(x)
        y[:, :2] = (x[:, :2] + x[:, 2:]) / 2
        y[:, 2:] = x[:, 2:] - x[:, :2]
        return y

    @property
    def conf(self):
        """Return confidence scores in detection order."""
        return self.data[:, 4]

    @property
    def cls(self):
        """Return class indices in detection order."""
        return self.data[:, 5]


def restore_view(config, shape):
    """Convert normalized ROI settings to pixels, rejecting invalid or tiny areas."""
    frame_height, frame_width = shape
    normalized_roi = config["normalized_xywh"]
    if (
        len(normalized_roi) != 4
        or not all(
            type(v) in (float, int) and np.isfinite(v) and 0 <= v <= 1 for v in normalized_roi
        )
        or min(normalized_roi[2:]) <= 0
        or normalized_roi[0] + normalized_roi[2] > 1.00001
        or normalized_roi[1] + normalized_roi[3] > 1.00001
    ):
        raise ValueError("Invalid normalized count ROI")
    roi_x, roi_y, roi_width, roi_height = [
        round(a * b)
        for a, b in zip(normalized_roi, (frame_width, frame_height, frame_width, frame_height))
    ]
    roi_width, roi_height = (
        min(roi_width, frame_width - roi_x),
        min(roi_height, frame_height - roi_y),
    )
    if min(roi_width, roi_height) < 40:
        raise ValueError("Count ROI too small")
    return [roi_x, roi_y, roi_width, roi_height]
