"""
Тесты intake_store.persist_record (Слайс 2): единая запись фактов из IntakeRecord.
Мокаем БД и анализ рациона. Запуск: python -m pytest agents/client/test_intake_store.py
"""

import unittest
from unittest.mock import patch

from agents.client import intake_store
from agents.client.intake_schema import from_diary_extract, empty_record


def _state():
    return {"client_id": "c", "channel": "telegram", "access_info": {"mode": "full_program"}}


class TestPersistWater(unittest.TestCase):
    def test_logs_water(self):
        rec = from_diary_extract({"kind": "water", "water_ml": 2000})
        with patch("database.queries.log_client_event") as log:
            out = intake_store.persist_record(_state(), rec)
        self.assertEqual(out, "water")
        self.assertEqual(log.call_args.kwargs["event_type"], "water_logged")
        self.assertEqual(log.call_args.kwargs["payload"]["water_ml"], 2000.0)

    def test_zero_is_none(self):
        rec = from_diary_extract({"kind": "water", "water_ml": 0})
        with patch("database.queries.log_client_event") as log:
            out = intake_store.persist_record(_state(), rec)
        self.assertIsNone(out)
        log.assert_not_called()


class TestPersistMeal(unittest.TestCase):
    def test_logs_meal_and_food_items(self):
        rec = from_diary_extract({"kind": "meal", "ingredients": ["курица", "рис"], "meal_type": "lunch"})
        state = _state()
        with patch("agents.client.intake_store.analyze_against_plan", return_value=[]) as ap, \
             patch("database.queries.log_client_event") as log:
            out = intake_store.persist_record(state, rec)
        self.assertEqual(out, "meal")
        self.assertEqual(state["food_items"], ["курица", "рис"])
        ap.assert_called_once()
        self.assertEqual(log.call_args.kwargs["event_type"], "calories_logged")
        payload = log.call_args.kwargs["payload"]
        self.assertEqual(payload["ingredients"], ["курица", "рис"])
        self.assertEqual(payload["meal_type"], "lunch")

    def test_meal_alert_sets_routing(self):
        rec = from_diary_extract({"kind": "meal", "ingredients": ["торт"]})
        state = _state()
        alert = {"type": "food_forbidden", "severity": "high", "message": "запрещено"}
        with patch("agents.client.intake_store.analyze_against_plan", return_value=[alert]), \
             patch("database.queries.log_client_event"):
            out = intake_store.persist_record(state, rec)
        self.assertEqual(out, "meal")
        self.assertIn(alert, state["alerts"])
        self.assertIsNotNone(state.get("routing"))

    def test_no_items_is_none(self):
        rec = empty_record("meal", "text")
        rec["meal"] = {"meal_type": "lunch", "items": [], "total": {}}
        with patch("database.queries.log_client_event") as log:
            out = intake_store.persist_record(_state(), rec)
        self.assertIsNone(out)
        log.assert_not_called()


class TestPersistWeight(unittest.TestCase):
    def test_inserts_measurement(self):
        rec = from_diary_extract({"kind": "weight", "weight_kg": "80,5"})
        with patch("database.queries.insert_measurement") as ins, \
             patch("business_rules.medical_rules.check_medical_alerts", return_value=[]):
            out = intake_store.persist_record(_state(), rec)
        self.assertEqual(out, "weight")
        self.assertEqual(ins.call_args.kwargs["weight"], 80.5)


class TestPersistWellbeing(unittest.TestCase):
    def test_bad_adds_alert(self):
        rec = from_diary_extract({"kind": "wellbeing", "wellbeing": {"answer": "плохо", "reason": "болит голова"}})
        state = _state()
        with patch("database.queries.log_client_event") as log:
            out = intake_store.persist_record(state, rec)
        self.assertEqual(out, "wellbeing")
        self.assertEqual(log.call_args.kwargs["event_type"], "bad_wellbeing")
        self.assertEqual(log.call_args.kwargs["severity"], "medium")
        self.assertTrue(any(a["type"] == "bad_wellbeing" for a in state["alerts"]))

    def test_ok_no_alert(self):
        rec = from_diary_extract({"kind": "wellbeing", "wellbeing": {"answer": "нормально", "reason": ""}})
        state = _state()
        with patch("database.queries.log_client_event") as log:
            out = intake_store.persist_record(state, rec)
        self.assertEqual(out, "wellbeing")
        self.assertEqual(log.call_args.kwargs["event_type"], "wellbeing_logged")
        self.assertNotIn("alerts", {k: v for k, v in state.items() if v})  # алертов не добавили


class TestPersistLab(unittest.TestCase):
    def test_inserts_labs(self):
        rec = from_diary_extract({"kind": "lab", "labs": [{"indicator": "Холестерин", "value": "5.2", "unit": "mmol/L"}]})
        state = _state()
        with patch("database.queries.insert_lab_result") as ins:
            out = intake_store.persist_record(state, rec)
        self.assertEqual(out, "labs")
        self.assertEqual(ins.call_args.kwargs["indicator"], "холестерин")
        self.assertEqual(ins.call_args.kwargs["value"], 5.2)
        self.assertEqual(ins.call_args.kwargs["source"], "client")
        self.assertEqual(state["saved_labs"][0]["indicator"], "холестерин")


class TestPersistNone(unittest.TestCase):
    def test_none_kind_returns_none(self):
        rec = from_diary_extract({"kind": "other"})
        self.assertIsNone(intake_store.persist_record(_state(), rec))


if __name__ == "__main__":
    unittest.main()
