"""
Тесты utils/consent.py::get_consent_text (LEGAL-1, миграция 018).
Запуск: python -m pytest utils/test_consent.py
"""

import unittest
from unittest.mock import patch

from utils.consent import DEFAULT_CONSENT_TEXT, get_consent_text


class TestGetConsentText(unittest.TestCase):
    def test_returns_default_when_no_override(self):
        with patch("database.queries.get_setting", return_value=None):
            self.assertEqual(get_consent_text(), DEFAULT_CONSENT_TEXT)

    def test_returns_default_when_override_has_no_version(self):
        with patch("database.queries.get_setting", return_value={"ru": {}}):
            self.assertEqual(get_consent_text(), DEFAULT_CONSENT_TEXT)

    def test_db_override_replaces_default_wholesale(self):
        override = {"version": "2.0", "ru": {"health_data": "x"}, "en": {}}
        with patch("database.queries.get_setting", return_value=override):
            self.assertEqual(get_consent_text(), override)

    def test_exception_falls_back_to_default(self):
        with patch("database.queries.get_setting", side_effect=RuntimeError("db down")):
            self.assertEqual(get_consent_text(), DEFAULT_CONSENT_TEXT)

    def test_default_has_both_granular_points_ru_and_en(self):
        for lang in ("ru", "en"):
            for key in ("health_data", "telegram_channel"):
                self.assertTrue(DEFAULT_CONSENT_TEXT[lang][key])


if __name__ == "__main__":
    unittest.main()
