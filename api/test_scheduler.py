"""
Тесты планировщика уведомлений (api/scheduler.py) — чистая логика без сети.
"""

import unittest
from datetime import datetime

import pytz

from api import scheduler as S


class TestIsDue(unittest.TestCase):
    def _utc(self, h, m):
        return datetime(2026, 6, 24, h, m, tzinfo=pytz.UTC)

    def test_due_in_client_timezone(self):
        # 08:00 в Asia/Dubai (UTC+4) = 04:00 UTC
        due, stamp = S._is_due("08:00:00", "Asia/Dubai", now_utc=self._utc(4, 0))
        self.assertTrue(due)
        self.assertEqual(stamp, "2026-06-24 08:00")

    def test_not_due_other_minute(self):
        due, _ = S._is_due("08:00:00", "Asia/Dubai", now_utc=self._utc(4, 1))
        self.assertFalse(due)

    def test_utc_zone(self):
        due, _ = S._is_due("09:30:00", "UTC", now_utc=self._utc(9, 30))
        self.assertTrue(due)

    def test_bad_timezone_falls_back_to_utc(self):
        due, _ = S._is_due("09:30:00", "Mars/Phobos", now_utc=self._utc(9, 30))
        self.assertTrue(due)

    def test_empty_scheduled_time(self):
        due, stamp = S._is_due(None, "UTC", now_utc=self._utc(9, 30))
        self.assertFalse(due)
        self.assertEqual(stamp, "")

    def test_malformed_time(self):
        due, _ = S._is_due("notatime", "UTC", now_utc=self._utc(9, 30))
        self.assertFalse(due)


class TestMessageFor(unittest.TestCase):
    def test_known_types(self):
        self.assertIn("утро", S._message_for("morning").lower())
        self.assertIn("вечер", S._message_for("evening").lower())

    def test_unknown_type_defaults_to_reminder(self):
        self.assertEqual(S._message_for("whatever"), S.NOTIFICATION_TEMPLATES["reminder"])
        self.assertEqual(S._message_for(None), S.NOTIFICATION_TEMPLATES["reminder"])


if __name__ == "__main__":
    unittest.main()
