"""Record the displayed inspection view as a timed H.264 presentation clip."""

import math
from pathlib import Path
import subprocess
import sys

import numpy as np


def encoder_executable():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError as exc:
        raise RuntimeError("Presentation recording needs imageio-ffmpeg. Install vision/requirements-presentation.txt with this Python interpreter.") from exc
    return get_ffmpeg_exe()


class PresentationRecorder:
    """Sample the actual displayed views at 30 fps without changing their timing."""

    def __init__(self, path, executable, fps=30):
        self.path = Path(path)
        if self.path.exists():
            raise ValueError(f"Presentation recording already exists: {self.path}")
        self.executable, self.fps = executable, fps
        self.process = None
        self.previous = None
        self.origin = self.last_timestamp = None
        self.frames = 0
        self.closed = False

    def _open(self, frame):
        height, width = frame.shape[:2]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.executable, "-hide_banner", "-loglevel", "error", "-n",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
                   "-r", str(self.fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                   "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p",
                   "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-movflags", "+faststart", str(self.path)]
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, **options)

    def _write(self, frame):
        try:
            self.process.stdin.write(np.ascontiguousarray(frame).tobytes())
        except OSError as exc:
            raise RuntimeError("Presentation encoder stopped accepting frames.") from exc
        self.frames += 1

    def add(self, frame, timestamp):
        if self.closed:
            raise ValueError("Presentation recording is already closed.")
        if not math.isfinite(timestamp) or self.last_timestamp is not None and timestamp < self.last_timestamp:
            raise ValueError("Presentation timestamps must be finite and nondecreasing.")
        if self.previous is None:
            self._open(frame)
            self.origin = timestamp
        else:
            if frame.shape != self.previous.shape:
                raise ValueError("Presentation frame dimensions changed during the recording.")
            # Hold the earlier displayed view until the next one actually arrived.
            # Camera throughput can differ from its reported recording frame rate.
            while self.frames / self.fps < timestamp - self.origin - 1e-9:
                self._write(self.previous)
        self.previous = frame.copy()
        self.last_timestamp = timestamp

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process is None:
            return
        try:
            end_frame = math.ceil((self.last_timestamp - self.origin) * self.fps - 1e-9) + 1
            while self.frames < end_frame:
                self._write(self.previous)
        finally:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired as exc:
                self.process.kill()
                self.process.wait()
                raise RuntimeError("Presentation encoder did not finish in time.") from exc
            finally:
                errors = self.process.stderr.read().decode("utf-8", errors="replace")
                self.process.stderr.close()
            if self.process.returncode:
                raise RuntimeError(f"Presentation encoder failed: {errors.strip()}")
