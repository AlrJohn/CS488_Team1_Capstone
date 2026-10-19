"""Locate the FFmpeg executable used to finalize Windows trial videos."""
import shutil


def encoder_executable():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except ImportError:
        executable = shutil.which('ffmpeg')
        if executable:
            return executable
        raise RuntimeError('Install vision/windows/requirements.txt, or put FFmpeg on PATH.')
