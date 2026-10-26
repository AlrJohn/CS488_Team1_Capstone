# 24 V stack light and four-channel relay

This plan uses the photographed Keyence MS2-H100, Xunhe XH50-3T/W-J lamp (12–24 V AC/DC), and optocoupled four-channel board with SRD-05VDC-SL-C relays and a VCC/JD-VCC jumper. See the [connection drawing](STACK-LIGHT-WIRING.svg). The physical circuit has not been electrically verified by the software tests.

The [annotated relay photograph](STACK-LIGHT-RELAY-PHOTO.png) marks the actual twelve screw positions. Hold the board exactly as photographed: screw terminals down the right edge, K1 at the top and K4 at the bottom. In every three-screw group the printed contact symbol shows **top NC, middle COM, bottom NO**. The middle moving contact rests against the top contact when off, identifying that top contact as normally closed.

Count the screws down the entire right-hand column, starting with 1 at the very top:

| Screw number | Terminal | Connection |
| --- | --- | --- |
| 1 | K1 NC | Empty |
| 2 | K1 COM | Fused +24 V branch |
| 3 | K1 NO | Red lamp wire |
| 4 | K2 NC | Empty |
| 5 | K2 COM | Fused +24 V branch |
| 6 | K2 NO | Yellow/orange lamp wire |
| 7 | K3 NC | Empty |
| 8 | K3 COM | Fused +24 V branch |
| 9 | K3 NO | Green lamp wire |
| 10 | K4 NC | Empty |
| 11 | K4 COM | Empty |
| 12 | K4 NO | Empty |

With power disconnected and no load wires attached, the first group's contact check is continuity between 2 and 1, and an open circuit between 2 and 3. Repeat the same pattern for the other groups. Check the printed symbols/measurements if a board differs; do not energize a mismatched pinout. Use a suitable distribution connector to split the fused +24 V feed into three branches, one for each COM. Loosen a terminal screw, insert its stripped conductor in that terminal's wire-entry opening, and tighten to the connector's specification; leave no exposed strands and check that the wire is held securely.

The [other team's model](https://sites.google.com/view/stacklightelectricitycontrol/full-page-embed) uses positive-side switching and a negative lamp return. This plan follows that common-negative arrangement. The lamp sheet identifies gray as common but does not mark DC polarity: verify common-negative operation with the supplier or a lab technician's protected bench setup before final assembly. The model's displayed currents are simulated, not measurements of our hardware.

The reference assigns green to GPIO17 and red to GPIO22. Our program uses **red GPIO17, yellow GPIO27, green GPIO22**. These tables match our program. K4 and the purple buzzer wire stay unused.

## Preparation

Unplug both Pi power and the Keyence mains supply before adding or changing wires. The exposed L, N and protective-earth terminals are the mains side: a lab technician should fit/check its mains cable, earthing, strain relief and terminal protection before energizing it. The connections below concern only the DC output and controller.

Use insulated leads, secure screw terminals/distribution block, a multimeter, three 10 kΩ input pull-ups, and a DC-rated inline fuse/holder selected for the lamp current and the smallest wire's rating. Keep the Pi on its normal USB-C supply. The Keyence protective-earth terminal is different from its negative DC output. Never feed 24 V into the Pi or the relay's small control pins.

The [annotated Keyence photograph](KEYENCE-POWER-SUPPLY-PHOTO.png) identifies its five screws with the display upright and the terminal column on the right. From top to bottom: **1 positive 24 V DC output**, **2 negative DC output**, **3 protective earth**, **4 mains neutral N**, **5 mains live L**. The first output goes through the DC fuse/distribution connector to relay COM screws 2, 5 and 8; the second goes to the lamp gray common in the common-negative arrangement above. The bottom three belong to a properly installed grounded 100–240 V AC input. Have a lab technician select and fit the mains cord, earth, strain relief and enclosure; the photo does not establish any particular cord's conductor colors. See the [manufacturer's MS2-series manual](https://www.artisantg.com/info/Keyence_MS2_H50_Manual_2021914121847.pdf) for installation requirements.

## 1. Separate 3.3 V inputs from 5 V relay coils

The [Pi-to-relay control diagram](PI-RELAY-CONTROL.png) shows the numbered 40-pin header, the input header in the photographed orientation, and the input pull-ups. Find the Pi's physical pin 1 marking before using its numbering map; the installed HAT may cover the header. If the pins are covered, use a correctly aligned stacking header or GPIO breakout rather than wedging wires underneath the HAT. [Editable SVG](PI-RELAY-CONTROL.svg).

**Remove the cap bridging VCC and JD-VCC first, and leave it removed.** Use printed pin labels rather than their position in a rotated picture.

| Pi physical pin | Relay board connection | Purpose |
| --- | --- | --- |
| 1 — 3.3 V | VCC on the six-pin input header | Input/opto circuit |
| 2 — 5 V | JD-VCC on the separate power header | Relay coils |
| 6 — GND | GND | Pi/relay-control return |

Do not connect the Keyence DC negative to the Pi/relay-control GND for this arrangement. The 24 V lamp return is separate and closes through the contacts. Using Pi power for both relay rails does not provide separate-supply optical isolation between the Pi and the coils.

The [Handson guide for this module design](https://www.handsontec.com/dataspecs/4Ch-relay.pdf), pages 2–3, describes JD-VCC at 5 V and input VCC at 3.3 V, but warns that some boards do not actuate reliably at 3.3 V. It describes a similar design, not a confirmed manufacturer identity for this unbranded board. Perform the next check before connecting signal GPIOs.

## 2. Relay-only check

Leave GPIO17/27/22 and all 24 V contact wiring disconnected. Add a **10 kΩ resistor from each IN1, IN2 and IN3 to 3.3 V VCC**. Tie unused IN4 directly to that VCC. These connections hold inputs off when no GPIO drives them.

Power the Pi/control board. Measure about 3.3 V between VCC/GND and about 5 V between JD-VCC/GND. Each IN-to-GND must stay at or below 3.3 V before connecting a Pi signal. Relays should be off with the inputs pulled high.

Temporarily connect IN1 to board GND with an insulated jumper: K1 should click on. Remove it: the pull-up should turn K1 off. Repeat IN2/K2 and IN3/K3 several times. An indicator LED alone does not establish contact closure.

Identify COM/NO with the printed switch symbol and a multimeter. In the pictured board COM is the center screw of each three-terminal group. The correct NO outside screw has no continuity to COM with the coil off, and continuity when energized. For this continuity test the contact circuit must have no 24 V or other load supply attached; only the coil/control supply may be on. Leave the other outside screw, NC, unused. Do not copy the illustration's terminal positions onto a rotated physical board.

If a channel fails to switch firmly/repeatedly or an input exceeds 3.3 V, keep the Pi signals disconnected and use a documented 3.3 V compatible driver/relay board. Do not increase input VCC to 5 V while driving IN pins directly from the Pi; a 5 V interface needs a suitable buffer first. Do not improvise resistor changes on the module.

## 3. Connect GPIO signals after that check passes

Power off before connecting. Retain the pull-ups and IN4-to-VCC connection; remove old bare LEDs from these GPIO outputs.

| Pi physical pin | BCM GPIO | Relay input | Light |
| --- | --- | --- | --- |
| 11 | 17 | IN1 / K1 | Red |
| 13 | 27 | IN2 / K2 | Yellow/amber |
| 15 | 22 | IN3 / K3 | Green |

A LOW input should activate a relay and HIGH should release it. Use `--gpio-active-low`. The software starts all three outputs HIGH/off, then pulls only the selected channel LOW. External pull-ups provide an off bias when GPIOs are released; releasing GPIOs is not a power switch.

## 4. Connect the 24 V lamp circuit

Power everything off. Following the common-negative reference arrangement:

| Connection | Destination |
| --- | --- |
| Keyence DC `+` | Inline fuse, then branch to K1 COM, K2 COM and K3 COM |
| K1 NO | Lamp red wire |
| K2 NO | Lamp amber/orange wire; the cable appears yellow |
| K3 NO | Lamp green wire |
| Keyence DC `−` | Lamp gray common wire |
| Purple buzzer wire | Individually insulated and disconnected |
| K1–K3 NC and all K4 contacts | Unused |

The label confirms 24 V operation, but the sheet does not print DC polarity. Have common-negative operation checked before final assembly; failure to light is not a reason to try arbitrary power wires or connect the lamp to mains.

For red, current travels: supply positive → fuse → K1 COM → closed K1 NO → red lamp section → gray common → supply negative. The 24 V supply connects only to relay **contacts**, never VCC, JD-VCC, GND or IN pins.

## 5. Test and run

Review/push the PC changes and pull them onto the Pi before using the new option. From the repo root with the existing Python environment activated, first test clicks with 24 V off:

```bash
python vision/pi/check_lights.py --cycle --gpio-active-low
```

Power off to finish/check the lamp wiring, then apply power and repeat. Red, yellow and green should appear in that order, then all turn off. Do not run the test alongside the counter. If several channels activate together, power off and check the jumper, polarity and terminal assignments.

For normal counting:

```bash
python vision/pi/run.py --backend hailo --source 0 --camera-fps 60 \
  --gpio --gpio-active-low \
  --color-config "vision/configs/local/color-profiles/colors-YOUR-FILENAME.json"
```

Replace the profile filename and retain any existing `--config-dir`, view or runtime options. P starts a box, N starts the next box/yellow, and Q saves/exits. Yellow means setup/counting/waiting; green means the exact recipe is ready without review; red means review or over target. Buzzer control has not been added.

`--gpio` alone retains active-high operation for bare LEDs/non-inverting interfaces. The new option changes polarity, not voltage. `stack_lights.py` uses libgpiod's active-low setting so initial/final logical INACTIVE means physical HIGH, and records the chosen polarity in metadata. Normal exit and handled errors request all off before release; a frozen process, broken wire or power failure is not independently monitored.

References: [Pi GPIO/header](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio), [Keyence specifications](https://www.keyence.com/products/controls/other-controls/ms2/models/ms2-h100/), [module design guide](https://www.handsontec.com/dataspecs/4Ch-relay.pdf), [libgpiod line settings](https://kernel.googlesource.com/pub/scm/libs/libgpiod/libgpiod/+/9d8940f38f6e858073e7f144664ec99061c71831/bindings/python/gpiod/line_settings.py), supplied lamp instruction sheet and hardware photographs.
