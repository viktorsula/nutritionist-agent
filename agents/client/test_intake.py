"""
Тесты определителя темы (intake).

call_llm мокается: проверяем разбор/валидацию/агрегацию, не реальный LLM.
Таксономия — 3 верхнеуровневые ветки: intake | profile | advice (см. branches.py).
"""

import unittest
from unittest.mock import patch

from agents.client import intake
from agents.client.branches import (
    ACK,
    ANSWER,
    CLARIFY,
    INTAKE,
    PROFILE,
    ADVICE,
    FALLBACK_BRANCH,
    VALID_BRANCHES,
    VALID_INTAKE_SUBTYPES,
    default_answer,
    is_valid_branch,
    is_valid_intake_subtype,
)


def _llm(content: str):
    """Заглушка call_llm: возвращает заданный content."""
    return lambda *a, **k: {"content": content, "model": "test"}


class TestBranches(unittest.TestCase):
    def test_taxonomy_has_three_branches(self):
        self.assertEqual(VALID_BRANCHES, {INTAKE, PROFILE, ADVICE})

    def test_default_answer_by_branch(self):
        self.assertEqual(default_answer(INTAKE), ACK)
        self.assertEqual(default_answer(PROFILE), ANSWER)
        self.assertEqual(default_answer(ADVICE), ANSWER)

    def test_unknown_branch_defaults_to_answer(self):
        self.assertFalse(is_valid_branch("whatever"))
        self.assertEqual(default_answer("whatever"), ANSWER)

    def test_fallback_is_profile(self):
        self.assertEqual(FALLBACK_BRANCH, PROFILE)

    def test_intake_subtypes(self):
        # под-типы хранения ветки intake (нижний уровень)
        for key in ("meal", "water", "weight", "wellbeing", "labs", "document"):
            self.assertIn(key, VALID_INTAKE_SUBTYPES)
            self.assertTrue(is_valid_intake_subtype(key))
        self.assertFalse(is_valid_intake_subtype("nope"))


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
    def test_single_intake_is_ack(self):
        parts = [{"kind": "text", "text": "на ужин курица с рисом"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"intake","parts":[0],"needs_answer":"ack"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], ACK)
        self.assertEqual(len(out["segments"]), 1)
        self.assertEqual(out["segments"][0]["branch"], INTAKE)

    def test_multi_segment_intake_plus_advice_is_answer(self):
        parts = [
            {"kind": "photo", "image_kind": "food", "text": "это мой ужин"},
            {"kind": "text", "text": "а что съесть завтра на обед?"},
        ]
        content = (
            '{"segments":['
            '{"branch":"intake","parts":[0],"needs_answer":"ack"},'
            '{"branch":"advice","parts":[1],"needs_answer":"answer"}]}'
        )
        with patch.object(intake, "call_llm", _llm(content)):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], ANSWER)  # агрегат: есть answer
        self.assertEqual([s["branch"] for s in out["segments"]], [INTAKE, ADVICE])

    def test_report_plus_question_on_one_part(self):
        # «холестерин 5.2, это нормально?» → intake/ack + profile/answer на одной части
        parts = [{"kind": "text", "text": "холестерин 5.2, это нормально?"}]
        content = (
            '{"segments":['
            '{"branch":"intake","parts":[0],"needs_answer":"ack"},'
            '{"branch":"profile","parts":[0],"needs_answer":"answer"}]}'
        )
        with patch.object(intake, "call_llm", _llm(content)):
            out = intake.determine_turn(parts)
        self.assertEqual([s["branch"] for s in out["segments"]], [INTAKE, PROFILE])
        self.assertEqual(out["needs_answer"], ANSWER)

    def test_invalid_branch_falls_back_to_profile(self):
        parts = [{"kind": "text", "text": "hmm"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"bogus","parts":[0],"needs_answer":"answer"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["segments"][0]["branch"], PROFILE)

    def test_bad_part_indices_are_corrected(self):
        parts = [{"kind": "text", "text": "вешу 80"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"intake","parts":[5,9],"needs_answer":"ack"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["segments"][0]["parts"], [0])  # некорректные индексы → все части

    def test_bad_needs_answer_uses_branch_default(self):
        parts = [{"kind": "text", "text": "что съесть на обед?"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"advice","parts":[0]}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["segments"][0]["needs_answer"], ANSWER)

    def test_llm_error_falls_back_to_clarify(self):
        # Определитель не смог разобрать ход → не угадываем, спрашиваем клиента.
        parts = [{"kind": "text", "text": "какой-то вопрос"}]
        def boom(*a, **k):
            raise RuntimeError("llm down")
        with patch.object(intake, "call_llm", boom):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], CLARIFY)
        self.assertEqual(out["segments"][0]["needs_answer"], CLARIFY)

    def test_clarify_segment_passes_through(self):
        parts = [{"kind": "text", "text": "асдфг 3#"}]
        with patch.object(intake, "call_llm", _llm('{"segments":[{"branch":"profile","parts":[0],"needs_answer":"clarify"}]}')):
            out = intake.determine_turn(parts)
        self.assertEqual(out["needs_answer"], CLARIFY)
        self.assertEqual(out["segments"][0]["needs_answer"], CLARIFY)

    def test_empty_parts(self):
        out = intake.determine_turn([])
        self.assertEqual(out["segments"], [])
        self.assertEqual(out["needs_answer"], ANSWER)


if __name__ == "__main__":
    unittest.main()
