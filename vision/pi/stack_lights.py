"""Optional, active-high breadboard status LEDs on the Pi 5 RP1 controller.

BCM17 / physical 11 = red; BCM27 / physical 13 = yellow;
BCM22 / physical 15 = green. Each LED needs its own series resistor.
Importing this module never opens GPIO. Hardware is opened only with --gpio.
"""
from pathlib import Path
import warnings

PINS = {'red': 17, 'yellow': 27, 'green': 22}


def status_color(pack=None):
    """Translate the existing ledger decision; never infer readiness from total alone."""
    if pack is None:
        return 'yellow'
    counts, recipe = pack.get('counts', {}), pack.get('recipe', {})
    if (pack.get('reviews') or pack.get('status') in ('REVIEW', 'OVER TARGET')
            or any(counts.get(c, 0) > n for c, n in recipe.items())):
        return 'red'
    if (pack.get('status') == 'RECIPE REACHED' and pack.get('ready') is True
            and recipe and counts == recipe):
        return 'green'
    return 'yellow'


def inspect_chip(chip=None):
    """Read controller/line metadata only. This does not claim or change any pin."""
    try:
        import gpiod
    except ImportError as exc:
        raise RuntimeError('Install vision/pi/requirements-gpio.txt with the same Python used to run the counter') from exc
    paths = [Path(f'/dev/gpiochip{chip}')] if chip is not None else sorted(Path('/dev').glob('gpiochip*'))
    errors = []
    for path in paths:
        try:
            with gpiod.Chip(str(path)) as device:
                info = device.get_info()
                if info.label != 'pinctrl-rp1':
                    if chip is not None:
                        raise RuntimeError(f'{path} is {info.label}, not the Pi 5 header controller pinctrl-rp1')
                    continue
                lines = {}
                for color, pin in PINS.items():
                    line = device.get_line_info(pin)
                    lines[color] = dict(bcm=pin, name=line.name, used=line.used,
                                        consumer=line.consumer, direction=line.direction.name)
                return dict(path=str(path), label=info.label, lines=lines)
        except OSError as exc:
            errors.append(f'{path}: {exc}')
    raise RuntimeError('No accessible Pi 5 RP1 GPIO controller found. Check /dev/gpiochip* permissions. '
                       + '; '.join(errors))


class GpiodOutput:
    """Exclusive three-line request; one set_values call updates all outputs."""
    def __init__(self, chip=None):
        self.info = inspect_chip(chip)
        import gpiod
        from gpiod.line import Direction, Value
        busy = [f'BCM{v["bcm"]} ({v["consumer"]})' for v in self.info['lines'].values() if v['used']]
        if busy:
            raise RuntimeError('GPIO already in use: ' + ', '.join(busy))
        self._value = Value
        self._request = gpiod.request_lines(self.info['path'], consumer='yards-stack-lights', config={
            tuple(PINS.values()): gpiod.LineSettings(direction=Direction.OUTPUT,
                                                   output_value=Value.INACTIVE)})

    def write(self, color):
        self._request.set_values({pin: self._value.ACTIVE if name == color else self._value.INACTIVE
                                  for name, pin in PINS.items()})

    def close(self):
        self._request.release()


class StackLights:
    """One active color, no repeated writes, and all off before releasing GPIO."""
    def __init__(self, *, enabled=False, chip=None, output_factory=None):
        self.enabled = enabled
        self.chip = chip
        self.state = 'off'
        self._output = None
        self._factory = output_factory or GpiodOutput

    def __enter__(self):
        if self.enabled:
            self._output = self._factory(self.chip)
        return self

    def show(self, color):
        if color not in (*PINS, 'off'):
            raise ValueError(f'Invalid stack light: {color}')
        if not self.enabled or color == self.state:
            return
        if self._output is None:
            raise RuntimeError('GPIO controller is not open')
        self._output.write(color)
        self.state = color

    def update(self, pack=None):
        self.show(status_color(pack))

    def metadata(self):
        return dict(enabled=self.enabled, bcm_pins=dict(PINS), active_high=True,
                    controller=getattr(self._output, 'info', None))

    def close(self):
        output, self._output = self._output, None
        if output is not None:
            try:
                output.write('off')
            finally:
                output.close()
                self.state = 'off'

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.close()
        except Exception as cleanup_error:
            if exc is None:
                raise
            warnings.warn(f'GPIO cleanup failed: {cleanup_error}', RuntimeWarning)
        return False
