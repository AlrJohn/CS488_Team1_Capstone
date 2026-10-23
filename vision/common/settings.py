"""Color settings used by the current instance-segmentation counter."""
from dataclasses import dataclass, field
import math
import json
from pathlib import Path

COLORS = ('red', 'green', 'blue')


@dataclass
class ColorRange:
    hue: int
    tolerance: int
    saturation_min: int
    value_min: int


@dataclass
class InteriorSampling:
    """Ordinary color-check limits, configurable alongside the side fallback."""

    # Defaults preserve older color profiles that have no interior_sampling.
    min_pixels: int = 25
    min_coverage: float = .10
    min_dominance: float = .60

    def __post_init__(self):
        """Validate pixel counts and fractions before opening the camera."""
        if type(self.min_pixels) is not int or self.min_pixels < 1:
            raise ValueError('Interior sampling needs a positive integer pixel count.')
        for name in ('min_coverage', 'min_dominance'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError('Invalid interior sampling fraction: ' + name)
        if self.min_dominance <= .5:
            raise ValueError('Interior sampling needs a majority color.')


@dataclass
class SideSampling:
    """Fallback evidence limits for cans with mostly white center labels."""

    enabled: bool = True
    band_fraction: float = .20
    min_pixels: int = 40
    min_coverage: float = .10
    min_dominance: float = .80
    min_row_fraction: float = .35

    def __post_init__(self):
        """Reject invalid controls before processing camera images."""
        if type(self.enabled) is not bool or type(self.min_pixels) is not int or self.min_pixels < 25:
            raise ValueError('Side sampling needs a boolean enabled flag and at least 25 pixels.')
        for name in ('band_fraction', 'min_coverage', 'min_dominance', 'min_row_fraction'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError('Invalid side sampling fraction: ' + name)
        if self.band_fraction > .5 or self.min_dominance <= .5:
            raise ValueError('Side bands must not overlap and need a majority color.')


@dataclass
class Settings:
    colors: dict
    rotate_180: bool
    side_sampling: SideSampling = field(default_factory=SideSampling)
    interior_sampling: InteriorSampling = field(default_factory=InteriorSampling)

    @classmethod
    def load(cls, path):
        """Read a saved color profile and validate its settings."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))

    @classmethod
    def from_dict(cls, data):
        """Validate an in-memory profile, including a proposed calibration."""
        if set(data['colors']) != set(COLORS):
            raise ValueError('Provide red, green and blue HSV ranges.')
        if type(data['rotate_180']) is not bool:
            raise ValueError('rotate_180 must be true or false.')
        ranges = {}
        previous = set()
        for name in COLORS:
            value = ColorRange(**data['colors'][name])
            if any(type(v) is not int for v in vars(value).values()) or not (
                0 <= value.hue <= 179 and 1 <= value.tolerance <= 44
                and 0 <= value.saturation_min <= 255 and 0 <= value.value_min <= 255
            ):
                raise ValueError('Invalid HSV range for ' + name)
            hues = {(value.hue + i) % 180 for i in range(-value.tolerance, value.tolerance + 1)}
            if hues & previous:
                raise ValueError('HSV hue ranges overlap; narrow or resample them.')
            previous |= hues
            ranges[name] = value
        return cls(ranges, data['rotate_180'],
                   side_sampling=SideSampling(**data.get('side_sampling', {})),
                   interior_sampling=InteriorSampling(**data.get('interior_sampling', {})))


def parse_recipe(value):
    try:
        counts = [int(s.strip()) for s in value.split(',')]
    except ValueError as exc:
        raise ValueError('Recipe format is RED,GREEN,BLUE, for example 4,4,4.') from exc
    if len(counts) != 3 or any(n < 0 for n in counts) or not any(counts):
        raise ValueError('Recipe needs three nonnegative counts with at least one can.')
    return dict(zip(COLORS, counts))
