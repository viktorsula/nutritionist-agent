"""
Часть B на общем ядре: NutritionistAdapter (LLM-оркестратор нутрициолога) за фиче-флагом.
Проверяем флаг, ДЕТЕРМИНИРОВАННОЕ подтверждение записи (Р1), staging write-инструментов,
аналитику-обёртку, get_client_data, view-директивы, сквозной process.
"""

import os
from unittest.mock import patch, MagicMock

from agents.nutritionist import agent_adapter as na
from agents.core.agent_engine import AgentResult


# ── Фиче-флаг ────────────────────────────────────────────────────────────────
def test_should_use_disabled_by_default():
    with patch.dict(os.environ, {"NUTRITIONIST_ORCHESTRATOR_ENABLED": ""}, clear=False):
        assert na.should_use("nid", "text") is False


def test_should_use_enabled_and_whitelist():
    with patch.dict(os.environ, {"NUTRITIONIST_ORCHESTRATOR_ENABLED": "on",
                                 "NUTRITIONIST_ORCHESTRATOR_IDS": "aaa,bbb"}, clear=False):
        assert na.should_use("bbb", "text") is True
        assert na.should_use("zzz", "text") is False
        assert na.should_use("bbb", "photo") is False  # у нутрициолога только текст/голос


# ── Р1: подтверждение записи детерминированное, вне модели ────────────────────
def test_confirmation_yes_executes_without_llm():
    state = {"nutritionist_id": "nid", "message": "да"}
    pending = {"action_type": "create_task",
               "params": {"client_id": "c1", "client_name": "Марина", "title": "Пить воду"}}
    with patch("agents.nutritionist.agent_adapter._load_pending_action", return_value=pending), \
         patch("agents.nutritionist.agent_adapter._execute_action",
               return_value="✅ Задача создана.") as ex:
        handled = na._handle_confirmation(state)
    assert handled is True
    ex.assert_called_once()
    assert state["intent"] == "confirm"
    assert state["agent_response"] == "✅ Задача создана."
    assert state["pending_action"] is None
    assert state["target_client_id"] == "c1"


def test_confirmation_no_cancels():
    state = {"nutritionist_id": "nid", "message": "нет"}
    with patch("agents.nutritionist.agent_adapter._load_pending_action",
               return_value={"action_type": "create_task", "params": {}}), \
         patch("agents.nutritionist.agent_adapter._execute_action") as ex:
        handled = na._handle_confirmation(state)
    assert handled is True
    ex.assert_not_called()
    assert state["intent"] == "cancel"
    assert state["pending_action"] is None


def test_confirmation_other_message_not_handled():
    state = {"nutritionist_id": "nid", "message": "поставь задачу Марине"}
    with patch("agents.nutritionist.agent_adapter._load_pending_action",
               return_value={"action_type": "create_task", "params": {}}):
        assert na._handle_confirmation(state) is False


def test_confirmation_no_pending_not_handled():
    with patch("agents.nutritionist.agent_adapter._load_pending_action", return_value=None):
        assert na._handle_confirmation({"nutritionist_id": "nid", "message": "да"}) is False


# ── write-инструменты ГОТОВЯТ pending_action, но НЕ пишут ─────────────────────
def test_create_task_stages_pending_no_write():
    state = {"nutritionist_id": "nid", "target_client_name": "Марина"}
    with patch("agents.nutritionist.agent_adapter.queries.create_task") as cw:
        out = na._build_handlers(state)["create_task"](
            {"client_id": "c1", "title": "Дневник питания"})
    cw.assert_not_called()
    assert state["pending_action"]["action_type"] == "create_task"
    assert state["pending_action"]["params"]["client_id"] == "c1"
    assert state["intent"] == "management"
    assert out.startswith("подготовлено")


def test_create_task_without_client_id_not_staged():
    state = {"nutritionist_id": "nid"}
    out = na._build_handlers(state)["create_task"]({"title": "X"})
    assert state.get("pending_action") is None
    assert out.startswith("не подготовлено")


def test_update_status_no_fields_not_staged():
    state = {"nutritionist_id": "nid"}
    out = na._build_handlers(state)["update_client_status"]({"client_id": "c1"})
    assert state.get("pending_action") is None
    assert "не подготовлено" in out


def test_add_trusted_source_stages():
    state = {"nutritionist_id": "nid"}
    out = na._build_handlers(state)["add_trusted_source"]({"url": "https://x", "name": "X"})
    assert state["pending_action"]["action_type"] == "add_trusted_source"
    assert out.startswith("подготовлено")


# ── аналитика-обёртка + get_client_data ──────────────────────────────────────
def test_run_analytics_wraps_pipeline_and_sets_analysis():
    state = {"nutritionist_id": "nid"}

    def fake_node(s):
        s["analysis"] = {"title": "Динамика веса", "markdown": "…", "charts": []}
        return s

    with patch("agents.nutritionist.agent_adapter.queries.get_client_by_id",
               return_value={"name": "Марина"}), \
         patch("agents.nutritionist.agent_adapter.analytics_agent.analytics_node",
               side_effect=fake_node):
        out = na._build_handlers(state)["run_analytics"]({"client_id": "c1", "period_days": 14})
    assert state["analysis"]["title"] == "Динамика веса"
    assert state["intent"] == "analytics"
    assert state["period_days"] == 14
    assert "панел" in out


def test_get_client_data_dispatches():
    state = {"nutritionist_id": "nid", "period_days": 30}
    handlers = na._build_handlers(state)
    with patch("agents.nutritionist.agent_adapter.queries.get_recent_lab_results",
               return_value=[{"indicator": "холестерин"}]) as q:
        res = handlers["get_client_data"]({"client_id": "c1", "scope": "labs"})
    q.assert_called_once()
    assert res == [{"indicator": "холестерин"}]
    assert state["target_client_id"] == "c1"


def test_find_client_single_match():
    state = {"nutritionist_id": "nid"}
    with patch("agents.nutritionist.agent_adapter._resolve_client", return_value=("c1", [])), \
         patch("agents.nutritionist.agent_adapter.queries.get_client_by_id",
               return_value={"name": "Марина"}):
        out = na._build_handlers(state)["find_client"]({"name": "марина"})
    assert "c1" in out
    assert state["target_client_id"] == "c1"


# ── view-директивы ───────────────────────────────────────────────────────────
def test_finalize_view_analytics():
    state = {"analysis": {"title": "t"}, "agent_response": "готово"}
    na._finalize(state)
    assert state["view"] == {"type": "analytics"}
    assert state["final_message"] == "готово"


def test_finalize_view_client_card():
    state = {"target_client_id": "c1", "target_client_name": "Марина", "agent_response": "ок"}
    na._finalize(state)
    assert state["view"]["type"] == "client_card"
    assert state["view"]["client_id"] == "c1"


def test_finalize_view_none():
    state = {"agent_response": "справка"}
    na._finalize(state)
    assert state["view"] is None


# ── сквозной process ─────────────────────────────────────────────────────────
def test_process_confirm_path_skips_llm():
    pending = {"action_type": "add_trusted_source", "params": {"url": "https://x"}}
    with patch("agents.nutritionist.agent_adapter._load_pending_action", return_value=pending), \
         patch("agents.nutritionist.agent_adapter._execute_action", return_value="✅ добавлено") as ex, \
         patch("agents.nutritionist.agent_adapter.save_to_db_node", side_effect=lambda s: s), \
         patch("agents.nutritionist.agent_adapter.run_agent") as ra:
        res = na.process("nid", "да", "web", "text", {})
    ex.assert_called_once()
    ra.assert_not_called()          # подтверждение НЕ идёт в модель
    assert res["message"] == "✅ добавлено"
    assert res["intent"] == "confirm"


def test_process_normal_path_runs_agent():
    with patch("agents.nutritionist.agent_adapter._load_pending_action", return_value=None), \
         patch("agents.nutritionist.agent_adapter._load_context", side_effect=lambda s: None), \
         patch("agents.nutritionist.agent_adapter.save_to_db_node", side_effect=lambda s: s), \
         patch("agents.nutritionist.agent_adapter.run_agent",
               return_value=AgentResult(content="Вот сводка.", model="claude-sonnet-4-6",
                                        usage={}, tool_calls=[{"name": "run_analytics"}])) as ra:
        res = na.process("nid", "сводка по базе", "web", "text", {})
    ra.assert_called_once()
    assert res["message"] == "Вот сводка."
    assert res["model"] == "claude-sonnet-4-6"
