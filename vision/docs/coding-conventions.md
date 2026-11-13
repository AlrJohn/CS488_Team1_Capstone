# Coding conventions

CS488 · Team 1 · Module 3 development

We use the standard agreed on in our Module 3 coding-conventions report: descriptive underscore names, four-space indentation, documented functions and classes, and comments explaining the parts of the processing that are harder to follow.

## Names and layout

| Element | Convention | Example in the application |
| --- | --- | --- |
| New folders and Python files | Lowercase words with underscores | `color_analysis.py`, `instance_memory.py` |
| Functions and methods | Lowercase action names with underscores | `sample_colors`, `acknowledge_review` |
| Variables and attributes | Descriptive lowercase names with underscores | `roi_width`, `context_height`, `color_evidence` |
| Classes | Capitalized words without underscores | `PackLedger`, `StackLights` |
| Constants | Uppercase words with underscores | `COLORS`, `PINS` |
| Internal helpers | Leading underscore where appropriate | `_quantities`, `_resolve_defect` |
| JSON keys | Stable descriptive underscore names | `expected_recipe`, `rotate_180` |
| Selected presentation images | Date, platform, description and sequence | `2026-11-13_pi_recipe_reached_01.png` |

Existing launch paths, JSON keys and Designer resource/widget names stay stable because other files and the installed Pi use them. Qt callbacks such as `resizeEvent` and `closeEvent`, unittest's `setUp`, and OpenCV's `isOpened` keep the names required by those interfaces. Short coordinate or mathematical symbols are used where their meaning is clear from the surrounding calculation. New processing stages use descriptive names.

We use four spaces, one statement per line, spaces around operators, and blank lines between definitions. Ruff formats the maintained code with a 100-character wrapping target. Long strings and comments may exceed that target. The formatter does not change detection thresholds or the order of processing.

## Documentation and comments

Each maintained module starts with its purpose and Team 1 identification. Classes, constructors, functions and private helpers have docstrings. Simple helpers have short descriptions; the central processing functions also explain inputs, returned values, errors and changes to program state.

Comments explain why a step exists. Examples include keeping a tracking margin outside the ROI, sampling only mask pixels, requiring actual color observations, preventing a second admission after an ID change, and switching outputs off during cleanup. We avoid comments that only repeat the next statement.

Third-party tracking source under `common/vendor/` retains its upstream code and license. It is excluded from our formatting and naming checks. Historical experiment notes retain their original context; retired executables are available through Git history.

## Errors and cleanup

We validate configuration, model identities and input dimensions before relying on them. Invalid settings raise specific errors such as `ValueError`, while device and processing failures identify the operation that failed. Worker/thread boundaries catch failures so they can report them to the UI. They do not turn a failed inspection into PASS.

Context managers and `try/finally` blocks close cameras, model streams, files and GPIO requests. Unknown colors stay unknown. A review warning remains separate from an incorrect quantity, and an operator acknowledgement records a manual check without silently changing counts.

## Check a change

Install the platform dependencies and `vision/requirements-dev.txt`, then run from the repository root:

```bash
python -m ruff format --check .
python -m ruff check .
python -m unittest discover -s vision/tests -v
```

For changes to the touchscreen, also run the Qt integration tests in the [test guide](testing.md). The root `pyproject.toml` keeps formatting, naming and docstring checks consistent across machines.
