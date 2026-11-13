"""Keep custom touchscreen recipes separate from station calibration files.

CS488 Capstone, Team 1.
"""

import json
from pathlib import Path

COLORS = ("Red", "Green", "Blue")


def validate_recipe(recipe):
    """Require a positive total and a nonnegative integer for each can color."""
    if set(recipe) != set(COLORS):
        raise ValueError("A recipe needs Red, Green and Blue quantities.")
    if any(type(recipe[color]) is not int or recipe[color] < 0 for color in COLORS):
        raise ValueError("Recipe quantities must be whole numbers of zero or more.")
    if sum(recipe.values()) == 0:
        raise ValueError("A recipe must contain at least one can.")
    return dict(recipe)


def load_recipes(path, default):
    """Always read the station recipe from the current runtime configuration."""
    recipes = {"Station Recipe": validate_recipe(default)}
    path = Path(path)
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8"))
        for name, recipe in saved.items():
            if name != "Station Recipe":
                recipes[name] = validate_recipe(recipe)
    return recipes


def save_recipes(path, recipes):
    """Replace the local recipe file only after the new contents are complete."""
    saved = {name: validate_recipe(recipe) for name, recipe in recipes.items()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    temporary.replace(path)
