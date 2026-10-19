"""Prepare Hailo RGB calibration input from a private TRAINING image folder."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.geometry import letterbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-images', required=True, type=Path,
        help='Training split only, already cropped to the intended runtime view; never validation/test footage')
    parser.add_argument('--output', type=Path, default=ROOT/'runs/build/calibration-rgb.npy')
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.json').exists():
        parser.error('Preserve existing calibration; choose a new output path.')
    images = sorted(p for p in args.train_images.rglob('*')
                    if p.suffix.lower() in {'.jpg','.jpeg','.png','.bmp'})
    if not images:
        parser.error('No training images found.')
    frames, sources = [], []
    for p in images:
        frame = cv2.imread(str(p))
        if frame is None:
            raise ValueError('Cannot read training image: ' + str(p))
        rgb, _ = letterbox(frame, (320,640))
        frames.append(rgb)
        sources.append({'path':str(p.relative_to(args.train_images)),
                        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, np.stack(frames).astype(np.uint8))
    args.output.with_suffix('.json').write_text(json.dumps(dict(
        role='Training-only INT8 calibration; not fine-tuning or evaluation',
        shape=[len(frames),320,640,3], sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        input_order='RGB',input_range=[0,255],sources=sources),indent=2)+'\n')
    print(f'Saved {len(frames)} training images to {args.output}')


if __name__ == '__main__':
    main()
