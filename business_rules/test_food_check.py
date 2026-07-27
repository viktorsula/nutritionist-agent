"""
Тесты смысловой проверки продуктов (P1-13, шаг 2).

Главное, что здесь проверяется, — что система НЕ выдаёт «зелёный свет» там, где на самом
деле не знает ответа: сбой модели, сбой БД, мусор в ответе и пропущенный продукт должны
давать 'unclear', а не 'ok'.
"""

import unittest
from unittest.mock import patch

from business_rules import food_check as fc


def _profile(allergies=None, intolerances=None):
    return {"allergies": allergies or [], "intolerances": intolerances or []}


def _plan(restrictions=None):
    return {"plan_json": {"restrictions": restrictions or []}}


def _llm(results):
    """Ответ модели в ожидаемом формате."""
    import json
    return {"content": json.dumps({"results": results}, ensure_ascii=False)}


class TestNoConstraints(unittest.TestCase):
    def setUp(self):
        fc.reset_cache()

    def test_no_constraints_skips_check_entirely(self):
        with patch("database.queries.get_client_profile", return_value=_profile()), \
             patch("database.queries.get_active_nutrition_plan", return_value=_plan()), \
             patch("utils.llm.call_llm") as llm:
            r = fc.check_food("cid", ["курица"])
        llm.assert_not_called()
        self.assertFalse(r["checked"])
        self.assertFalse(r["blocked"])

    def test_no_items_is_noop(self):
        with patch("database.queries.get_client_profile") as prof:
            r = fc.check_food("cid", [])
        prof.assert_not_called()
        self.assertFalse(r["checked"])


class TestVerdicts(unittest.TestCase):
    def setUp(self):
        fc.reset_cache()

    def _run(self, items, results, direction="incoming"):
        with patch("database.queries.get_client_profile",
                   return_value=_profile(allergies=["орехи"])), \
             patch("database.queries.get_active_nutrition_plan",
                   return_value=_plan(["молочные продукты, кроме козьего"])), \
             patch("business_rules.food_check._knowledge_context", return_value=""), \
             patch("prompts.load_prompt", return_value="sys"), \
             patch("utils.llm.call_llm", return_value=_llm(results)):
            return fc.check_food("cid", items, direction=direction)

    def test_violation_detected_semantically(self):
        # Смысл всей задачи: «кешью» не содержит подстроки «орехи».
        r = self._run(["кешью"], [
            {"item": "кешью", "verdict": "violates", "reason": "кешью — орех", "source": "allergies"},
        ])
        self.assertEqual(len(r["violations"]), 1)
        self.assertTrue(r["blocked"])

    def test_explicit_exception_is_respected(self):
        # Обратная сторона: козий сыр прямо разрешён оговоркой — запрещать его нельзя.
        r = self._run(["козий сыр"], [
            {"item": "козий сыр", "verdict": "ok", "reason": "разрешён оговоркой",
             "source": "restrictions"},
        ])
        self.assertEqual(r["violations"], [])
        self.assertEqual(r["unclear"], [])
        self.assertFalse(r["blocked"])

    def test_unclear_blocks_outgoing_but_not_incoming(self):
        results = [{"item": "плов", "verdict": "unclear", "reason": "состав неизвестен",
                    "source": "model"}]
        incoming = self._run(["плов"], results, direction="incoming")
        outgoing = self._run(["плов"], results, direction="outgoing")
        # Уже съеденное блокировать бессмысленно — только сигнал нутрициологу…
        self.assertFalse(incoming["blocked"])
        # …а предлагать при неясности нельзя (асимметрия, решение владельца).
        self.assertTrue(outgoing["blocked"])

    def test_missing_item_in_response_becomes_unclear(self):
        # Модель ответила не про все продукты — про пропущенный не додумываем «ok».
        r = self._run(["кешью", "рис"], [
            {"item": "кешью", "verdict": "violates", "reason": "орех", "source": "allergies"},
        ])
        unclear_items = [v["item"] for v in r["unclear"]]
        self.assertEqual(unclear_items, ["рис"])

    def test_unknown_verdict_value_becomes_unclear(self):
        r = self._run(["рис"], [{"item": "рис", "verdict": "наверное можно", "reason": ""}])
        self.assertEqual(len(r["unclear"]), 1)


class TestFailuresAreNotGreenLight(unittest.TestCase):
    """Сбой ≠ «продукт безопасен». Это ядро безопасности всей проверки."""

    def setUp(self):
        fc.reset_cache()

    def _run_with_llm(self, llm_kwargs):
        with patch("database.queries.get_client_profile",
                   return_value=_profile(allergies=["орехи"])), \
             patch("database.queries.get_active_nutrition_plan", return_value=_plan()), \
             patch("business_rules.food_check._knowledge_context", return_value=""), \
             patch("prompts.load_prompt", return_value="sys"), \
             patch("utils.llm.call_llm", **llm_kwargs):
            return fc.check_food("cid", ["кешью"], direction="outgoing")

    def test_llm_exception_gives_unclear(self):
        r = self._run_with_llm({"side_effect": RuntimeError("429")})
        self.assertEqual(len(r["unclear"]), 1)
        self.assertTrue(r["blocked"])

    def test_llm_garbage_gives_unclear(self):
        r = self._run_with_llm({"return_value": {"content": "я не понял вопрос"}})
        self.assertEqual(len(r["unclear"]), 1)
        self.assertTrue(r["blocked"])

    def test_db_failure_gives_unclear(self):
        with patch("database.queries.get_client_profile", side_effect=RuntimeError("db down")):
            r = fc.check_food("cid", ["кешью"], direction="outgoing")
        self.assertTrue(r["checked"])
        self.assertEqual(len(r["unclear"]), 1)
        self.assertTrue(r["blocked"])

    def test_knowledge_base_failure_does_not_break_check(self):
        # База знаний недоступна — проверка всё равно идёт, просто без её контекста.
        with patch("database.queries.get_client_profile",
                   return_value=_profile(allergies=["орехи"])), \
             patch("database.queries.get_active_nutrition_plan", return_value=_plan()), \
             patch("utils.knowledge.search_knowledge_base", side_effect=RuntimeError("down")), \
             patch("prompts.load_prompt", return_value="sys"), \
             patch("utils.llm.call_llm", return_value=_llm(
                 [{"item": "кешью", "verdict": "violates", "reason": "орех", "source": "allergies"}])):
            r = fc.check_food("cid", ["кешью"])
        self.assertEqual(len(r["violations"]), 1)


class TestCache(unittest.TestCase):
    def setUp(self):
        fc.reset_cache()

    def test_repeat_item_does_not_call_model_twice(self):
        with patch("database.queries.get_client_profile",
                   return_value=_profile(allergies=["орехи"])), \
             patch("database.queries.get_active_nutrition_plan", return_value=_plan()), \
             patch("business_rules.food_check._knowledge_context", return_value=""), \
             patch("prompts.load_prompt", return_value="sys"), \
             patch("utils.llm.call_llm", return_value=_llm(
                 [{"item": "рис", "verdict": "ok", "reason": "", "source": "restrictions"}])) as llm:
            fc.check_food("cid", ["рис"])
            fc.check_food("cid", ["рис"])
        self.assertEqual(llm.call_count, 1)

    def test_changed_constraints_invalidate_cache(self):
        # Нутрициолог поменял план — старый вердикт переиспользовать нельзя.
        with patch("business_rules.food_check._knowledge_context", return_value=""), \
             patch("prompts.load_prompt", return_value="sys"), \
             patch("utils.llm.call_llm", return_value=_llm(
                 [{"item": "рис", "verdict": "ok", "reason": "", "source": "restrictions"}])) as llm:
            with patch("database.queries.get_client_profile", return_value=_profile()), \
                 patch("database.queries.get_active_nutrition_plan", return_value=_plan(["рис"])):
                fc.check_food("cid", ["рис"])
            with patch("database.queries.get_client_profile", return_value=_profile()), \
                 patch("database.queries.get_active_nutrition_plan",
                       return_value=_plan(["рис", "гречка"])):
                fc.check_food("cid", ["рис"])
        self.assertEqual(llm.call_count, 2)


if __name__ == "__main__":
    unittest.main()
