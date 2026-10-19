"""Classify label color inside an instance mask and explain uncertain votes."""
import cv2
import numpy as np

COLORS = ("red", "green", "blue")


def sample_colors(frame, masks, settings, interior=True):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16)
    selected = {}
    for name in COLORS:
        limits = settings.colors[name]
        delta = np.abs(hue-limits.hue)
        selected[name] = (np.minimum(delta, 180-delta) <= limits.tolerance) & (
            hsv[:, :, 1] >= limits.saturation_min) & (hsv[:, :, 2] >= limits.value_min)
    labels, diagnostics = [], []
    kernel = np.ones((3, 3), np.uint8)
    for raw in masks:
        mask = raw.astype(np.uint8)
        sample = mask > 0
        used_core = False
        if interior and sample.any():
            yy, xx = np.where(sample)
            x0, x1, y0, y1 = int(xx.min()), int(xx.max())+1, int(yy.min()), int(yy.max())+1
            eroded = cv2.erode(mask, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0)>0
            core = np.zeros_like(sample)
            # Reduce finger/rim/boundary contamination while retaining most of
            # the can body. Small or heavily occluded masks use the full mask.
            core[y0+round((y1-y0)*.12):y1-round((y1-y0)*.10),
                 x0+round((x1-x0)*.04):x1-round((x1-x0)*.04)] = True
            core &= eroded
            if int(core.sum()) >= max(100, int(sample.sum())*.25):
                sample, used_core = core, True
        count = int(sample.sum())
        votes = {name:int((sample & pixels).sum()) for name,pixels in selected.items()}
        winner = max(votes,key=votes.get)
        coverage = votes[winner]/max(1,count)
        dominance = votes[winner]/max(1,sum(votes.values()))
        enough = votes[winner]>=25 and coverage>=.10 and dominance>=.60
        labels.append(winner if enough else "unknown")
        reason = "confirmed label pixels" if enough else "too few colored pixels" if votes[winner]<25 else "too little label coverage" if coverage<.10 else "mixed color votes"
        diagnostics.append({"color":labels[-1],"reason":reason,"sample_pixels":count,
            "interior_sample":used_core,"votes":votes,"coverage":coverage,"dominance":dominance})
    return labels,diagnostics
