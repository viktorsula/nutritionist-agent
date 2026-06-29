"""
Тесты diary-логики: тип приёма пищи (resolve_meal_type) и маппинг под-типа для подачи.
Запись фактов (вода/вес/еда/…) тестируется на уровне intake_store (test_intake_store.py).
"""

import unittest

from agents.client.food_analysis import resolve_meal_type


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


if __name__ == "__main__":
    unittest.main()
