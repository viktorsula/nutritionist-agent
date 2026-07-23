"""
Тесты agents/client/questionnaire_context.py::format_questionnaire_extra (P1-14).
Запуск: python -m pytest agents/client/test_questionnaire_context.py
"""

import unittest

from agents.client.questionnaire_context import format_questionnaire_extra


class TestFormatQuestionnaireExtra(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(format_questionnaire_extra(None), "")

    def test_empty_dict_returns_empty(self):
        self.assertEqual(format_questionnaire_extra({}), "")

    def test_excluded_fields_never_appear(self):
        # Поля, уже отражённые в структурных колонках client_profiles, не дублируются.
        qj = {"birth_date": "1990-01-01", "gender": "female", "weight": 60,
              "chronic_conditions": "диабет", "allergies": {"answer": True, "details": "орехи"}}
        out = format_questionnaire_extra(qj)
        self.assertEqual(out, "")

    def test_plain_textarea_field_included(self):
        out = format_questionnaire_extra({"medications": "витамин D, 2000 МЕ"})
        self.assertIn("Принимаемые препараты", out)
        self.assertIn("витамин D, 2000 МЕ", out)

    def test_empty_field_skipped(self):
        out = format_questionnaire_extra({"medications": "", "supplements": None})
        self.assertEqual(out, "")

    def test_yesno_text_true_with_details(self):
        out = format_questionnaire_extra({"under_doctor": {"answer": True, "details": "эндокринолог"}})
        self.assertIn("На учёте у врача: да — эндокринолог", out)

    def test_yesno_text_false(self):
        out = format_questionnaire_extra({"smoking": {"answer": False, "details": ""}})
        self.assertIn("Курение: нет", out)

    def test_select_option_translated(self):
        out = format_questionnaire_extra({"work_activity": "sedentary"})
        self.assertIn("Активность на работе: Сидячая", out)
        self.assertNotIn("sedentary", out)

    def test_unknown_select_value_falls_back_to_raw(self):
        out = format_questionnaire_extra({"cold_frequency": "unexpected_value"})
        self.assertIn("unexpected_value", out)

    def test_multiple_fields_all_present(self):
        qj = {
            "medications": "нет",
            "stress": "умеренный, по вечерам",
            "water_liters": 1.5,
            "family_support": "supportive",
        }
        out = format_questionnaire_extra(qj)
        lines = out.split("\n")
        self.assertEqual(len(lines), 4)
        self.assertIn("Поддержка семьи в ЗОЖ: Поддерживают", out)


if __name__ == "__main__":
    unittest.main()
