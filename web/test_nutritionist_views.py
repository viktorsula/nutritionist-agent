"""
Тесты веб-представлений нутрициолога (Этап 8, Шаг 1) — без живой БД.

Проверяют:
1. Импорт модуля web.nutritionist и наличие render-функций
2. get_client_registry() формирует корректный запрос к view (мок supabase)
3. Вспомогательные функции форматирования (_registry_table, _join, _allergy_names)
4. _run_ai_analysis вызывает analytics_node с правильным state (мок агента)

Запуск:
    PYTHONPATH=/workspaces/nutritionist-agent python3 web/test_nutritionist_views.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestImports(unittest.TestCase):
    def test_module_and_functions(self):
        from web.nutritionist import (
            render_registry,
            render_analytics,
            _registry_table,
            _join,
            _allergy_names,
        )
        self.assertTrue(callable(render_registry))
        self.assertTrue(callable(render_analytics))


class TestRegistryQuery(unittest.TestCase):
    @patch("database.queries._service_client")
    def test_get_client_registry_uses_view(self, mock_client):
        from database import queries

        # Цепочка supabase.table(...).select(...).execute()
        fake = MagicMock()
        fake.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "c1", "name": "Марина", "client_status": "active"}
        ]
        mock_client.return_value = fake

        rows = queries.get_client_registry()

        fake.table.assert_called_with("client_registry_view")
        self.assertEqual(rows[0]["name"], "Марина")

    @patch("database.queries._service_client")
    def test_get_client_registry_filter(self, mock_client):
        from database import queries

        fake = MagicMock()
        chain = fake.table.return_value.select.return_value
        chain.eq.return_value.execute.return_value.data = []
        chain.execute.return_value.data = []
        mock_client.return_value = fake

        queries.get_client_registry(status="active")
        chain.eq.assert_called_with("client_status", "active")


class TestFormatters(unittest.TestCase):
    def test_registry_table_shape(self):
        from web.nutritionist import _registry_table

        rows = [{
            "name": "Марина", "client_status": "active", "payment_status": "active",
            "access_status": "active", "goals": "похудеть", "weight": 70,
            "plan_title": "Базовый", "last_contact": "2026-06-18", "open_tasks": 2,
        }]
        table = _registry_table(rows)
        self.assertEqual(table[0]["Имя"], "Марина")
        self.assertEqual(table[0]["Откр. задач"], 2)

    def test_join_and_allergies(self):
        from web.nutritionist import _join, _allergy_names

        self.assertEqual(_join(None), "—")
        self.assertEqual(_join(["a", "b"]), "a, b")
        self.assertEqual(_allergy_names([{"name": "орехи"}, "молоко"]), ["орехи", "молоко"])
        self.assertEqual(_allergy_names(None), [])


class TestAiAnalysis(unittest.TestCase):
    @patch("agents.nutritionist.analytics_agent.analytics_node")
    def test_run_ai_analysis_builds_state(self, mock_node):
        from web.nutritionist import _run_ai_analysis

        def fake_node(state):
            # Проверяем, что state собран правильно
            assert state["intent"] == "analytics"
            assert state["target_client_id"] == "c1"
            assert state["period_days"] == 30
            state["agent_response"] = "Анализ готов."
            return state

        mock_node.side_effect = fake_node

        text = _run_ai_analysis("c1", "Марина", 30)
        self.assertEqual(text, "Анализ готов.")
        mock_node.assert_called_once()


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tc in (TestImports, TestRegistryQuery, TestFormatters, TestAiAnalysis):
        suite.addTests(loader.loadTestsFromTestCase(tc))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТЫ ВЕБ-ПРЕДСТАВЛЕНИЙ НУТРИЦИОЛОГА (Этап 8)")
    print("=" * 60)
    success = run_tests()
    print("\n" + ("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if success else "❌ ЕСТЬ ПРОВАЛЫ"))
    sys.exit(0 if success else 1)
