"""
Тесты present-слоя (Слайс 3): тёплый ответ из IntakeRecord. call_llm замокан.
Запуск: python -m pytest agents/client/test_intake_present.py
"""

import unittest
from unittest.mock import patch

from agents.client import intake_present as p
from agents.client.intake_schema import from_diary_extract, normalize


def _state(**extra):
    base = {"message": "съел курицу с рисом", "client_profile": {"name": "Катя"}, "active_plan": {}}
    base.update(extra)
    return base


class TestPresent(unittest.TestCase):
    def test_uses_llm_and_sets_model(self):
        rec = from_diary_extract({"kind": "meal", "ingredients": ["курица", "рис"], "meal_type": "lunch"})
        with patch("agents.client.intake_present.call_llm",
                   return_value={"content": "Записал обед!", "model": "groq-x", "usage": {}}) as llm:
            out = p.present(_state(), rec, prompt_name="client/diary_system")
        self.assertEqual(out, "Записал обед!")
        # факты для LLM собраны из записи: состав попал в user-сообщение
        facts = llm.call_args.kwargs["messages"][1]["content"]
        self.assertIn("курица", facts)
        self.assertIn("рис", facts)

    def test_fallback_on_llm_error(self):
        rec = from_diary_extract({"kind": "weight", "weight_kg": 80})
        with patch("agents.client.intake_present.call_llm", side_effect=RuntimeError("down")):
            out = p.present(_state(), rec, prompt_name="client/diary_system")
        self.assertIn("вес", out.lower())

    def test_facts_include_alerts(self):
        rec = from_diary_extract({"kind": "meal", "ingredients": ["торт"]})
        state = _state(alerts=[{"type": "food_forbidden", "severity": "high", "message": "запрещено"}])
        facts = p._facts_from_record(state, normalize(rec))
        self.assertIn("food_forbidden", facts)
        self.assertIn("запрещено", facts)

    def test_facts_meal_kbju_and_dish(self):
        rec = normalize({
            "kind": "meal", "source": "photo",
            "meal": {"meal_type": "lunch", "dish_name": "Плов",
                     "items": [{"name": "рис", "kbju": {"kcal": 200}}]},
        })
        facts = p._facts_from_record(_state(), rec)
        self.assertIn("Плов", facts)
        self.assertIn("200", facts)  # КБЖУ справочно

    def test_fallback_per_kind(self):
        self.assertIn("анализов", p._fallback({"kind": "lab"}))
        self.assertIn("самочувствием", p._fallback({"kind": "wellbeing"}))
        self.assertEqual(p._fallback({"kind": "none"}), "Принято ✅")


if __name__ == "__main__":
    unittest.main()
