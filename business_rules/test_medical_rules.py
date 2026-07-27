"""
Тесты business_rules/medical_rules.py: _check_food_forbidden (P0-1), пороги алертов
из system_settings.alert_thresholds (P1-4), _check_food_incompatible через pgvector
(P1-3), отсутствие _check_bad_wellbeing как мёртвого кода (P1-5).

Ограничения нутрициолог правит через редактор плана, они лежат в
nutrition_plans.plan_json.restrictions (верхнеуровневой колонки restrictions нет в схеме).
Запуск: python -m pytest business_rules/test_medical_rules.py
"""

import unittest
from unittest.mock import patch

import business_rules.medical_rules as medical_rules
from business_rules.medical_rules import (
    _check_food_forbidden,
    _check_food_incompatible,
    _check_no_response,
    _check_weight_increase,
    _get_alert_thresholds,
)


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


class TestCheckAllergiesVsIntolerances(unittest.TestCase):
    """P1-13 шаг 1: аллергия и непереносимость — разные состояния, разная severity."""

    def _profile(self, allergies=None, intolerances=None):
        return {"allergies": allergies or [], "intolerances": intolerances or []}

    def test_allergen_is_critical(self):
        with patch("business_rules.medical_rules.get_client_profile",
                   return_value=self._profile(allergies=["орехи"])):
            r = medical_rules.check_allergies("cid", ["орехи кешью"])
        self.assertTrue(r["has_allergen"])
        self.assertEqual(r["severity"], "critical")
        self.assertIn("орехи", r["allergens_found"])

    def test_intolerance_is_medium_and_not_flagged_as_allergen(self):
        # Ключевое: непереносимость НЕ абсолютный запрет — has_allergen остаётся False,
        # иначе система запретила бы то, что решает нутрициолог.
        with patch("business_rules.medical_rules.get_client_profile",
                   return_value=self._profile(intolerances=["лактоза"])):
            r = medical_rules.check_allergies("cid", ["лактоза"])
        self.assertFalse(r["has_allergen"])
        self.assertEqual(r["severity"], "medium")
        self.assertIn("лактоза", r["intolerances_found"])

    def test_allergen_takes_priority_over_intolerance(self):
        with patch("business_rules.medical_rules.get_client_profile",
                   return_value=self._profile(allergies=["орехи"], intolerances=["лактоза"])):
            r = medical_rules.check_allergies("cid", ["орехи", "лактоза"])
        self.assertEqual(r["severity"], "critical")
        self.assertIn("орехи", r["allergens_found"])
        self.assertIn("лактоза", r["intolerances_found"])  # не теряется

    def test_clean_meal_returns_none_severity(self):
        with patch("business_rules.medical_rules.get_client_profile",
                   return_value=self._profile(allergies=["орехи"], intolerances=["лактоза"])):
            r = medical_rules.check_allergies("cid", ["курица", "рис"])
        self.assertFalse(r["has_allergen"])
        self.assertEqual(r["severity"], "none")

    def test_empty_profile_is_safe(self):
        with patch("business_rules.medical_rules.get_client_profile", return_value={}):
            r = medical_rules.check_allergies("cid", ["что угодно"])
        self.assertEqual(r["severity"], "none")

    def test_db_failure_reports_error_not_clean(self):
        # Сбой проверки не должен выглядеть как «проверено, аллергенов нет».
        with patch("business_rules.medical_rules.get_client_profile",
                   side_effect=RuntimeError("db down")):
            r = medical_rules.check_allergies("cid", ["орехи"])
        self.assertEqual(r["severity"], "error")
        self.assertFalse(r["has_allergen"])

    def test_no_ingredients_short_circuits(self):
        with patch("business_rules.medical_rules.get_client_profile") as prof:
            r = medical_rules.check_allergies("cid", [])
        prof.assert_not_called()
        self.assertEqual(r["severity"], "none")


class TestGetAlertThresholds(unittest.TestCase):
    def test_reads_alert_thresholds_setting(self):
        with patch("business_rules.medical_rules.get_setting",
                   return_value={"weight_increase_kg": 2, "no_response_hours": 24}):
            result = _get_alert_thresholds()
        self.assertEqual(result, {"weight_increase_kg": 2, "no_response_hours": 24})

    def test_empty_when_setting_missing(self):
        with patch("business_rules.medical_rules.get_setting", return_value=None):
            self.assertEqual(_get_alert_thresholds(), {})

    def test_empty_when_setting_not_a_dict(self):
        with patch("business_rules.medical_rules.get_setting", return_value="oops"):
            self.assertEqual(_get_alert_thresholds(), {})

    def test_empty_on_exception(self):
        with patch("business_rules.medical_rules.get_setting", side_effect=RuntimeError("down")):
            self.assertEqual(_get_alert_thresholds(), {})


class TestCheckWeightIncreaseThreshold(unittest.TestCase):
    def test_uses_alert_thresholds_setting_key(self):
        # Порог берётся из alert_thresholds.weight_increase_kg (не из несуществующей
        # отдельной строки weight_increase_threshold_kg — P1-4).
        with patch("business_rules.medical_rules.get_client_profile", return_value={}), \
             patch("business_rules.medical_rules.get_setting",
                   return_value={"weight_increase_kg": 0.5}), \
             patch("business_rules.medical_rules.get_recent_measurements", return_value=[
                 {"weight": 71, "measured_at": "2026-07-25"},
                 {"weight": 70, "measured_at": "2026-07-24"},
             ]):
            result = _check_weight_increase("cid")
        self.assertIsNotNone(result)
        self.assertEqual(result["details"]["threshold_kg"], 0.5)

    def test_custom_client_threshold_overrides_global(self):
        with patch("business_rules.medical_rules.get_client_profile",
                   return_value={"custom_alert_thresholds": {"weight_increase_threshold": 0.1}}), \
             patch("business_rules.medical_rules.get_setting",
                   return_value={"weight_increase_kg": 5}), \
             patch("business_rules.medical_rules.get_recent_measurements", return_value=[
                 {"weight": 70.2, "measured_at": "2026-07-25"},
                 {"weight": 70, "measured_at": "2026-07-24"},
             ]):
            result = _check_weight_increase("cid")
        self.assertIsNotNone(result)
        self.assertEqual(result["details"]["threshold_kg"], 0.1)

    def test_falls_back_to_hardcoded_default_when_no_settings(self):
        with patch("business_rules.medical_rules.get_client_profile", return_value={}), \
             patch("business_rules.medical_rules.get_setting", return_value=None), \
             patch("business_rules.medical_rules.get_recent_measurements", return_value=[
                 {"weight": 72, "measured_at": "2026-07-25"},
                 {"weight": 70, "measured_at": "2026-07-24"},
             ]):
            result = _check_weight_increase("cid")
        self.assertIsNotNone(result)
        self.assertEqual(result["details"]["threshold_kg"], 1.0)


class TestCheckNoResponseThreshold(unittest.TestCase):
    def test_uses_alert_thresholds_setting_key(self):
        old_ts = "2026-07-01T00:00:00+00:00"
        with patch("business_rules.medical_rules.get_setting",
                   return_value={"no_response_hours": 1}), \
             patch("business_rules.medical_rules.get_conversations", return_value=[
                 {"role": "client", "message_timestamp": old_ts},
             ]):
            result = _check_no_response("cid")
        self.assertIsNotNone(result)
        self.assertEqual(result["details"]["threshold_hours"], 1)

    def test_falls_back_to_48h_default(self):
        recent_ts = medical_rules.datetime.utcnow().isoformat()
        with patch("business_rules.medical_rules.get_setting", return_value=None), \
             patch("business_rules.medical_rules.get_conversations", return_value=[
                 {"role": "client", "message_timestamp": recent_ts},
             ]):
            result = _check_no_response("cid")
        self.assertIsNone(result)  # только что писал — порог 48ч не превышен


class TestCheckFoodIncompatible(unittest.TestCase):
    def test_single_item_never_checked(self):
        with patch("utils.knowledge.search_knowledge_base") as search_mock:
            result = _check_food_incompatible("cid", ["молоко"])
        self.assertIsNone(result)
        search_mock.assert_not_called()

    def test_no_match_returns_none(self):
        with patch("utils.knowledge.search_knowledge_base", return_value=[]):
            result = _check_food_incompatible("cid", ["молоко", "рыба"])
        self.assertIsNone(result)

    def test_match_above_threshold_returns_alert(self):
        chunks = [{"chunk_text": "Молоко и рыба вместе плохо усваиваются.",
                   "similarity": 0.9, "source": "doc1"}]
        with patch("utils.knowledge.search_knowledge_base", return_value=chunks) as search_mock:
            result = _check_food_incompatible("cid", ["молоко", "рыба"])
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "food_incompatible")
        self.assertEqual(result["severity"], "medium")
        self.assertIn("Молоко и рыба", result["message"])
        # Порог похожести передан явно, не полагаемся на дефолт 0.0 (P2-2).
        self.assertEqual(search_mock.call_args.kwargs["similarity_threshold"], 0.75)

    def test_search_exception_returns_none(self):
        with patch("utils.knowledge.search_knowledge_base", side_effect=RuntimeError("down")):
            result = _check_food_incompatible("cid", ["молоко", "рыба"])
        self.assertIsNone(result)


class TestBadWellbeingRemoved(unittest.TestCase):
    def test_check_bad_wellbeing_no_longer_exists(self):
        # P1-5: _check_bad_wellbeing был мёртвым кодом (всегда падал с TypeError,
        # результат нигде не потреблялся) — удалён, а не починен.
        self.assertFalse(hasattr(medical_rules, "_check_bad_wellbeing"))

    def test_check_medical_alerts_does_not_crash_without_it(self):
        with patch("business_rules.medical_rules.get_client_profile", return_value={}), \
             patch("business_rules.medical_rules.get_setting", return_value={}), \
             patch("business_rules.medical_rules.get_recent_measurements", return_value=[]), \
             patch("business_rules.medical_rules.get_conversations", return_value=[]):
            alerts = medical_rules.check_medical_alerts("cid")
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
