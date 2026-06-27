"""
Интеграционные тесты полного графа клиента (end-to-end на моках).

Прогоняем create_client_graph().invoke() целиком: ingest → determine → load_context →
dispatch → format_response → save_to_db. Внешние зависимости (БД, LLM, обработчики) мокаются;
проверяем, что узлы корректно соединены и склейка ответа работает.
"""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from agents.client import orchestrator as orch
from agents.client.orchestrator import create_client_graph
from agents.client.state import create_initial_state
from agents.client.branches import INTAKE, PROFILE, ACK, ANSWER, CLARIFY


def _patch_db(stack: ExitStack) -> None:
    import database.queries as q
    import agents.client.summary as summary

    stack.enter_context(patch.object(q, 'get_client_by_id',
        lambda cid: {"name": "Аня", "nutritionist_notes": None, "conversation_summary": ""}))
    stack.enter_context(patch.object(q, 'get_client_profile', lambda cid: {"allergies": []}))
    stack.enter_context(patch.object(q, 'get_active_nutrition_plan', lambda cid: {}))
    stack.enter_context(patch.object(q, 'get_latest_measurement', lambda cid: None))
    stack.enter_context(patch.object(q, 'get_recent_lab_results', lambda cid, limit=20: []))
    stack.enter_context(patch.object(q, 'get_wellness_plan', lambda cid: None))
    stack.enter_context(patch.object(q, 'get_pending_tasks', lambda cid: []))
    stack.enter_context(patch.object(q, 'get_conversations', lambda client_id=None, limit=10: []))
    stack.enter_context(patch.object(q, 'save_conversation', lambda **k: None))
    stack.enter_context(patch.object(summary, 'update_rolling_summary', lambda s: None))


def _fake_diary_capture(state):
    state['intake_subtype'] = 'meal'   # успешный захват приёма пищи
    state['agent_used'] = 'diary_agent'
    return state


def _fake_dialog(state):
    state['agent_response'] = 'Ваш вес сейчас 80 кг.'
    state['agent_used'] = 'dialog_agent'
    return state


class TestGraphEndToEnd(unittest.TestCase):
    def _run(self, segments, handlers=None, message_type='text', message='привет'):
        graph = create_client_graph()
        with ExitStack() as stack:
            _patch_db(stack)
            stack.enter_context(patch.object(orch.intake, 'determine_turn',
                lambda parts: {"segments": segments, "needs_answer": "answer"}))
            stack.enter_context(patch.object(orch, '_render_ack', lambda s: "Спасибо, Аня! Принято ✅"))
            stack.enter_context(patch.object(orch, '_render_clarify', lambda s: "Уточни, пожалуйста, чего ты хочешь?"))
            for name, fn in (handlers or {}).items():
                stack.enter_context(patch.object(orch, name, fn))
            state = create_initial_state(
                client_id="c", message=message, channel="web", message_type=message_type,
            )
            return graph.invoke(state)

    def test_pure_intake_ack_produces_receipt(self):
        final = self._run(
            [{"branch": INTAKE, "parts": [0], "needs_answer": ACK}],
            handlers={'diary_node': _fake_diary_capture},
            message="на ужин курица с рисом",
        )
        msg = final['final_message']
        self.assertIn("Принято", msg)
        self.assertIn("✓ Записал: Приём пищи", msg)

    def test_profile_answer(self):
        final = self._run(
            [{"branch": PROFILE, "parts": [0], "needs_answer": ANSWER}],
            handlers={'dialog_node': _fake_dialog},
            message="какой у меня вес?",
        )
        self.assertIn("Ваш вес сейчас 80 кг.", final['final_message'])

    def test_clarify_flow(self):
        final = self._run(
            [{"branch": PROFILE, "parts": [0], "needs_answer": CLARIFY}],
            message="асдфг 3#",
        )
        self.assertIn("Уточни", final['final_message'])

    def test_mixed_intake_and_profile(self):
        final = self._run(
            [
                {"branch": INTAKE, "parts": [0], "needs_answer": ACK},
                {"branch": PROFILE, "parts": [0], "needs_answer": ANSWER},
            ],
            handlers={'diary_node': _fake_diary_capture, 'dialog_node': _fake_dialog},
            message="холестерин 5.2, это нормально?",
        )
        msg = final['final_message']
        self.assertIn("Ваш вес сейчас 80 кг.", msg)       # ответ
        self.assertIn("✓ Записал: Приём пищи", msg)         # квитанция

    def test_intake_capture_fail_becomes_clarify(self):
        def fail_diary(state):
            state['agent_response'] = "Это про вес, еду или анализы? Уточни, пожалуйста."
            state['agent_used'] = 'diary_agent'
            return state  # intake_subtype не выставлен → захват не удался

        final = self._run(
            [{"branch": INTAKE, "parts": [0], "needs_answer": ACK}],
            handlers={'diary_node': fail_diary},
            message="ну это самое",
        )
        self.assertIn("Уточни", final['final_message'])


if __name__ == "__main__":
    unittest.main()
