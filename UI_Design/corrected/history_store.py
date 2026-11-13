"""Append completed carton records compatible with the existing history widget.

CS488 Capstone, Team 1.
"""

import csv
from datetime import datetime
from pathlib import Path

FIELDNAMES = [
    "Date",
    "Time",
    "Batch ID",
    "Passed",
    "Failed",
    "Status",
    "Recipe",
    "Expected Red",
    "Expected Green",
    "Expected Blue",
    "Observed Red",
    "Observed Green",
    "Observed Blue",
    "Mode",
]


def save_box(path, recipe, expected, observed, mode="CAMERA", status_override=None):
    """Append a carton result to CSV, preserving older history during schema migration.

    Mismatched quantities cannot be overridden as PASS. A review status can be saved
    when the quantities match but tracking or confirmation still needs checking.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    expected = {k: int(expected.get(k, 0)) for k in ("Red", "Green", "Blue")}
    observed = {k: int(observed.get(k, 0)) for k in ("Red", "Green", "Blue")}
    passed = sum(min(observed[k], expected[k]) for k in expected)
    differences = sum(abs(observed[k] - expected[k]) for k in expected)
    status = "PASS" if differences == 0 else "FAIL"
    if status_override is not None:
        if status_override not in ("PASS", "FAIL", "REVIEW"):
            raise ValueError("Invalid inspection status override")
        # Never override a mismatched count as PASS.
        status = status_override if differences == 0 or status_override != "PASS" else "FAIL"
    record = {
        "Date": now.strftime("%m/%d/%Y"),
        "Time": now.strftime("%I:%M:%S %p"),
        "Batch ID": now.strftime("B-%Y%m%d-%H%M%S-%f"),
        "Passed": passed,
        "Failed": differences,
        "Status": status,
        "Recipe": recipe,
        "Mode": mode,
    }
    for color in ("Red", "Green", "Blue"):
        record["Expected " + color] = expected[color]
        record["Observed " + color] = observed[color]
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open(newline="", encoding="utf-8") as f:
            existing_header = next(csv.reader(f), [])
        if existing_header != FIELDNAMES:
            # Preserve earlier 6-column history; migrate to the extended schema.
            with path.open(newline="", encoding="utf-8") as f:
                previous = list(csv.DictReader(f))
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                for old in previous:
                    writer.writerow({key: old.get(key, "") for key in FIELDNAMES})
            exists = True
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        writer.writerow(record)
    return record
