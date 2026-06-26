"""
Тесты определителя темы (intake) — Фаза 1.

call_llm мокается: проверяем разбор/валидацию/агрегацию, не реальный LLM.
"""

import unittest
from unittest.mock import patch

from agents.client import intake
from agents.client.branches import (
    ACK,
    ANSWER,
    VALID_BRANCHES,
    default_answer,
    is_valid_branch,
)


def _llm(content: str):
    """Заглушка call_llm: возвращает заданный content."""
    return lambda *a, **k: {"content": content, "model": "test"}


class TestBranches(unittest.TestCase):
    def test_taxonomy_has_eight_branches(self):
        self.assertEqual(len(VALID_BRANCHES), 8)

    def test_default_answer_by_branch(self):
        self.assertEqual(default_answer("meal"), ACK)
        self.assertEqual(default_answer("labs"), ACK)
        self.assertEqual(default_answer("nutrition_q"), ANSWER)
        self.assertEqual(default_answer("own_data"), ANSWER)

    def test_unknown_branch_defaults_to_answer(self):
        self.assertFalse(is_valid_branch("whatever"))
        self.assertEqual(default_answer("whatever"), ANSWER)


class TestBuildTurnView(unittest.TestCase):
    def test_renders_parts_with_kind_and_image_hint(self):
        parts = [
            {"kind": "text", "text": "это мой ужин"},
            {"kind": "photo", "image_kind": "food", "text": ""},
        ]
        view = intake.build_turn_view(parts)
        self.assertIn("Часть 0 [текст]: это мой ужин", view)
        self.assertIn("Часть 1 [фото: распознано как food]: —", view)


class TestDetermineTurn(unittest.TestCase):
    def test_single_meal_is_ack(self):
        parts = [{"kind": "text", "text": "на ужин курица с рисом"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"meal","parts":[0],"needs_answer":"ack"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], ACK)
        self.assertEqual(len(out["segments"]), 1)
        self.assertEqual(out["segments"][0]["branch"], "meal")

    def test_multi_segment_meal_plus_question_is_answer(self):
        parts = [
            {"kind": "photo", "image_kind": "food", "text": "это мой ужин"},
            {"kind": "text", "text": "а что съесть завтра на обед?"},
        ]
        content = (
            '{"segments":['
            '{"branch":"meal","parts":[0],"needs_answer":"ack"},'
            '{"branch":"nutrition_q","parts":[1],"needs_answer":"answer"}]}'
        )
        with patch.object(intake, "call_llm", _llm(content)):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], ANSWER)  # агрегат: есть answer
        self.assertEqual([s["branch"] for s in out["segments"]], ["meal", "nutrition_q"])

    def test_invalid_branch_falls_back_to_dialog(self):
        parts = [{"kind": "text", "text": "hmm"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"bogus","parts":[0],"needs_answer":"answer"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["segments"][0]["branch"], "dialog")

    def test_bad_part_indices_are_corrected(self):
        parts = [{"kind": "text", "text": "вешу 80"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"weight","parts":[5,9],"needs_answer":"ack"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["segments"][0]["parts"], [0])  # некорректные индексы → все части

    def test_bad_needs_answer_uses_branch_default(self):
        parts = [{"kind": "text", "text": "что съесть на обед?"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"nutrition_q","parts":[0]}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["segments"][0]["needs_answer"], ANSWER)

    def test_llm_error_falls_back_to_dialog_answer(self):
        parts = [{"kind": "text", "text": "какой-то вопрос"}]
        def boom(*a, **k):
            raise RuntimeError("llm down")
        with patch.object(intake, "call_llm", boom):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], ANSWER)
        self.assertEqual(out["segments"][0]["branch"], "dialog")

    def test_empty_parts(self):
        out = intake.determine_turn([])
        self.assertEqual(out["segments"], [])
        self.assertEqual(out["needs_answer"], ANSWER)


if __name__ == "__main__":
    unittest.main()
