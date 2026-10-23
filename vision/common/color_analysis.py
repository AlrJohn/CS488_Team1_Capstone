"""Classify label color inside a can mask, with a fallback for white labels."""
import cv2
import numpy as np

from .settings import InteriorSampling, SideSampling

COLORS = ("red", "green", "blue")


def _measure_colors(hsv, sample, settings, *, min_pixels, min_coverage,
                    min_dominance, min_row_fraction=0.):
    """Count matching HSV pixels and check the requested evidence limits.

    Side sampling also checks how many image rows contain at least two
    matching pixels. This prevents a small colored logo or fleck from being
    sufficient evidence by itself. No pixels outside the mask can vote.
    """
    count = int(np.count_nonzero(sample))
    votes = dict.fromkeys(COLORS, 0)
    matches = {}
    if count:
        pixels = hsv[sample]
        hue = pixels[:, 0].astype(np.int16)
        for name in COLORS:
            limits = settings.colors[name]
            delta = np.abs(hue-limits.hue)
            matches[name] = (np.minimum(delta, 180-delta) <= limits.tolerance) & (
                pixels[:, 1] >= limits.saturation_min) & (pixels[:, 2] >= limits.value_min)
            votes[name] = int(np.count_nonzero(matches[name]))
    winner = max(votes, key=votes.get)
    coverage = votes[winner]/max(1, count)
    dominance = votes[winner]/max(1, sum(votes.values()))
    enough = votes[winner] >= min_pixels and coverage >= min_coverage and dominance >= min_dominance
    reason = ("confirmed label pixels" if enough else "too few colored pixels" if votes[winner] < min_pixels
              else "too little label coverage" if coverage < min_coverage else "mixed color votes")
    result = dict(color=winner if enough else "unknown", reason=reason,
                  sample_pixels=count, votes=votes, coverage=coverage, dominance=dominance)
    if min_row_fraction:
        rows = np.nonzero(sample)[0]
        supported = np.zeros(sample.shape[0], dtype=bool)
        if count:
            supported = np.bincount(rows[matches[winner]], minlength=sample.shape[0]) >= 2
        fraction = float(np.count_nonzero(supported)/max(1, sample.shape[0]))
        result['supported_row_fraction'] = fraction
        if enough and fraction < min_row_fraction:
            result.update(color='unknown', reason='color limited to a small patch')
    return result


def _sample_sides(hsv, body, settings, policy):
    """Check left and right body bands without overriding conflicting colors.

    Either side may supply the evidence when the other is white or hidden.
    Both bands stay inside the eroded can mask and exclude the top/bottom.
    """
    width = body.shape[1]
    band_width = max(1, int(width*policy.band_fraction))
    bands = []
    for name, start, stop in [('left', 0, band_width), ('right', width-band_width, width)]:
        sample = np.zeros_like(body)
        sample[:, start:stop] = body[:, start:stop]
        evidence = _measure_colors(hsv, sample, settings, min_pixels=policy.min_pixels,
                                   min_coverage=policy.min_coverage, min_dominance=policy.min_dominance,
                                   min_row_fraction=policy.min_row_fraction)
        bands.append((name, sample, evidence))
    accepted = {evidence['color'] for _, _, evidence in bands if evidence['color'] != 'unknown'}
    # Coverage is checked per band: a white opposite side must not dilute a
    # valid strip. The pooled colored votes must still agree on one color.
    combined = _measure_colors(hsv, bands[0][1] | bands[1][1], settings,
                               min_pixels=policy.min_pixels, min_coverage=0.,
                               min_dominance=policy.min_dominance, min_row_fraction=policy.min_row_fraction)
    if len(accepted) > 1:
        combined.update(color='unknown', reason='conflicting side colors')
    elif not accepted:
        combined.update(color='unknown', reason='neither side has enough consistent color')
    elif combined['color'] not in accepted:
        combined.update(color='unknown', reason='side colors do not agree')
    return combined, {name: evidence for name, _, evidence in bands}


def sample_colors(frame, masks, settings, interior=True):
    """Return a color and diagnostic evidence for each individual can mask.

    Args:
        frame: BGR image in the same coordinates as the masks.
        masks: Binary can masks, one per detection.
        settings: HSV ranges, ordinary evidence limits and side-fallback controls.
        interior: Use the usual interior check, then a side fallback if needed.

    Returns:
        Labels and matching dictionaries explaining the sampling and color votes.
        Both checks use their configured evidence limits from the color profile.
    """
    labels, diagnostics = [], []
    kernel = np.ones((3, 3), np.uint8)
    ordinary = getattr(settings, 'interior_sampling', None) or InteriorSampling()
    policy = getattr(settings, 'side_sampling', None) or SideSampling()
    for raw in masks:
        full_mask = np.asarray(raw, dtype=np.uint8)
        x, y, width, height = cv2.boundingRect(full_mask)
        mask = full_mask[y:y+height, x:x+width]
        sample = mask > 0
        used_core = False
        body = np.zeros_like(sample)
        if interior and width and height:
            eroded = cv2.erode(mask, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
            # Keep the existing vertical margins away from silver rims and bases.
            top, bottom = round(height*.12), height-round(height*.10)
            body[top:bottom] = eroded[top:bottom]
            core = np.zeros_like(sample)
            core[:, round(width*.04):width-round(width*.04)] = body[:, round(width*.04):width-round(width*.04)]
            if int(core.sum()) >= max(100, int(sample.sum())*.25):
                sample, used_core = core, True
        # HSV conversion remains restricted to this can's bounding rectangle.
        hsv = cv2.cvtColor(frame[y:y+height, x:x+width], cv2.COLOR_BGR2HSV) if sample.any() else np.empty((0, 0, 3), np.uint8)
        evidence = _measure_colors(hsv, sample, settings, min_pixels=ordinary.min_pixels,
                                   min_coverage=ordinary.min_coverage, min_dominance=ordinary.min_dominance)
        evidence.update(interior_sample=used_core, sampling_method='interior' if used_core else 'full_mask')
        # White printing may hide most color or leave strips outside the normal
        # four-percent trim. Do not override an already confirmed/mixed result.
        if (interior and policy.enabled and width >= 4 and body.any() and evidence['color'] == 'unknown'
                and evidence['reason'] != 'mixed color votes'):
            side_evidence, bands = _sample_sides(hsv, body, settings, policy)
            if side_evidence['color'] != 'unknown':
                primary = evidence
                evidence = dict(side_evidence, interior_sample=True, sampling_method='side_bands',
                                primary_analysis=primary)
            evidence['side_analysis'] = dict(result=side_evidence, bands=bands)
        labels.append(evidence['color'])
        diagnostics.append(evidence)
    return labels, diagnostics
