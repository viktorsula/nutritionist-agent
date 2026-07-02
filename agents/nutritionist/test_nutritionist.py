"""
Тесты ветки нутрициолога (Этап 6 Часть B).

Проверяют без БД и реальных LLM (всё замокано):
1. Импорты + сборку графа
2. parse_request: классификацию intent + резолв клиента по имени
3. parse_request: детект подтверждения/отмены pending_action
4. management: разбор команды → pending_action (без записи)
5. management: confirm → исполнение действия (+ audit)
6. management: cancel → отмена
7. analytics: read-only анализ

Запуск:
    PYTHONPATH=/workspaces/nutritionist-agent python3 agents/nutritionist/test_nutritionist.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.nutritionist.orchestrator import (
    create_nutritionist_graph,
    parse_request_node,
    _route_by_intent,
)
from agents.nutritionist.management_agent import management_node
from agents.nutritionist.analytics_agent import analytics_node
from agents.nutritionist.state import create_initial_state


def _llm(content: str):
    """Мок ответа call_llm."""
    return {"content": content, "model": "mock-model", "usage": {}}


class TestGraphStructure(unittest.TestCase):
    def test_graph_builds(self):
        graph = create_nutritionist_graph()
        self.assertIsNotNone(graph)

    def test_route_by_intent(self):
        self.assertEqual(_route_by_intent({"intent": "analytics"}), "analytics")
        self.assertEqual(_route_by_intent({"intent": "management"}), "management")
        self.assertEqual(_route_by_intent({"intent": "confirm"}), "management")
        self.assertEqual(_route_by_intent({"intent": "cancel"}), "management")
        self.assertEqual(_route_by_intent({"intent": "help"}), "help")
        self.assertEqual(_route_by_intent({}), "help")


class TestParseRequest(unittest.TestCase):
    @patch("agents.nutritionist.orchestrator.queries.get_conversation_thread", return_value=[])
    @patch("agents.nutritionist.orchestrator.queries.get_all_clients")
    @patch("agents.nutritionist.orchestrator.call_llm")
    def test_classify_analytics_and_resolve_client(self, mock_llm, mock_clients, _thread):
        mock_llm.return_value = _llm(
            '{"intent": "analytics", "client_name": "Марина", "period_days": 14}'
        )
        mock_clients.return_value = [
            {"id": "c1", "name": "Марина Иванова"},
            {"id": "c2", "name": "Пётр Сидоров"},
        ]

        state = create_initial_state("nut-1", "сводка по Марине за 2 недели")
        parse_request_node(state)

        self.assertEqual(state["intent"], "analytics")
        self.assertEqual(state["target_client_id"], "c1")
        self.assertEqual(state["period_days"], 14)

    @patch("agents.nutritionist.orchestrator.queries.get_conversation_thread", return_value=[])
    @patch("agents.nutritionist.orchestrator.queries.get_all_clients")
    @patch("agents.nutritionist.orchestrator.call_llm")
    def test_ambiguous_client_becomes_candidates(self, mock_llm, mock_clients, _thread):
        mock_llm.return_value = _llm('{"intent": "analytics", "client_name": "Иван"}')
        mock_clients.return_value = [
            {"id": "c1", "name": "Иван Иванов"},
            {"id": "c2", "name": "Иван Петров"},
        ]

        state = create_initial_state("nut-1", "как дела у Ивана")
        parse_request_node(state)

        self.assertIsNone(state["target_client_id"])
        self.assertEqual(len(state["client_candidates"]), 2)

    @patch("agents.nutritionist.orchestrator.queries.get_conversation_thread")
    @patch("agents.nutritionist.orchestrator.call_llm")
    def test_confirm_detected_with_pending(self, mock_llm, mock_thread):
        pending = {"action_type": "create_task", "params": {"title": "t"}}
        mock_thread.return_value = [
            {"role": "agent", "metadata_json": {"pending_action": pending}},
        ]

        state = create_initial_state("nut-1", "да")
        parse_request_node(state)

        self.assertEqual(state["intent"], "confirm")
        self.assertEqual(state["pending_action"], pending)
        mock_llm.assert_not_called()  # подтверждение не зовёт классификатор

    @patch("agents.nutritionist.orchestrator.queries.get_conversation_thread")
    @patch("agents.nutritionist.orchestrator.call_llm")
    def test_cancel_detected_with_pending(self, mock_llm, mock_thread):
        pending = {"action_type": "create_task", "params": {"title": "t"}}
        mock_thread.return_value = [
            {"role": "agent", "metadata_json": {"pending_action": pending}},
        ]

        state = create_initial_state("nut-1", "нет, отмена")
        parse_request_node(state)

        self.assertEqual(state["intent"], "cancel")


class TestManagement(unittest.TestCase):
    @patch("agents.nutritionist.management_agent.call_llm")
    def test_command_creates_pending_action_no_write(self, mock_llm):
        mock_llm.return_value = _llm(
            '{"action_type": "create_task", '
            '"params": {"title": "взвеситься", "due_date": "2026-06-21"}, '
            '"human_summary": "Создать задачу взвеситься клиенту Марина на 2026-06-21"}'
        )

        state = create_initial_state("nut-1", "поставь Марине задачу взвеситься в пятницу")
        state["intent"] = "management"
        state["target_client_id"] = "c1"
        state["target_client_name"] = "Марина Иванова"

        management_node(state)

        self.assertIsNotNone(state["pending_action"])
        self.assertEqual(state["pending_action"]["action_type"], "create_task")
        # client_id подставлен в params
        self.assertEqual(state["pending_action"]["params"]["client_id"], "c1")
        self.assertIn("подтверждения", state["agent_response"])

    @patch("agents.nutritionist.management_agent.call_llm")
    def test_command_without_client_asks_to_specify(self, mock_llm):
        mock_llm.return_value = _llm(
            '{"action_type": "create_task", "params": {"title": "x"}, "human_summary": "..."}'
        )

        state = create_initial_state("nut-1", "поставь задачу")
        state["intent"] = "management"
        state["target_client_id"] = None
        state["client_candidates"] = []

        management_node(state)

        self.assertIsNone(state["pending_action"])
        self.assertIn("клиент", state["agent_response"].lower())

    @patch("agents.nutritionist.management_agent.queries.write_audit_log", return_value={})
    @patch("agents.nutritionist.management_agent.queries.create_task")
    def test_confirm_executes_create_task(self, mock_create, mock_audit):
        mock_create.return_value = {"id": "task-1"}

        state = create_initial_state("nut-1", "да")
        state["intent"] = "confirm"
        state["pending_action"] = {
            "action_type": "create_task",
            "params": {"client_id": "c1", "client_name": "Марина", "title": "взвеситься"},
        }

        management_node(state)

        mock_create.assert_called_once()
        self.assertEqual(mock_create.call_args.kwargs["created_by"], "nutritionist")
        mock_audit.assert_called_once()
        self.assertIsNone(state["pending_action"])
        self.assertIn("✅", state["agent_response"])

    def test_cancel_clears_pending(self):
        state = create_initial_state("nut-1", "нет")
        state["intent"] = "cancel"
        state["pending_action"] = {"action_type": "create_task", "params": {}}

        management_node(state)

        self.assertIsNone(state["pending_action"])
        self.assertIn("отмен", state["agent_response"].lower())

    def test_confirm_without_pending(self):
        state = create_initial_state("nut-1", "да")
        state["intent"] = "confirm"
        state["pending_action"] = None

        management_node(state)

        self.assertIn("нет действия", state["agent_response"].lower())


class TestAnalytics(unittest.TestCase):
    @patch("agents.nutritionist.analytics_agent.call_llm")
    @patch("agents.nutritionist.analytics_agent.queries.get_client_events", return_value=[])
    @patch("agents.nutritionist.analytics_agent.queries.get_client_summary")
    def test_client_analytics(self, mock_summary, _events, mock_llm):
        mock_summary.return_value = {
            "client": {"name": "Марина Иванова", "client_status": "active"},
            "message_count": 12,
            "total_events": 3,
            "critical_alerts": 0,
            "high_alerts": 1,
            "pending_tasks": 2,
            "completed_tasks": 5,
        }
        mock_llm.return_value = _llm("Анализ: динамика стабильна.")

        state = create_initial_state("nut-1", "сводка по Марине")
        state["intent"] = "analytics"
        state["target_client_id"] = "c1"
        state["period_days"] = 7

        analytics_node(state)

        # Сырой анализ LLM уходит в панель «Аналитика» (state["analysis"]);
        # agent_response — директива вида (агент наполняет центр, фича 22 июня).
        self.assertEqual(state["analysis"]["markdown"], "Анализ: динамика стабильна.")
        self.assertIn("Аналитика", state["agent_response"])
        self.assertEqual(state["agent_used"], "analytics_agent")
        mock_summary.assert_called_once()

    @patch("agents.nutritionist.analytics_agent.call_llm")
    @patch("agents.nutritionist.analytics_agent.queries.get_critical_alerts", return_value=[])
    @patch("agents.nutritionist.analytics_agent.queries.get_all_clients")
    def test_base_analytics(self, mock_clients, _alerts, mock_llm):
        mock_clients.return_value = [
            {"client_status": "active"},
            {"client_status": "active"},
            {"client_status": "paused"},
        ]
        mock_llm.return_value = _llm("По базе: 3 клиента.")

        state = create_initial_state("nut-1", "статистика по базе")
        state["intent"] = "analytics"
        state["target_client_id"] = None

        analytics_node(state)

        self.assertEqual(state["analysis"]["markdown"], "По базе: 3 клиента.")
        self.assertIn("Аналитика", state["agent_response"])
        mock_clients.assert_called_once()


def test_gather_client_data_includes_conversation_summary():
    """
    Нарративная память клиента (скользящая сводка) должна попадать в контекст аналитики —
    иначе нутрициолог не видит субъективных жалоб (напр. «вчера болела голова»), которые
    остались только в диалоге, а не в структурных событиях.
    """
    from agents.nutritionist.analytics_agent import _gather_client_data

    summary = {"client": {"name": "Екатерина", "client_status": "active",
                          "conversation_summary": "Вчера клиент жаловался на головную боль."}}
    with patch("agents.nutritionist.analytics_agent.queries.get_client_summary", return_value=summary), \
         patch("agents.nutritionist.analytics_agent.queries.get_client_profile", return_value={}), \
         patch("agents.nutritionist.analytics_agent.queries.get_client_events", return_value=[]), \
         patch("agents.nutritionist.analytics_agent.queries.get_recent_lab_results", return_value=[]), \
         patch("agents.nutritionist.analytics_agent.queries.get_active_nutrition_plan", return_value=None):
        ctx, _indicators = _gather_client_data("c1", 7)

    assert "головную боль" in ctx
    assert "Память диалога" in ctx


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tc in (TestGraphStructure, TestParseRequest, TestManagement, TestAnalytics):
        suite.addTests(loader.loadTestsFromTestCase(tc))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite).wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТЫ ВЕТКИ НУТРИЦИОЛОГА (Этап 6 Часть B)")
    print("=" * 60)
    success = run_tests()
    print("\n" + ("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if success else "❌ ЕСТЬ ПРОВАЛЫ"))
    sys.exit(0 if success else 1)
