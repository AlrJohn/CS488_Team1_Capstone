"""Conservative duplicate-mask handling and explicit target/review states."""
from collections import Counter
import numpy as np


def deduplicate(masks, labels, confidence, threshold=.95):
    """Collapse almost identical same-color masks, preserving touching cans.

    Conflicting or unknown colors stay unresolved. No hand/unknown detection is
    discarded just because it prevents a desired count.
    """
    keep=[];duplicates=[]
    order=sorted(range(len(masks)),key=lambda i:float(confidence[i]),reverse=True)
    areas=[int(mask.sum()) for mask in masks]
    for index in order:
        duplicate=None
        for other in keep:
            if labels[index]=='unknown' or labels[index]!=labels[other]:continue
            intersection=int(np.logical_and(masks[index],masks[other]).sum())
            if intersection/max(1,min(areas[index],areas[other]))>=threshold:
                # Large containment alone could hide a small rear can. Demand
                # comparable mask area as well as nearly identical pixels.
                if min(areas[index],areas[other])/max(1,max(areas[index],areas[other]))>=.60:
                    duplicate=other;break
        if duplicate is None:keep.append(index)
        else:duplicates.append({'removed_detection':index,'kept_detection':duplicate,'reason':'near-identical same-color instance masks'})
    return sorted(keep),duplicates


def target_status(confirmed,recipe):
    counts=Counter(item['color'] for item in confirmed.values())
    expected=Counter({c:n for c,n in recipe.items() if n})
    known=Counter({c:counts[c] for c in ('red','green','blue') if counts[c]})
    if counts==expected:return 'TARGET PATTERN CONFIRMED'
    if known==expected and counts['unknown']:return 'TARGETS OBSERVED / REVIEW: UNKNOWN EXTRA'
    if any(counts[c]>recipe[c] for c in ('red','green','blue')):return 'REVIEW: EXTRA COLORED CANDIDATE'
    return 'WAIT: NEED MORE TARGET EVIDENCE'
