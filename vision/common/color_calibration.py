"""Fit session HSV ranges from labeled can pixels and verify fresh examples.

This module has no camera, GUI, tracking or GPIO side effects. The Pi screen
collects samples here, then tests the proposed profile with sample_colors().
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from .settings import COLORS, Settings


@dataclass
class CalibrationPolicy:
    """Validated controls loaded from configs/calibration.json."""

    warmup_seconds: float
    probe_seconds: float
    collection_frames: int
    verification_frames: int
    sample_interval_seconds: float
    collection_timeout_seconds: float
    min_pixels_per_frame: int
    max_pixels_per_frame: int
    seed_radius: int
    saturation_floor: int
    value_floor: int
    seed_saturation_fraction: float
    seed_hue_window: int
    max_hue_shift: int
    min_hue_tolerance: int
    max_hue_tolerance: int
    hue_margin: int
    sv_margin: int
    lower_percentile: float
    hue_percentile: float
    minimum_fit_recall: float
    minimum_verification_accuracy: float
    maximum_wrong_frames: int

    def __post_init__(self):
        """Keep capture sizes bounded and reject unsafe or nonsensical limits."""
        integer_limits = {
            'collection_frames': (5, 300), 'verification_frames': (5, 300),
            'min_pixels_per_frame': (1, 10000), 'max_pixels_per_frame': (1, 10000),
            'seed_radius': (0, 20), 'saturation_floor': (1, 255), 'value_floor': (1, 255),
            'seed_hue_window': (1, 44), 'max_hue_shift': (1, 89),
            'min_hue_tolerance': (1, 44), 'max_hue_tolerance': (1, 44),
            'hue_margin': (0, 20), 'sv_margin': (0, 100), 'maximum_wrong_frames': (0, 300),
        }
        for name, (low, high) in integer_limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Invalid calibration setting: ' + name)
        for name in ('warmup_seconds', 'probe_seconds', 'sample_interval_seconds', 'collection_timeout_seconds',
                     'seed_saturation_fraction', 'lower_percentile', 'hue_percentile',
                     'minimum_fit_recall', 'minimum_verification_accuracy'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('Invalid calibration setting: ' + name)
        if (self.probe_seconds <= 0 or self.sample_interval_seconds <= 0
                or self.collection_timeout_seconds < self.collection_frames*self.sample_interval_seconds
                or not 0 < self.seed_saturation_fraction <= 1
                or not 0 < self.minimum_fit_recall <= 1 or not 0 < self.minimum_verification_accuracy <= 1
                or not 0 <= self.lower_percentile < 50 or not 50 < self.hue_percentile <= 100
                or self.min_pixels_per_frame > self.max_pixels_per_frame
                or self.min_hue_tolerance > self.max_hue_tolerance
                or self.maximum_wrong_frames >= self.verification_frames):
            raise ValueError('Inconsistent calibration settings')

    @classmethod
    def load(cls, path):
        """Load every fitting/capture control from the selected JSON file."""
        return cls(**json.loads(Path(path).read_text(encoding='utf-8')))


def hue_delta(values, center):
    """Return signed circular hue differences, including red's 179/0 boundary."""
    return (np.asarray(values, dtype=float)-center+90) % 180-90


def select_seed(frame, mask, point, policy):
    """Read a clicked colored patch inside the detected can, rejecting white.

    Args:
        frame: BGR image in the mask's coordinates.
        mask: One binary can mask.
        point: Clicked x/y image coordinates.
        policy: Pixel floors and patch size.

    Returns:
        A hue/saturation/value seed used to isolate that label's colored pixels.
    """
    x, y = point
    if not (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x]):
        raise ValueError('Click a colored part inside the detected can mask.')
    radius = policy.seed_radius
    left, top = max(0, x-radius), max(0, y-radius)
    hsv = cv2.cvtColor(frame[top:y+radius+1, left:x+radius+1], cv2.COLOR_BGR2HSV)
    center = hsv[y-top, x-left]
    if center[1] < policy.saturation_floor or center[2] < policy.value_floor:
        raise ValueError('That patch is white, gray or too dark. Click the colored label.')
    inside = mask[top:top+hsv.shape[0], left:left+hsv.shape[1]] > 0
    valid = inside & (hsv[:, :, 1] >= policy.saturation_floor) & (hsv[:, :, 2] >= policy.value_floor)
    valid &= np.abs(hue_delta(hsv[:, :, 0], float(center[0]))) <= policy.seed_hue_window
    pixels = hsv[valid]
    return dict(hue=int(round(float(center[0])+float(np.median(hue_delta(pixels[:, 0], float(center[0])))))) % 180,
                saturation=float(np.median(pixels[:, 1])), value=float(np.median(pixels[:, 2])))


def collect_pixels(frame, mask, seed, policy):
    """Collect a bounded set of colored body pixels from this observed image."""
    x, y, width, height = cv2.boundingRect(np.asarray(mask, dtype=np.uint8))
    if not width or not height:
        raise ValueError('No can mask is available.')
    crop = frame[y:y+height, x:x+width]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    inside = cv2.erode(mask[y:y+height, x:x+width].astype(np.uint8), np.ones((3, 3), np.uint8),
                       borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
    saturation = max(policy.saturation_floor, seed['saturation']*policy.seed_saturation_fraction)
    valid = inside & (hsv[:, :, 1] >= saturation) & (hsv[:, :, 2] >= policy.value_floor)
    valid &= np.abs(hue_delta(hsv[:, :, 0], seed['hue'])) <= policy.seed_hue_window
    pixels = hsv[valid]
    if len(pixels) < policy.min_pixels_per_frame:
        raise ValueError('Too few colored pixels. Keep a colored side visible and reduce glare.')
    indices = np.linspace(0, len(pixels)-1, min(len(pixels), policy.max_pixels_per_frame), dtype=int)
    return pixels[indices].copy()


def fit_profile(base, samples, seeds, policy):
    """Fit compact, non-overlapping HSV ranges without changing counting rules.

    Samples come only from the collection phase. Verification frames are never
    supplied to this function. Hue centers are circular medians around the seed;
    percentiles tolerate a small number of noisy pixels. All three colors are
    fitted together so widening one range cannot silently overlap another.
    """
    settings = Settings.from_dict(base)
    pixels, centers = {}, {}
    for name in COLORS:
        if len(samples.get(name, [])) < policy.collection_frames or name not in seeds:
            raise ValueError('Collect all required views of ' + name + ' first.')
        pixels[name] = np.concatenate(samples[name])
        centers[name] = int(round(seeds[name]['hue']+float(np.median(hue_delta(pixels[name][:, 0], seeds[name]['hue']))))) % 180
        if abs(float(hue_delta(centers[name], base['colors'][name]['hue']))) > policy.max_hue_shift:
            raise ValueError(name + ': hue shifted too far. Check the selected color, patch and lighting.')
    profile, report = deepcopy(base), {}
    # Make every effective color-evidence limit visible in saved profiles,
    # including when the input was an older/partial station configuration.
    profile['interior_sampling'] = asdict(settings.interior_sampling)
    profile['side_sampling'] = asdict(settings.side_sampling)
    for name in COLORS:
        values, center = pixels[name], centers[name]
        separation = min(abs(float(hue_delta(center, centers[other]))) for other in COLORS if other != name)
        cap = min(policy.max_hue_tolerance, math.floor(separation/2)-1)
        if cap < policy.min_hue_tolerance:
            raise ValueError('The sampled colors are too similar. Recheck the colored patches and lighting.')
        required = math.ceil(float(np.percentile(np.abs(hue_delta(values[:, 0], center)), policy.hue_percentile)))+policy.hue_margin
        tolerance = max(policy.min_hue_tolerance, min(required, cap))
        saturation = max(policy.saturation_floor, math.floor(float(np.percentile(values[:, 1], policy.lower_percentile)))-policy.sv_margin)
        brightness = max(policy.value_floor, math.floor(float(np.percentile(values[:, 2], policy.lower_percentile)))-policy.sv_margin)
        accepted = ((np.abs(hue_delta(values[:, 0], center)) <= tolerance)
                    & (values[:, 1] >= saturation) & (values[:, 2] >= brightness))
        recall = float(np.mean(accepted))
        if recall < policy.minimum_fit_recall:
            raise ValueError(name + ': samples vary too much for a distinct color range. Recollect under steady lighting.')
        profile['colors'][name] = dict(hue=center, tolerance=tolerance, saturation_min=saturation, value_min=brightness)
        report[name] = dict(frames=len(samples[name]), pixels=len(values), selected_pixel_recall=recall)
    Settings.from_dict(profile)
    return profile, report


class Verification:
    """Count all fresh verification observations, including unknown/missing cans."""

    def __init__(self, expected, policy):
        self.expected, self.policy, self.votes = expected, policy, Counter()

    def add(self, predicted):
        """Record one scheduled observation; never omit a failed recognition."""
        if sum(self.votes.values()) < self.policy.verification_frames:
            self.votes[predicted if predicted in COLORS else 'unknown'] += 1

    def summary(self):
        """Return frame accuracy and the configured pass decision."""
        total = sum(self.votes.values())
        correct = self.votes[self.expected]
        wrong = sum(self.votes[name] for name in COLORS if name != self.expected)
        passed = (total >= self.policy.verification_frames and correct/max(1, total) >= self.policy.minimum_verification_accuracy
                  and wrong <= self.policy.maximum_wrong_frames)
        return dict(total=total, correct=correct, wrong=wrong, unknown=self.votes['unknown'],
                    accuracy=correct/max(1, total), passed=passed, votes=dict(self.votes))


def save_profile(folder, profile, verification, report):
    """Save a new local profile only after all three fresh sequences pass.

    An exclusive create prevents overwriting any existing profile. Only compact
    settings/metrics are saved; no camera images or sampled pixel arrays.
    """
    if set(verification) != set(COLORS) or not all(item.summary()['passed'] for item in verification.values()):
        raise ValueError('Verify all three colors before saving.')
    Settings.from_dict(profile)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
    result = deepcopy(profile)
    result['calibration'] = dict(report, saved_utc=stamp, verification={name: verification[name].summary() for name in COLORS},
                                 scope='Session color calibration; not a production acceptance test')
    path = folder/f'colors-{stamp}-{uuid4().hex[:8]}.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return path
