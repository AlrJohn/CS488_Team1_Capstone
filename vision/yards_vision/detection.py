"""HSV segmentation detects colored regions, not guaranteed physical can identities."""

from dataclasses import dataclass
import cv2
import numpy as np

from .config import COLORS

BGR = {"red": (45, 45, 235), "green": (50, 210, 65), "blue": (235, 110, 45)}


@dataclass(frozen=True)
class Detection:
    color: str
    center: tuple
    box: tuple  # normalized x/y/width/height
    area: float


def color_mask(hsv, color):
    """Circular hue interval, including red's wrap from 179 back to 0."""
    hue = hsv[:, :, 0].astype(np.int16)
    distance = np.abs(hue - color.hue)
    distance = np.minimum(distance, 180 - distance)
    selected = (distance <= color.tolerance) & (hsv[:, :, 1] >= color.saturation_min) & (hsv[:, :, 2] >= color.value_min)
    return selected.astype(np.uint8) * 255


def detect(frame, settings, mode="picks"):
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    x, y, w, h = settings.roi
    x0, y0 = round(x * width), round(y * height)
    x1, y1 = min(width, round((x + w) * width)), min(height, round((y + h) * height))
    roi_mask = np.zeros((height, width), np.uint8)
    roi_mask[y0:y1, x0:x1] = 255
    kernel = np.ones((settings.morphology_size, settings.morphology_size), np.uint8)
    detections, warnings, masks = [], [], {}
    for name in COLORS:
        mask = cv2.bitwise_and(color_mask(hsv, settings.colors[name]), roi_mask)
        if settings.morphology_size > 1:
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            mask = cv2.bitwise_and(mask, roi_mask)
        masks[name] = mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour) / (width * height)
            if area < settings.min_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(contour)
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            center = (moments["m10"] / moments["m00"] / width, moments["m01"] / moments["m00"] / height)
            fill = cv2.contourArea(contour) / (bw * bh)
            if area > settings.max_area or fill < settings.min_fill or not 0.18 <= bw / bh <= 5.0:
                # Live counts inspect the transfer area; staged checks must
                # resolve every significant region throughout the entire ROI.
                signed = settings.distance(center) * (1 if settings.distance(settings.packing_point) > 0 else -1)
                box = (bx / width, by / height, bw / width, bh / height)
                if mode == "staged" or signed > -settings.hysteresis * 2 and settings.overlaps_transfer(box):
                    warnings.append(f"Unresolved {name} region in the inspection area: check for a group, occlusion, or background color")
                continue
            detections.append(Detection(name, center, (bx / width, by / height, bw / width, bh / height), area))
    return detections, masks, warnings
