"""Portable settings; geometry is normalized to the camera image."""

from dataclasses import asdict, dataclass, field
import copy
import json
import math
from pathlib import Path

COLORS = ("red", "green", "blue")


@dataclass
class ColorRange:
    hue: int
    tolerance: int
    saturation_min: int = 90
    value_min: int = 55


@dataclass
class Settings:
    recipe: dict = field(default_factory=lambda: dict.fromkeys(COLORS, 4))
    colors: dict = field(default_factory=lambda: {
        "red": ColorRange(0, 10), "green": ColorRange(60, 22),
        "blue": ColorRange(110, 20),
    })
    rotate_180: bool = False
    roi: list = field(default_factory=lambda: [0.0, 0.0, 1.0, 1.0])
    boundary_start: list = field(default_factory=lambda: [0.5, 0.0])
    boundary_end: list = field(default_factory=lambda: [0.5, 1.0])
    packing_point: list = field(default_factory=lambda: [0.85, 0.5])
    hysteresis: float = 0.025
    transfer_band: list | None = None
    min_area: float = 0.0015
    max_area: float = 0.065
    min_fill: float = 0.25
    morphology_size: int = 3
    min_hits: int = 3
    side_frames: int = 3
    max_missed: int = 15
    max_crossing_gap: int = 2
    match_distance: float = 0.13
    ambiguity_margin: float = 0.012
    settle_seconds: float = 0.8

    def with_rotation(self, rotate_180):
        """Change view orientation while retaining the same physical geometry."""
        if type(rotate_180) is not bool:
            raise ValueError("rotate_180 must be true or false.")
        candidate = copy.deepcopy(self)
        if rotate_180 != self.rotate_180:
            x, y, w, h = self.roi
            candidate.roi = [round(1 - x - w, 12), round(1 - y - h, 12), w, h]
            for name in ("boundary_start", "boundary_end", "packing_point"):
                setattr(candidate, name, [round(1 - value, 12) for value in getattr(self, name)])
        candidate.rotate_180 = rotate_180
        return candidate.validate()

    def distance(self, point):
        ax, ay = self.boundary_start
        bx, by = self.boundary_end
        dx, dy = bx - ax, by - ay
        return (dx * (point[1] - ay) - dy * (point[0] - ax)) / math.hypot(dx, dy)

    def side(self, point):
        """-1 = lane, 0 = dead band, +1 = visible packing/exit side."""
        sign = 1 if self.distance(self.packing_point) > 0 else -1
        distance = self.distance(point) * sign
        return 1 if distance > self.hysteresis else -1 if distance < -self.hysteresis else 0

    def inside_transfer(self, point):
        """Optional lane/exit widths around the line; masks retain the full ROI."""
        if self.transfer_band is None:
            return True
        sign = 1 if self.distance(self.packing_point) > 0 else -1
        distance = self.distance(point) * sign
        return -self.transfer_band[0] <= distance <= self.transfer_band[1]

    def overlaps_transfer(self, box):
        if self.transfer_band is None:
            return True
        x, y, w, h = box
        sign = 1 if self.distance(self.packing_point) > 0 else -1
        distances = [self.distance(p) * sign for p in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]]
        return min(distances) <= self.transfer_band[1] and max(distances) >= -self.transfer_band[0]

    def validate(self):
        if type(self.rotate_180) is not bool:
            raise ValueError("rotate_180 must be true or false.")
        if set(self.recipe) != set(COLORS) or any(type(n) is not int or n < 0 for n in self.recipe.values()) or sum(self.recipe.values()) == 0:
            raise ValueError("Recipe must contain nonnegative integer red/green/blue counts, with at least one can.")
        if set(self.colors) != set(COLORS):
            raise ValueError("Provide exactly red, green, and blue color ranges.")
        hue_sets = []
        for name in COLORS:
            c = self.colors[name]
            values = (c.hue, c.tolerance, c.saturation_min, c.value_min)
            if any(type(v) is not int for v in values) or not 0 <= c.hue <= 179 or not 1 <= c.tolerance <= 44 or not 0 <= c.saturation_min <= 255 or not 0 <= c.value_min <= 255:
                raise ValueError(f"Invalid HSV settings for {name}.")
            hues = {(c.hue + i) % 180 for i in range(-c.tolerance, c.tolerance + 1)}
            if any(hues & previous for previous in hue_sets):
                raise ValueError("Color hue ranges overlap. Narrow the tolerance or re-sample the can colors.")
            hue_sets.append(hues)
        geometry = self.roi + self.boundary_start + self.boundary_end + self.packing_point
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in geometry):
            raise ValueError("Geometry must contain finite normalized coordinates.")
        if len(self.roi) != 4 or any(len(p) != 2 for p in (self.boundary_start, self.boundary_end, self.packing_point)):
            raise ValueError("ROI needs x/y/width/height; boundary and packing point need x/y.")
        x, y, w, h = self.roi
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.000001 or y + h > 1.000001:
            raise ValueError("ROI must stay inside the image.")
        if any(v < 0 or v > 1 for v in geometry[4:]):
            raise ValueError("Boundary and packing point must stay inside the image.")
        if math.dist(self.boundary_start, self.boundary_end) < 0.05:
            raise ValueError("Boundary is too short.")
        if not 0 < self.hysteresis < 0.2 or abs(self.distance(self.packing_point)) <= self.hysteresis:
            raise ValueError("Packing point must be clearly on one side of the boundary.")
        if self.transfer_band is not None:
            if not isinstance(self.transfer_band, list) or len(self.transfer_band) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or not self.hysteresis < v <= 1.5 for v in self.transfer_band):
                raise ValueError("Transfer band needs lane/exit widths larger than the neutral band and at most 1.5.")
        sides = {self.side(p) for p in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]}
        if not {-1, 1}.issubset(sides):
            raise ValueError("The ROI needs visible lane and exit areas on opposite sides of the boundary.")
        if not 0 < self.min_area < self.max_area < 1 or not 0 < self.min_fill <= 1:
            raise ValueError("Area fractions must satisfy 0 < min_area < max_area < 1.")
        if type(self.morphology_size) is not int or self.morphology_size not in (1, 3, 5, 7, 9):
            raise ValueError("Morphology size must be one of 1, 3, 5, 7, 9.")
        for name in ("min_hits", "side_frames", "max_missed", "max_crossing_gap"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.max_crossing_gap > self.max_missed or not 0 < self.match_distance < 0.5 or not 0 <= self.ambiguity_margin < self.match_distance or not 0 <= self.settle_seconds <= 30:
            raise ValueError("Invalid tracking distances, gap, or settling time.")
        return self

    def save(self, path):
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path=None):
        if path is None:
            return cls().validate()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if "colors" in data:
            data["colors"] = {name: ColorRange(**value) for name, value in data["colors"].items()}
        return cls(**data).validate()


def parse_recipe(text):
    try:
        values = [int(value.strip()) for value in text.split(",")]
    except ValueError as exc:
        raise ValueError("Recipe format is RED,GREEN,BLUE, for example 4,4,4.") from exc
    if len(values) != 3 or any(v < 0 for v in values) or not any(values):
        raise ValueError("Recipe needs three nonnegative counts with at least one can.")
    return dict(zip(COLORS, values))
