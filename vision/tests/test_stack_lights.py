"""Status decisions and output lifetime, exercised without physical GPIO."""
from pathlib import Path
from enum import Enum
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

VISION = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(VISION), str(VISION/'pi')]
from common.pack_ledger import PackLedger
from stack_lights import GpiodOutput, PINS, StackLights, status_color


class FakeOutput:
    def __init__(self, chip=None):
        self.writes = []
        self.closed = False

    def write(self, color):
        self.writes.append(color)

    def close(self):
        self.closed = True


class StackLightTests(unittest.TestCase):
    def test_disabled_runtime_does_not_open_gpio(self):
        def forbidden(chip):
            self.fail('GPIO opened when disabled')
        with StackLights(output_factory=forbidden) as lights:
            lights.update(PackLedger().snapshot())
            self.assertEqual(lights.state, 'off')

    def test_setup_partial_and_pending_pack_are_yellow(self):
        self.assertEqual(status_color(), 'yellow')
        ledger = PackLedger()
        ledger.apply('pick', {'red': 4, 'green': 4, 'blue': 3}, 1, 0.)
        self.assertEqual(status_color(ledger.snapshot()), 'yellow')
        ledger.apply('last', {'blue': 1}, 1, 1.)
        self.assertEqual(status_color(ledger.snapshot(pending=True)), 'yellow')

    def test_exact_recipe_becomes_green_then_defect_and_reset_yellow(self):
        ledger = PackLedger()
        ledger.apply('all', {'red': 4, 'green': 4, 'blue': 4}, 1, 0.)
        self.assertEqual(status_color(ledger.snapshot()), 'green')
        ledger.apply('defect', {'blue': 1}, -1, 1.)
        self.assertEqual(status_color(ledger.snapshot()), 'yellow')
        ledger.undo(2.)
        self.assertEqual(status_color(ledger.snapshot()), 'green')
        ledger.new_box(3.)
        self.assertEqual(status_color(ledger.snapshot()), 'yellow')

    def test_review_and_over_target_are_red(self):
        ledger = PackLedger()
        ledger.apply('all', {'red': 4, 'green': 4, 'blue': 4}, 1, 0.)
        ledger.review('Verify identity', 1.)
        self.assertEqual(status_color(ledger.snapshot()), 'red')
        ledger.acknowledge_review(2.)
        self.assertEqual(status_color(ledger.snapshot()), 'green')
        ledger.apply('extra', {'red': 1}, 1, 3.)
        self.assertEqual(status_color(ledger.snapshot()), 'red')

    def test_total_twelve_with_wrong_mix_is_not_green(self):
        ledger = PackLedger()
        ledger.apply('wrong', {'red': 5, 'green': 4, 'blue': 3}, 1, 0.)
        self.assertEqual(ledger.snapshot()['total'], 12)
        self.assertEqual(status_color(ledger.snapshot()), 'red')

    def test_unknown_or_inconsistent_status_cannot_show_green(self):
        pack = PackLedger().snapshot()
        pack.update(ready=True, status='RECIPE REACHED')
        self.assertEqual(status_color(pack), 'yellow')
        pack.update(counts=dict(red=4, green=4, blue=4), status='UNRECOGNIZED')
        self.assertEqual(status_color(pack), 'yellow')

    def test_repeated_frame_does_not_rewrite_gpio_and_exit_turns_off(self):
        output = FakeOutput()
        with StackLights(enabled=True, output_factory=lambda chip: output) as lights:
            lights.update()
            lights.update()
            lights.show('green')
            lights.update()  # New-box action must immediately revoke green.
            self.assertEqual(output.writes, ['yellow', 'green', 'yellow'])
        self.assertEqual(output.writes[-1], 'off')
        self.assertTrue(output.closed)
        self.assertEqual(lights.state, 'off')

    def test_startup_or_processing_exception_also_turns_off(self):
        for error in (RuntimeError('camera failure'), KeyboardInterrupt()):
            output = FakeOutput()
            with self.assertRaises(type(error)):
                with StackLights(enabled=True, output_factory=lambda chip: output) as lights:
                    lights.show('green')
                    raise error
            self.assertEqual(output.writes, ['green', 'off'])
            self.assertTrue(output.closed)

    def test_write_failure_still_releases_request(self):
        output = FakeOutput()
        def fail(color):
            raise OSError('disconnected controller')
        output.write = fail
        lights = StackLights(enabled=True, output_factory=lambda chip: output)
        lights.__enter__()
        with self.assertRaises(OSError):
            lights.close()
        self.assertTrue(output.closed)

    def test_driver_requests_initially_low_and_writes_all_three_together(self):
        class Value(Enum):
            INACTIVE = 0
            ACTIVE = 1
        request = Mock()
        api = SimpleNamespace(request_lines=Mock(return_value=request), LineSettings=Mock())
        line_api = SimpleNamespace(Value=Value, Direction=SimpleNamespace(OUTPUT='output'))
        info = dict(path='/dev/gpiochip0', lines={c:dict(bcm=p, used=False) for c,p in PINS.items()})
        with patch.dict(sys.modules, {'gpiod':api, 'gpiod.line':line_api}), patch('stack_lights.inspect_chip', return_value=info):
            output = GpiodOutput()
            api.LineSettings.assert_called_once_with(direction='output', output_value=Value.INACTIVE)
            self.assertEqual(set(api.request_lines.call_args.kwargs['config']), {tuple(PINS.values())})
            for color in ('red', 'yellow', 'green', 'off'):
                output.write(color)
                values = request.set_values.call_args.args[0]
                self.assertEqual(set(values), set(PINS.values()))
                self.assertEqual([p for p,v in values.items() if v == Value.ACTIVE],
                                 [] if color == 'off' else [PINS[color]])
            output.close()
            request.release.assert_called_once()

    def test_driver_does_not_claim_a_pin_used_by_another_program(self):
        api = SimpleNamespace(request_lines=Mock())
        info = dict(path='/dev/gpiochip0', lines={'red':dict(bcm=17, used=True, consumer='another app')})
        with patch.dict(sys.modules, {'gpiod':api, 'gpiod.line':SimpleNamespace(Direction=None,Value=None)}), patch('stack_lights.inspect_chip', return_value=info):
            with self.assertRaisesRegex(RuntimeError, 'already in use'):
                GpiodOutput()
            api.request_lines.assert_not_called()


if __name__ == '__main__':
    unittest.main()
