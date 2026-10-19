"""PyTorch can inference and mask rendering used by the Windows counter."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import time
import cv2
import numpy as np
from common.torch_support import setup
torch = setup()
from ultralytics import YOLO
from common.geometry import Boxes
from common.settings import Settings, parse_recipe
from common.camera import has_image_signal, open_source, orient_frame, recorded_rotation
from common.observer import Observer, TRACKER
from common.color_analysis import sample_colors
from common.instance_quality import deduplicate
from common.video import encoder_executable
BGR = {'red': (0,0,255), 'green': (0,230,0), 'blue': (255,110,40)}
COLORS = ('red','green','blue')

def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verified_model(path):
    """Resolve a local inference checkpoint and check its recorded identity."""
    path = path.resolve()
    identity_file = path.with_suffix('.json')
    if path.suffix.lower() != '.pt' or not path.is_file() or not identity_file.is_file():
        raise ValueError('Model requires a local .pt checkpoint and its matching .json metadata')
    identity = json.loads(identity_file.read_text(encoding='utf-8'))
    actual_hash = digest(path)
    if actual_hash != identity.get('sha256'):
        raise ValueError('Selected model hash does not match its metadata')
    if identity.get('task') != 'segment' or identity.get('classes') != {'0': 'can'}:
        raise ValueError('Selected model must be a one-class can instance segmenter')
    return path, actual_hash

def annotate(frame, roi, masks, observed, confirmed, state, recipe, fps, elapsed_ms,
             seen, frame_index, window_seconds, trial_info=None):
    x, y, w, h = roi
    view = frame.copy()
    region = view[y:y+h, x:x+w]
    tint = region.copy()
    for mask, item in zip(masks, observed):
        tint[mask > 0] = BGR.get(item["color"], (170, 170, 170))
    region[:] = cv2.addWeighted(region, .70, tint, .30, 0)
    for mask, item in zip(masks, observed):
        color = BGR.get(item["color"], (170, 170, 170))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(region, contours, -1, color, 2)
        bx, by, ex, ey = np.rint(item["xyxy_roi"]).astype(int)
        identity = item["track_id"]
        label = f"T{identity}" if identity is not None else "untracked"
        label += f" {item['color']} {item['confidence']:.2f}"
        if item.get('color_analysis') and item['color'] == 'unknown':
            label += ' (' + item['color_analysis']['reason'] + ')'
        if identity in confirmed:
            label += f" [{confirmed[identity]['observations']}/5]"
        cv2.rectangle(region, (bx, by), (ex, ey), color, 1)
        cv2.putText(region, label, (max(0, bx), max(18, by-5)), 0, .50,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(region, label, (max(0, bx), max(18, by-5)), 0, .50,
                    (255, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(view, (x, y), (x+w-1, y+h-1), (0, 220, 255), 2)
    width = max(960, frame.shape[1])
    canvas = np.full((frame.shape[0]+164, width, 3), 24, np.uint8)
    canvas[132:132+frame.shape[0], :frame.shape[1]] = view
    totals = Counter(item["color"] for item in confirmed.values())
    expected = "/".join(str(recipe[c]) for c in COLORS)
    actual = "/".join(str(totals[c]) for c in COLORS)
    performance = (f'{fps:.1f} processed fps | model {elapsed_ms:.1f} ms'
                   if fps is not None and elapsed_ms is not None else 'cached replay; timing not measured')
    lines = [f"FINE-TUNED CAN MODEL | {state} | target R/G/B: {expected}",
             f"Observed now: {len(observed)} | 3-of-5 IDs R/G/B: {actual} | unknown: {totals['unknown']}",
             f"Pattern seen this trial: {'YES' if seen else 'NO'} | frame {frame_index} | {performance}",
             "P: start trial   N: finish/reset   O: select area (setup)   S: snapshot   Q: quit"]
    if trial_info is not None:
        target=trial_info['target_color']
        actual_count=trial_info['declared_actual_count']
        declared=str(actual_count) if actual_count is not None else 'choose 0-6'
        other=sum(n for c,n in totals.items() if c not in (target,'unknown'))
        lines=[f"FOUR-CAN TRIAL | {target.upper()} | target: 4 | actual: {declared} | {state}",
            f"Detected now: {len(observed)} | stable {target}: {totals[target]}/4 | other colors: {other} | unknown: {totals['unknown']}",
            f"Match seen: {'YES' if seen else 'NO'} | best stable: {trial_info['best_stable_target_count']} | frame {frame_index} | {performance}",
            'B/G/R: color   0-6: actual cans   P: record   N: save/reset   O: area   S: snapshot   Q: quit']
    for i, line in enumerate(lines):
        text_width=cv2.getTextSize(line,0,.59,1)[0][0]
        scale=.59*min(1.,(width-20)/max(1,text_width))
        cv2.putText(canvas, line, (10, 24+i*30), 0, scale, (240, 240, 240), 1, cv2.LINE_AA)
    detail = f" | last five processed images span {window_seconds:.3f}s" if window_seconds is not None else ""
    cv2.putText(canvas, "Presence evidence only; pickup / box placement NOT verified"+detail,
                (10, canvas.shape[0]-10), 0, .50, (0, 210, 255), 1, cv2.LINE_AA)
    return canvas

def predict(model, frame, settings, config, *, color_mode='v2', diagnostics=None,
            deduplicate_masks=False):
    if config["device"] != "cpu":
        torch.cuda.synchronize()
    started = time.perf_counter()
    result = model.predict(frame, classes=[0], **config)[0]
    if config["device"] != "cpu":
        torch.cuda.synchronize()
    elapsed = (time.perf_counter()-started)*1000
    masks = ((result.masks.data.cpu().numpy() > .5).astype(np.uint8)
             if result.masks is not None else np.zeros((0, *frame.shape[:2]), np.uint8))
    if masks.shape[1:] != frame.shape[:2]:
        raise RuntimeError("Predicted masks do not align with the image")
    color_start = time.perf_counter()
    labels, votes = sample_colors(frame, masks, settings, interior=True)
    color_ms = (time.perf_counter()-color_start)*1000
    boxes = Boxes(result.boxes.data.cpu().numpy(), frame.shape[:2])
    input_count = len(masks)
    keep = list(range(input_count))
    duplicates = []
    duplicate_start = time.perf_counter()
    if deduplicate_masks:
        keep, duplicates = deduplicate(masks, labels, boxes.conf)
        masks, boxes = masks[keep], boxes[keep]
        labels = [labels[i] for i in keep]
        if votes is not None:
            votes = [votes[i] for i in keep]
    duplicate_ms = (time.perf_counter()-duplicate_start)*1000
    if diagnostics is not None:
        diagnostics.update(color_analysis=votes, color_ms=color_ms,
                           deduplication_ms=duplicate_ms, input_detections=input_count,
                           retained_detection_indices=keep, suppressed_duplicates=duplicates)
    return masks, boxes, labels, elapsed
