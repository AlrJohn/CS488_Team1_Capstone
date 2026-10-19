"""Compatibility entry point for the earlier color-only prototype."""
import sys
from yards_vision.app import main

if __name__ == '__main__':
    print('Legacy color-only prototype. Current can counter: python vision/windows/run.py', file=sys.stderr)
    raise SystemExit(main())
