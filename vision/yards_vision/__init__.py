"""Compatibility import for the archived color-only prototype.

The implementation is in legacy/color_baseline/yards_vision. Current counters
start at windows/run.py or pi/run.py and use common/ instead.
"""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[1] / 'legacy/color_baseline/yards_vision')]
