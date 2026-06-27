"""
Тесты оркестратора клиента: определитель → dispatch по сегментам → склейка ответа.

Обработчики и LLM мокаются; БД не задействуется (тестируем чистую логику графа).
"""

import unittest
from unittest.mock import patch

from agents.client import orchestrator as orch
from agents.client.branches import ACK, ANSWER, CLARIFY, INTAKE, PROFILE, ADVICE


class TestBuildParts(unittest.TestCase):
    def test_text_part(self):
        part = orch._build_parts({"message_type": "text", "message": "привет"})[0]
        self.assertEqual(part["kind"], "text")
        self.assertEqual(part["text"], "привет")
        self.assertNotIn("image_kind", part)

    def test_photo_part_carries_image_kind(self):
        part = orch._build_parts(
            {"message_type": "photo", "message": "что приготовить?", "image_kind": "fridge"}
        )[0]
        self.assertEqual(part["kind"], "photo")
        self.assertEqual(part["image_kind"], "fridge")


class TestDetermineNode(unittest.TestCase):
    def test_sets_segments_and_metadata(self):
        fake = {"segments": [{"branch": PROFILE, "parts": [0], "needs_answer": ANSWER}],
                "needs_answer": ANSWER}
        with patch.object(orch.intake, "determine_turn", lambda parts: fake):
            out = orch.determine_node(
                {"client_id": "c", "message_type": "text", "message": "привет", "metadata": {}}
            )
        self.assertEqual(out["segments"][0]["branch"], PROFILE)
        self.assertEqual(out["needs_answer"], ANSWER)
        self.assertEqual(out["metadata"]["intake"]["needs_answer"], ANSWER)


class TestDedup(unittest.TestCase):
    def test_merge_same_branch_answer_wins(self):
        segs = [
            {"branch": INTAKE, "parts": [0], "needs_answer": ACK},
            {"branch": INTAKE, "parts": [1], "needs_answer": ANSWER},
        ]
        out = orch._dedup_segments(segs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["needs_answer"], ANSWER)
        self.assertEqual(out[0]["parts"], [0, 1])

    def test_order_preserved_by_first_appearance(self):
        segs = [
            {"branch": PROFILE, "parts": [0], "needs_answer": ANSWER},
            {"branch": INTAKE, "parts": [0], "needs_answer": ACK},
        ]
        out = orch._dedup_segments(segs)
        self.assertEqual([s["branch"] for s in out], [PROFILE, INTAKE])


class TestResolveHandler(unittest.TestCase):
    def test_advice_to_nutrition(self):
        self.assertIs(orch._resolve_handler({"message_type": "text"}, ADVICE), orch.nutrition_node)

    def test_profile_to_dialog(self):
        self.assertIs(orch._resolve_handler({"message_type": "text"}, PROFILE), orch.dialog_node)

    def test_intake_photo_to_vision(self):
        self.assertIs(orch._resolve_handler({"message_type": "photo"}, INTAKE), orch.vision_node)

    def test_intake_text_to_diary(self):
        self.assertIs(orch._resolve_handler({"message_type": "text"}, INTAKE), orch.diary_node)

    def test_intake_document_to_document(self):
        self.assertIs(orch._resolve_handler({"message_type": "document"}, INTAKE), orch.document_node)


class TestDispatch(unittest.TestCase):
    def test_intake_captured_is_ack_with_subtype_label(self):
        state = {
            "message_type": "text",
            "segments": [
                {"branch": INTAKE, "parts": [0], "needs_answer": ACK},
                {"branch": PROFILE, "parts": [0], "needs_answer": ANSWER},
            ],
        }

        def fake_diary(s):
            s["intake_subtype"] = "meal"   # успешный захват
            s["agent_used"] = "diary_agent"
            return s

        def fake_dialog(s):
            s["agent_response"] = "ваш вес 80 кг"
            s["agent_used"] = "dialog_agent"
            return s

        with patch.object(orch, "diary_node", fake_diary), \
             patch.object(orch, "dialog_node", fake_dialog):
            out = orch.dispatch_node(state)

        results = out["segment_results"]
        self.assertEqual(results[0]["branch"], INTAKE)
        self.assertEqual(results[0]["needs_answer"], ACK)
        self.assertEqual(results[0]["label"], "Приём пищи")   # из INTAKE_SUBTYPES
        self.assertEqual(results[1]["needs_answer"], ANSWER)
        self.assertEqual(results[1]["text"], "ваш вес 80 кг")

    def test_intake_capture_fail_becomes_clarify(self):
        state = {"message_type": "text",
                 "segments": [{"branch": INTAKE, "parts": [0], "needs_answer": ACK}]}

        def fake_diary_fail(s):
            # под-тип не выставлен → захват не удался; отдаём поясняющий текст
            s["agent_response"] = "Это про вес, еду или анализы? Уточни, пожалуйста."
            s["agent_used"] = "diary_agent"
            return s

        with patch.object(orch, "diary_node", fake_diary_fail):
            out = orch.dispatch_node(state)

        r = out["segment_results"][0]
        self.assertEqual(r["needs_answer"], CLARIFY)
        self.assertIn("Уточни", r["text"])

    def test_topic_clarify_segment_uses_render(self):
        state = {"message_type": "text",
                 "segments": [{"branch": PROFILE, "parts": [0], "needs_answer": CLARIFY}]}
        with patch.object(orch, "_render_clarify", lambda s: "Уточни, чего ты хочешь?"):
            out = orch.dispatch_node(state)
        r = out["segment_results"][0]
        self.assertEqual(r["needs_answer"], CLARIFY)
        self.assertEqual(r["text"], "Уточни, чего ты хочешь?")

    def test_empty_segments_fallback_clarify(self):
        with patch.object(orch, "_render_clarify", lambda s: "Уточни?"):
            out = orch.dispatch_node({"message_type": "text", "segments": []})
        self.assertEqual(len(out["segment_results"]), 1)
        self.assertEqual(out["segment_results"][0]["needs_answer"], CLARIFY)


class TestFormatResponse(unittest.TestCase):
    def _state(self, results, alerts=None, routing=None):
        return {
            "segment_results": results,
            "alerts": alerts or [],
            "routing": routing or {},
            "client_id": "c",
            "client_profile": {"name": "Аня"},
        }

    def test_answer_plus_ack_shows_receipt_not_warm_ack(self):
        state = self._state([
            {"branch": INTAKE, "needs_answer": ACK, "text": "", "label": "Приём пищи"},
            {"branch": PROFILE, "needs_answer": ANSWER, "text": "ваш вес 80 кг", "label": "Запрос по профилю"},
        ])
        out = orch.format_response_node(state)
        msg = out["final_message"]
        self.assertIn("ваш вес 80 кг", msg)        # ответ
        self.assertIn("✓ Записал: Приём пищи", msg)  # квитанция по под-типу

    def test_pure_ack_warm_plus_receipt(self):
        state = self._state([
            {"branch": INTAKE, "needs_answer": ACK, "text": "", "label": "Вода"},
        ])
        with patch.object(orch, "_render_ack", lambda s: "Спасибо, Аня! Принято ✅"):
            out = orch.format_response_node(state)
        msg = out["final_message"]
        self.assertIn("Принято", msg)
        self.assertIn("✓ Записал: Вода", msg)

    def test_clarify_shown_first(self):
        state = self._state([
            {"branch": INTAKE, "needs_answer": ACK, "text": "", "label": "Вес/замеры"},
            {"branch": INTAKE, "needs_answer": CLARIFY, "text": "А это что — еда или анализы?", "label": ""},
        ])
        out = orch.format_response_node(state)
        msg = out["final_message"]
        self.assertIn("А это что", msg)             # уточнение показано
        self.assertIn("✓ Записал: Вес/замеры", msg)  # и квитанция по захваченному

    def test_two_answers_get_headers(self):
        state = self._state([
            {"branch": ADVICE, "needs_answer": ANSWER, "text": "вариант ужина", "label": "Совет по питанию"},
            {"branch": PROFILE, "needs_answer": ANSWER, "text": "ваш прогресс", "label": "Запрос по профилю"},
        ])
        out = orch.format_response_node(state)
        msg = out["final_message"]
        self.assertIn("Совет по питанию", msg)
        self.assertIn("Запрос по профилю", msg)

    def test_safety_alert_prepended_even_on_ack(self):
        state = self._state(
            [{"branch": INTAKE, "needs_answer": ACK, "text": "", "label": "Приём пищи"}],
            alerts=[{"type": "food_forbidden", "severity": "high", "message": "Свинина в плане запрещена"}],
            routing={"notify_nutritionist": True},
        )
        with patch.object(orch, "_render_ack", lambda s: "Принято ✅"):
            out = orch.format_response_node(state)
        msg = out["final_message"]
        self.assertIn("Нутрициолог", msg)              # уведомление сверху
        self.assertIn("Свинина в плане запрещена", msg)  # предупреждение
        self.assertIn("✓ Записал: Приём пищи", msg)


if __name__ == "__main__":
    unittest.main()
