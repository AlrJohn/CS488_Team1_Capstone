# Breadboard stack-light prototype

We use three separate LEDs to display the same decision as the Pi preview. GPIO output happens after counting; it does not change the model, color analysis, tracking or recipe.

| Light | Program decision |
| --- | --- |
| Yellow | Setup, counting below the recipe, or waiting for confirmation/settling |
| Green | Exact configured recipe, no review and no pending confirmation; normally 4 red + 4 green + 4 blue |
| Red | A review warning or any color above its target |
| All off | GPIO disabled, application exited, or no indicator power |

The lights describe the current box. Green still relies on our assumption that admitted cans go into the carton. A left-side defect removal can change green back to yellow. An extra can can change it to red. **N** immediately returns to yellow for the next box. **U** and **A** update the light from the resulting ledger decision; acknowledging a review does not fix an incorrect mix.

## Parts and exact wiring

Use a breadboard, separate red/yellow/green indicator LEDs, **three 1 kΩ resistors** (one per LED, 1/4 W is fine), female-to-male jumper wires for the Pi header, and short breadboard jumpers. A four-band 1 kΩ resistor is brown-black-red-gold. These instructions are for bare, low-current indicator LEDs, not 5/12/24 V stack lamps or LED strips.

Shut down the Pi and **unplug USB-C power before wiring**. Identify physical pin 1 from the board marking or the [official GPIO pinout](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header). Do not infer pin 1 from a rotated photo or the orientation of the HAT. Physical pin numbers count positions on the connector; BCM numbers are the identifiers used by Python.

| Connection | Physical header pin | BCM number | Breadboard connection |
| --- | --- | --- | --- |
| Red output | **11** | **17** | Through its own 1 kΩ resistor to red LED long leg/anode (+) |
| Yellow output | **13** | **27** | Through its own 1 kΩ resistor to yellow LED long leg/anode (+) |
| Green output | **15** | **22** | Through its own 1 kΩ resistor to green LED long leg/anode (+) |
| Common ground | **6** | GND | To the breadboard ground rail; connect all three LED short legs/cathodes (-) to this rail |

The short leg and the flat side of a standard LED identify its cathode. If its legs have been trimmed, check its markings/datasheet. Put the two LED legs in electrically separate breadboard rows. Many boards join each group of five holes in a numbered row; putting both legs in that connected group shorts the LED. Some ground rails are split halfway down; use a jumper if the LEDs span that split.

```text
Pi physical 11 / BCM17 ----[ 1 kΩ ]---->| red LED -----+
Pi physical 13 / BCM27 ----[ 1 kΩ ]---->| yellow LED --+---- ground rail
Pi physical 15 / BCM22 ----[ 1 kΩ ]---->| green LED ---+
Pi physical  6 / GND --------------------------------+
                                   anode -> cathode
```

No connection to the Pi's 5 V or 3.3 V power pins is needed: each GPIO supplies 3.3 V when its LED should turn on. Never connect a bare LED without its resistor or apply 5 V to a GPIO. See [Raspberry Pi's electrical guidance](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header).

The AI HAT+ communicates over PCIe. With that HAT installed, our read-only check on 2026-10-19 found GPIO17, GPIO27 and GPIO22 unused and configured as inputs. Leave the HAT installed. If it blocks header access, use a compatible 40-pin breakout/pass-through extension that preserves the HAT connection and pin numbering. Fit it with power unplugged and check neither row is shifted. Keep jumpers clear of the fan, heatsink and PCIe ribbon. The supplied HAT stacking header may not leave accessible male pins above the board.

## Install and check without turning anything on

Install the optional dependency in the **same Python environment** as HailoRT. From the repository root on the Pi:

```bash
.venv-pi/bin/python -m pip install -r vision/pi/requirements-gpio.txt
.venv-pi/bin/python vision/pi/check_lights.py
```

The check only reads chip/line metadata. It should report `pinctrl-rp1` and `used: false` for each selected pin when no counter/light test is running. It does not turn on LEDs or change pin direction. Our Ubuntu Pi exposes RP1 as `/dev/gpiochip0`; the program finds it by label rather than assuming a chip number. It refuses a different controller or pins already in use. `--gpio-chip 0` permits an explicit choice, but it must still be RP1.

Run the source from the Git checkout. An existing working Python environment may be reused, but the script path must point to this repo. Older pilot folders and their shortcuts are backups; [the migration notes](UPDATING.md) explain how to preserve their settings before pulling updates.

## Test the wiring, then run the counter

Reconnect power after checking wiring. From the repository root:

```bash
.venv-pi/bin/python vision/pi/check_lights.py --cycle
```

Red, yellow and green should each light for two seconds, then all turn off. This test needs no camera or model. If one fails, power down before changing wiring. Check polarity, resistor value, physical pin and ground continuity. Do not run this test and the counter together: GPIO access is exclusive.

Start the repository camera application with GPIO enabled and the station settings:

```bash
.venv-pi/bin/python vision/pi/run.py --backend hailo --source 0 --gpio \
  --config-dir vision/configs/local/pi
```

The station folder must contain `runtime.json`, `colors.json` and `view.json` calibrated for this mounting. Without `--config-dir`, the public examples are used.

Yellow appears during model loading/setup. Click the preview and press **P** with an empty box/count area. Build the 12-pack; green appears when the existing ready rule passes. Press **N** for a new box or **Q** to save and quit. Outputs are set low and released on normal exit, Ctrl+C or a handled exception. Without `--gpio`, Python does not open pins or require the GPIO library. The application stops if requested GPIO access fails.

## Code and troubleshooting

`stack_lights.py` uses the official libgpiod v2 binding (`gpiod==2.5.0`). It requests three lines initially low, then updates them together with `set_values()` only when the selected color changes. `run.py` calls it after the pipeline returns a pack decision and after manual controls change that decision. Metadata records the pin mapping/controller; observation rows record the commanded light. This field is not electrical readback or proof an LED is connected.

`check_lights.py` provides the read-only check and explicit cycle. `tests/test_stack_lights.py` checks recipe status, defects, reviews, reset and cleanup with fake outputs. This uses the Linux GPIO character device interface supported by Pi 5 rather than the older RPi.GPIO library.

Our Ubuntu `team1` session already had read/write access to RP1, so sudo was unnecessary. If another Pi reports permission denied, grant the intended user access through its OS GPIO group/udev rules, then log out/in. Do not make all device files world writable or run the full camera application as root to bypass permissions. SSH and desktop sessions can have different device access.

This is a prototype status display. A frozen process, forced kill, power loss or broken wire is not independently monitored; all-off never means the pack passed. A real stack lamp needs an appropriately rated transistor/MOSFET/relay driver and its specified supply. Do not connect it directly using this circuit.

References: [official GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header), [AI HAT+ product brief](https://datasheets.raspberrypi.com/ai-hat-plus/raspberry-pi-ai-hat-plus-product-brief.pdf), [official libgpiod package](https://pypi.org/project/gpiod/), [multi-line output API](https://libgpiod.readthedocs.io/en/v2.3/python_line_request.html).
