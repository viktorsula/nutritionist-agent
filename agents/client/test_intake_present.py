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

    def test_injects_history_and_summary(self):
        # Регресс: intake-ответ должен видеть контекст (иначе повторно здоровается).
        rec = from_diary_extract({"kind": "meal", "ingredients": ["курица"], "meal_type": "lunch"})
        state = _state(
            conversation_summary="Клиент на снижении веса, аллергия на орехи.",
            conversation_history=[
                {"role": "user", "content": "Привет"},
                {"role": "assistant", "content": "Привет, Катя!"},
            ],
        )
        with patch("agents.client.intake_present.call_llm",
                   return_value={"content": "ok", "model": "m", "usage": {}}) as llm:
            p.present(state, rec, prompt_name="client/diary_system")
        msgs = llm.call_args.kwargs["messages"]
        # система содержит сводку
        self.assertIn("снижении веса", msgs[0]["content"])
        # предыдущие реплики идут ДО фактов текущего хода
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertEqual(msgs[1]["content"], "Привет")
        self.assertIn("курица", msgs[-1]["content"])  # факты — последним

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


class TestClarifyFromUncertainties(unittest.TestCase):
    def test_one_message_lists_all(self):
        rec = {"uncertainties": ["объём курицы", "рис отварной или жареный"]}
        out = p.clarify_from_uncertainties({"client_profile": {"name": "Катя"}}, rec)
        self.assertIn("Катя", out)
        self.assertIn("1) объём курицы", out)
        self.assertIn("2) рис отварной или жареный", out)

    def test_empty_when_no_uncertainties(self):
        self.assertEqual(p.clarify_from_uncertainties({}, {"uncertainties": []}), "")
        self.assertEqual(p.clarify_from_uncertainties({}, {}), "")


if __name__ == "__main__":
    unittest.main()
