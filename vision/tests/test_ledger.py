"""Exercise count transactions and review behavior without camera inputs.

CS488 Capstone, Team 1.
"""

from pathlib import Path
import sys
import unittest

VISION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VISION))
from common.pack_ledger import PackLedger
from common.settings import parse_recipe


class LedgerTests(unittest.TestCase):
    """Guard against repeated events, incorrect undo and hidden count errors."""

    def test_repeated_pick_and_undo_cannot_readmit_the_same_event(self):
        """Keep an undone identity consumed even if its original event is delivered again."""
        ledger = PackLedger()
        event = ledger.apply("one", {"red": 1}, 1, 0)
        self.assertIs(ledger.apply("one", {"red": 1}, 1, 1), event)
        ledger.undo(2)
        ledger.apply("one", {"red": 1}, 1, 3)
        self.assertEqual(ledger.counts["red"], 0)
        with self.assertRaisesRegex(ValueError, "reused"):
            ledger.apply("one", {"blue": 1}, 1, 4)

    def test_excess_removal_requests_review_and_acknowledgement_keeps_counts(self):
        """Prevent negative quantities without fabricating a replacement transaction."""
        ledger = PackLedger()
        event = ledger.apply("removal", {"green": 1}, -1, 0)
        self.assertEqual(event["kind"], "rejected_defect")
        self.assertEqual(ledger.snapshot()["status"], "REVIEW")
        ledger.acknowledge_review(1)
        self.assertFalse(ledger.reviews)
        self.assertEqual(sum(ledger.counts.values()), 0)

    def test_review_resolution_and_new_box_do_not_leak_old_counts(self):
        """Clear only the requested review, then close and reset the carton."""
        ledger = PackLedger()
        ledger.review("color", 0)
        ledger.review("identity", 0)
        ledger.resolve_review("color", 1)
        self.assertEqual(ledger.reviews, ["identity"])
        ledger.apply("pick", {"blue": 2}, 1, 2)
        closed = ledger.new_box(3)
        self.assertEqual(closed["counts"]["blue"], 2)
        self.assertEqual(ledger.box, 2)
        self.assertEqual(sum(ledger.counts.values()), 0)

    def test_invalid_recipes_events_and_times_are_rejected(self):
        """Reject malformed input before modifying the ledger."""
        self.assertEqual(parse_recipe("4, 4, 4"), dict(red=4, green=4, blue=4))
        for value in ("0,0,0", "4,-1,4", "a,4,4", "4,4"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_recipe(value)
        ledger = PackLedger()
        for quantities, direction, timestamp in (
            ({"red": -1}, 1, 0),
            ({"red": 1}, 2, 0),
            ({"red": 1}, 1, float("nan")),
            ({"red": 1}, 1, -1),
        ):
            with self.subTest(quantities=quantities, direction=direction, timestamp=timestamp):
                with self.assertRaises(ValueError):
                    ledger.apply("invalid", quantities, direction, timestamp)
        self.assertEqual(sum(ledger.counts.values()), 0)


if __name__ == "__main__":
    unittest.main()
