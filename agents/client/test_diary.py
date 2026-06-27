"""
Тесты dairy-логики 1.4: тип приёма пищи (resolve_meal_type) и фиксация воды.
"""

import unittest
from unittest.mock import patch

from agents.client.food_analysis import resolve_meal_type
from agents.client import diary_agent


class TestResolveMealType(unittest.TestCase):
    def test_explicit_wins(self):
        self.assertEqual(resolve_meal_type("неважно", explicit="dinner"), "dinner")

    def test_markers_in_text(self):
        self.assertEqual(resolve_meal_type("на завтрак овсянка"), "breakfast")
        self.assertEqual(resolve_meal_type("в обед суп"), "lunch")
        self.assertEqual(resolve_meal_type("ужин: рыба"), "dinner")
        self.assertEqual(resolve_meal_type("перекус — яблоко"), "snack")
        self.assertEqual(resolve_meal_type("рацион на весь день"), "all_day")

    def test_falls_back_to_time(self):
        # без маркеров → по времени суток; значение из допустимых
        self.assertIn(resolve_meal_type("просто поел"), ("breakfast", "lunch", "dinner", "snack"))


class TestHandleWater(unittest.TestCase):
    def test_logs_water_event(self):
        state = {"client_id": "c", "channel": "telegram"}
        with patch("database.queries.log_client_event") as log:
            outcome = diary_agent._handle_water(state, {"water_ml": 2000}, "full_program")
        self.assertEqual(outcome, "water")
        log.assert_called_once()
        kwargs = log.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "water_logged")
        self.assertEqual(kwargs["payload"]["water_ml"], 2000)

    def test_no_value_is_other(self):
        with patch("database.queries.log_client_event") as log:
            outcome = diary_agent._handle_water({"client_id": "c"}, {"water_ml": None}, "full_program")
        self.assertEqual(outcome, "other")
        log.assert_not_called()

    def test_subtype_mapping(self):
        # lab → labs, остальные как есть, other → None
        self.assertEqual(diary_agent._SUBTYPE_OF["lab"], "labs")
        self.assertEqual(diary_agent._SUBTYPE_OF["water"], "water")
        self.assertIsNone(diary_agent._SUBTYPE_OF["other"])


if __name__ == "__main__":
    unittest.main()
