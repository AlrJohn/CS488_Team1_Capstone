"""Camera configuration and delivery measurement without loading a model."""
import math
import sys
import time

import cv2
import numpy as np


def open_camera(source, width=1280, height=720, pixel_format='MJPG', fps=30.):
    """Open a USB camera and record requested and reported settings.

    Args:
        source: Numeric camera index.
        width: Requested image width.
        height: Requested image height.
        pixel_format: MJPG or YUYV camera format.
        fps: Requested frames per second; actual delivery is measured separately.

    Returns:
        The open capture device and a dictionary of settings and accepted requests.

    Raises:
        ValueError: A requested dimension, rate or format is invalid.
        RuntimeError: The camera cannot be opened.
    """
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise ValueError('Camera dimensions must be positive integers')
    if not math.isfinite(fps) or fps <= 0 or pixel_format not in ('MJPG', 'YUYV'):
        raise ValueError('Use a positive camera rate and MJPG or YUYV format')
    api = cv2.CAP_V4L2 if sys.platform.startswith('linux') else cv2.CAP_ANY
    capture = cv2.VideoCapture(int(source), api)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError('Could not open camera ' + str(source))
    try:
        requests = {
            'format': capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pixel_format)),
            'width': capture.set(cv2.CAP_PROP_FRAME_WIDTH, width),
            'height': capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height),
            'fps': capture.set(cv2.CAP_PROP_FPS, fps),
            'buffer': capture.set(cv2.CAP_PROP_BUFFERSIZE, 1),
        }
        fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
        info = {
            'requested_format': pixel_format, 'requested_fps': fps,
            'requested_size': [width, height], 'accepted_requests': requests,
            'actual_fourcc': ''.join(chr(fourcc >> (8*i) & 255) for i in range(4)),
            'reported_fps': capture.get(cv2.CAP_PROP_FPS),
            'actual_size': [capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)],
        }
        return capture, info
    except BaseException:
        capture.release()
        raise


def measure_delivery(capture, seconds=30., warmup_seconds=2., clock=time.perf_counter):
    """Measure camera reads after warmup, with no model, GUI or image writes.

    The result describes delivery to this process. It does not measure sensor
    timestamps, unique sensor exposures or time already spent in driver buffers.
    A blocked driver read may extend the requested test duration.
    """
    if not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(warmup_seconds) or warmup_seconds < 0:
        raise ValueError('Use a positive duration and nonnegative warmup')
    start = clock()
    while clock()-start < warmup_seconds:
        ok, _ = capture.read()
        if not ok:
            raise RuntimeError('Camera stopped during warmup')
    stamps = []
    start = clock()
    while clock()-start < seconds:
        ok, _ = capture.read()
        if not ok:
            raise RuntimeError('Camera stopped during delivery measurement')
        stamps.append(clock())
    elapsed = clock()-start
    intervals = np.diff(stamps)*1000
    return {
        'frames': len(stamps), 'elapsed_seconds': elapsed,
        'delivered_fps': (len(stamps)-1)/(stamps[-1]-stamps[0]) if len(stamps)>1 else None,
        'read_interval_ms': {'median': float(np.median(intervals)), 'p95': float(np.percentile(intervals, 95)),
                             'maximum': float(np.max(intervals))} if len(intervals) else None,
        'model_loaded': False, 'image_saving': False, 'preview_enabled': False,
        'timing_basis': 'Host camera read completion after warmup; not sensor timestamps',
    }
