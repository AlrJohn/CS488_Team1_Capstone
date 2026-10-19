"""Camera opening and recording orientation helpers from the Windows prototype."""
import json
from pathlib import Path
import sys
import cv2
import numpy as np

def has_image_signal(frame):
    """Reject empty/constant backend frames; this does not assess lighting quality."""
    return frame is not None and frame.size > 0 and int(np.ptp(frame)) > 3

def orientation_path(path):
    path = Path(path)
    return path.with_suffix(path.suffix + ".orientation.json")

def recorded_rotation(path):
    metadata = orientation_path(path)
    if not metadata.exists():
        return False  # Older recordings contain the original camera view.
    data = json.loads(metadata.read_text(encoding="utf-8"))
    if data.get("version") != 1 or type(data.get("rotate_180")) is not bool:
        raise ValueError(f"Invalid recording orientation in {metadata}")
    return data["rotate_180"]

def orient_frame(frame, target_rotation, source_rotation=False):
    # A recorded file may already contain the correction. Apply only the
    # difference so replay uses the same coordinates as the saved calibration.
    return cv2.rotate(frame, cv2.ROTATE_180) if target_rotation != source_rotation else frame

def open_source(source, backend, width, height):
    camera = source.isdecimal()
    value = int(source) if camera else source
    apis = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}
    if not camera:
        backends = [cv2.CAP_ANY]
    elif backend != "auto":
        backends = [apis[backend]]
    elif sys.platform == "win32":
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY]
    blank_camera = False
    for api in backends:
        capture = cv2.VideoCapture(value, api)
        if not capture.isOpened():
            capture.release()
            continue
        if camera:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Some backends report success but deliver a constant gray image.
            # Allow startup frames, then reject that source instead of showing
            # an apparently working inspection window with no camera evidence.
            visible = False
            for _ in range(30):
                ok, frame = capture.read()
                if ok and has_image_signal(frame):
                    visible = True
                    break
            if not visible:
                blank_camera = True
                capture.release()
                continue
        return capture, camera
    if blank_camera:
        raise RuntimeError(f"Source {source!r} opened but delivered no usable image. Check the lens, lighting, and camera backend; try --backend dshow from the VS Code terminal.")
    raise RuntimeError(f"Cannot open source {source!r}. Close other camera apps, check Windows camera permissions, or try --source 1 / --backend msmf.")
