"""Color settings used by the current instance-segmentation counter."""
from dataclasses import dataclass
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
class Settings:
    colors: dict
    rotate_180: bool

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
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
        return cls(ranges, data['rotate_180'])


def parse_recipe(value):
    try:
        counts = [int(s.strip()) for s in value.split(',')]
    except ValueError as exc:
        raise ValueError('Recipe format is RED,GREEN,BLUE, for example 4,4,4.') from exc
    if len(counts) != 3 or any(n < 0 for n in counts) or not any(counts):
        raise ValueError('Recipe needs three nonnegative counts with at least one can.')
    return dict(zip(COLORS, counts))
