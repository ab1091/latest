import asyncio
import unittest
from datetime import datetime

from api.sms.router import _has_explicit_slot_and_email_approval, _next_five_minute_start


class AppointmentConfirmationGateTests(unittest.TestCase):
    def test_broad_window_does_not_book(self):
        history = [
            {"role": "agent", "content": "What works best: morning, afternoon, or evening?"},
            {"role": "user", "content": "Morning"},
            {"role": "agent", "content": "I can offer Tuesday at 9:00 AM."},
        ]
        self.assertFalse(asyncio.run(_has_explicit_slot_and_email_approval(history)))

    def test_collision_advances_in_five_minute_steps(self):
        requested = datetime(2026, 8, 4, 9, 0)
        occupied = [
            datetime(2026, 8, 4, 9, 0),
            datetime(2026, 8, 4, 9, 5),
        ]
        self.assertEqual(
            _next_five_minute_start(requested, occupied),
            datetime(2026, 8, 4, 9, 10),
        )

    def test_open_requested_time_is_unchanged(self):
        requested = datetime(2026, 8, 4, 9, 0)
        self.assertEqual(
            _next_five_minute_start(requested, [datetime(2026, 8, 4, 10, 0)]),
            requested,
        )

    def test_exact_slot_without_email_does_not_book(self):
        history = [
            {"role": "agent", "content": "I can offer Tuesday at 9:00 AM. Does that work?"},
            {"role": "user", "content": "Yes please"},
        ]
        self.assertFalse(asyncio.run(_has_explicit_slot_and_email_approval(history)))

    def test_slot_and_email_must_be_explicitly_approved(self):
        history = [
            {
                "role": "agent",
                "content": (
                    "I can offer Tuesday at 9:00 AM and send the invite to jane@example.com. "
                    "Please confirm that both are correct."
                ),
            },
            {"role": "user", "content": "Yes please, that works"},
            {"role": "agent", "content": "Thanks, I'll check availability."},
        ]
        self.assertTrue(asyncio.run(_has_explicit_slot_and_email_approval(history)))

    def test_correction_requires_a_new_confirmation_turn(self):
        history = [
            {
                "role": "agent",
                "content": (
                    "I can offer Tuesday at 9:00 AM and send the invite to jane@example.com. "
                    "Please confirm that both are correct."
                ),
            },
            {"role": "user", "content": "No, use new@example.com instead"},
            {
                "role": "agent",
                "content": (
                    "I can offer Tuesday at 9:00 AM and send the invite to new@example.com. "
                    "Please confirm that both are correct."
                ),
            },
        ]
        self.assertFalse(asyncio.run(_has_explicit_slot_and_email_approval(history)))

    def test_qualified_yes_with_rejection_does_not_book(self):
        history = [
            {
                "role": "agent",
                "content": (
                    "I can offer tomorrow at 2:00 PM and send the invite to jane@example.com. "
                    "Does this slot and email work?"
                ),
            },
            {"role": "user", "content": "Yes, but that time doesn't work"},
        ]
        self.assertFalse(asyncio.run(_has_explicit_slot_and_email_approval(history)))


if __name__ == "__main__":
    unittest.main()
