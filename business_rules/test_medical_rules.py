"""
Тесты business_rules/medical_rules.py::_check_food_forbidden (P0-1).

Ограничения нутрициолог правит через редактор плана, они лежат в
nutrition_plans.plan_json.restrictions (верхнеуровневой колонки restrictions нет в схеме).
Запуск: python -m pytest business_rules/test_medical_rules.py
"""

import unittest
from unittest.mock import patch

from business_rules.medical_rules import _check_food_forbidden


class TestCheckFoodForbidden(unittest.TestCase):
    def test_reads_restrictions_from_plan_json(self):
        # Матчинг в коде — по подстроке (не семантический), поэтому продукт должен
        # текстово пересекаться с ограничением: этот тест проверяет ТОЛЬКО то, что
        # чтение поля исправлено (plan_json.restrictions), не качество матчинга.
        plan = {"plan_json": {"restrictions": ["сыр", "глютен"]}}
        with patch("business_rules.medical_rules.get_active_nutrition_plan", return_value=plan):
            result = _check_food_forbidden("cid", ["козий сыр"])
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "food_forbidden")
        self.assertIn("козий сыр", result["details"]["forbidden_items"])

    def test_fallback_to_top_level_restrictions_for_old_records(self):
        plan = {"restrictions": ["орехи"]}
        with patch("business_rules.medical_rules.get_active_nutrition_plan", return_value=plan):
            result = _check_food_forbidden("cid", ["орехи кешью"])
        self.assertIsNotNone(result)

    def test_no_plan_returns_none(self):
        with patch("business_rules.medical_rules.get_active_nutrition_plan", return_value=None):
            result = _check_food_forbidden("cid", ["что угодно"])
        self.assertIsNone(result)

    def test_no_restrictions_returns_none(self):
        plan = {"plan_json": {"restrictions": []}}
        with patch("business_rules.medical_rules.get_active_nutrition_plan", return_value=plan):
            result = _check_food_forbidden("cid", ["курица"])
        self.assertIsNone(result)

    def test_no_match_returns_none(self):
        plan = {"plan_json": {"restrictions": ["молочные продукты"]}}
        with patch("business_rules.medical_rules.get_active_nutrition_plan", return_value=plan):
            result = _check_food_forbidden("cid", ["курица", "рис"])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
