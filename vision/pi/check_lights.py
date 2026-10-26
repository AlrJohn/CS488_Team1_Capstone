"""Read GPIO availability, or exercise three verified LED/relay status outputs."""
import argparse
import json
import time
from stack_lights import StackLights, inspect_chip


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpio-chip', type=int, help='Override RP1 /dev/gpiochip number')
    parser.add_argument('--gpio-active-low', action='store_true', help='LOW activates a verified 3.3 V compatible relay input')
    parser.add_argument('--cycle', action='store_true', help='Actually drive red, yellow, green; wire first')
    parser.add_argument('--seconds', type=float, default=2., help='Seconds per LED during --cycle')
    args = parser.parse_args(argv)
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    print(json.dumps(inspect_chip(args.gpio_chip), indent=2), flush=True)
    if args.cycle:
        with StackLights(enabled=True, chip=args.gpio_chip, active_low=args.gpio_active_low) as lights:
            for color in ('red', 'yellow', 'green'):
                print(color, flush=True)
                lights.show(color)
                time.sleep(args.seconds)
        print('All off; GPIO released.', flush=True)
    else:
        print('Read-only check: no GPIO outputs were changed.', flush=True)


if __name__ == '__main__':
    main()
