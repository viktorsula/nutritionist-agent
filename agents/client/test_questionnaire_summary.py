"""
Тесты agents/client/questionnaire_summary.py::build_questionnaire_summary (миграция 017).
Запуск: python -m pytest agents/client/test_questionnaire_summary.py
"""

import unittest
from unittest.mock import patch

from agents.client.questionnaire_summary import build_questionnaire_summary


class TestBuildQuestionnaireSummary(unittest.TestCase):
    def test_empty_profile_returns_none_without_calling_llm(self):
        with patch("agents.client.questionnaire_summary.call_llm") as mock_llm:
            result = build_questionnaire_summary({})
        self.assertIsNone(result)
        mock_llm.assert_not_called()

    def test_calls_llm_with_summary_task_type(self):
        profile = {"goals": "снижение веса"}
        with patch("agents.client.questionnaire_summary.call_llm",
                   return_value={"content": "Клиент хочет снизить вес."}) as mock_llm, \
             patch("agents.client.questionnaire_summary.load_prompt", return_value="SYSTEM"):
            result = build_questionnaire_summary(profile)
        self.assertEqual(result, "Клиент хочет снизить вес.")
        self.assertEqual(mock_llm.call_args.kwargs["task_type"], "summary")

    def test_llm_failure_returns_none(self):
        profile = {"goals": "снижение веса"}
        with patch("agents.client.questionnaire_summary.call_llm", side_effect=RuntimeError("down")):
            result = build_questionnaire_summary(profile)
        self.assertIsNone(result)

    def test_truncates_to_max_chars(self):
        from agents.client import questionnaire_summary as qs
        profile = {"goals": "снижение веса"}
        long_text = "а" * 2000
        with patch("agents.client.questionnaire_summary.call_llm",
                   return_value={"content": long_text}), \
             patch("agents.client.questionnaire_summary.load_prompt", return_value="SYSTEM"):
            result = build_questionnaire_summary(profile)
        self.assertEqual(len(result), qs.MAX_SUMMARY_CHARS)


if __name__ == "__main__":
    unittest.main()
