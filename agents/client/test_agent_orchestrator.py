"""
Фаза 1 — LLM-оркестратор ветки клиента: фиче-флаг, инструменты (обёртки над
persist_record / чтением данных), цикл агента и откат на граф.
"""

import os
from unittest.mock import patch, MagicMock

from agents.client import agent_orchestrator as ao


# ── Фиче-флаг ────────────────────────────────────────────────────────────────
def test_should_use_disabled_by_default():
    with patch.dict(os.environ, {"CLIENT_ORCHESTRATOR_ENABLED": ""}, clear=False):
        assert ao.should_use("cid", "text") is False


def test_should_use_enabled_for_all_when_no_allowlist():
    with patch.dict(os.environ, {"CLIENT_ORCHESTRATOR_ENABLED": "true",
                                 "CLIENT_ORCHESTRATOR_CLIENT_IDS": ""}, clear=False):
        assert ao.should_use("cid", "text") is True
        assert ao.should_use("cid", "voice") is True


def test_should_use_respects_allowlist():
    with patch.dict(os.environ, {"CLIENT_ORCHESTRATOR_ENABLED": "1",
                                 "CLIENT_ORCHESTRATOR_CLIENT_IDS": "aaa, bbb"}, clear=False):
        assert ao.should_use("bbb", "text") is True
        assert ao.should_use("zzz", "text") is False


def test_should_use_photo_goes_to_graph():
    with patch.dict(os.environ, {"CLIENT_ORCHESTRATOR_ENABLED": "on",
                                 "CLIENT_ORCHESTRATOR_CLIENT_IDS": ""}, clear=False):
        assert ao.should_use("cid", "photo") is False


# ── Инструменты: обёртки над persist_record ──────────────────────────────────
def test_log_meal_builds_meal_record():
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record",
               return_value="meal") as pr:
        out = ao._build_handlers(state)["log_meal"]({
            "items": [{"name": "овсянка", "amount": "200 г"}, {"name": ""}],
            "dish_name": "завтрак", "meal_type": "breakfast",
            "total": {"kcal": 350},
        })
    rec = pr.call_args.args[1]
    assert rec["kind"] == "meal"
    assert rec["meal"]["items"] == [{"name": "овсянка", "amount": "200 г"}]  # пустое имя отброшено
    assert rec["meal"]["meal_type"] == "breakfast"
    assert rec["meal"]["total"] == {"kcal": 350}
    assert out == "записано: meal"


def test_log_water_weight_wellbeing_labs_records():
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record") as pr:
        handlers = ao._build_handlers(state)
        pr.return_value = "water"
        handlers["log_water"]({"water_ml": 250})
        assert pr.call_args.args[1] == {"kind": "water", "source": "text", "water_ml": 250}

        pr.return_value = "weight"
        handlers["log_weight"]({"weight_kg": 70.5})
        assert pr.call_args.args[1]["weight_kg"] == 70.5

        pr.return_value = "wellbeing"
        handlers["log_wellbeing"]({"status": "bad", "reason": "болит голова"})
        assert pr.call_args.args[1]["wellbeing"] == {"status": "bad", "reason": "болит голова"}

        pr.return_value = "labs"
        handlers["log_labs"]({"labs": [{"indicator": "холестерин", "value": 5.2, "unit": "ммоль/л"}]})
        assert pr.call_args.args[1]["labs"][0]["indicator"] == "холестерин"


def test_log_meal_reports_not_captured():
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record", return_value=None):
        out = ao._build_handlers(state)["log_meal"]({"items": []})
    assert out.startswith("не записано")


def test_get_client_data_dispatches_scopes():
    state = {"client_id": "cid", "active_plan": {"target_calories": 1800}}
    handlers = ao._build_handlers(state)
    with patch("database.queries.get_latest_measurement", return_value={"weight": 70}) as m:
        assert handlers["get_client_data"]({"scope": "measurements"}) == {"weight": 70}
        m.assert_called_once_with("cid")
    # plan берётся из уже загруженного state (нормализованный вид), без обращения в БД
    assert handlers["get_client_data"]({"scope": "plan"})["target_calories"] == 1800
    assert "неизвестный scope" in handlers["get_client_data"]({"scope": "wat"})


# ── Заземление на назначения нутрициолога (plan_json) ────────────────────────
def test_plan_view_reads_from_plan_json():
    plan = {
        "title": "Снижение веса",
        "plan_json": {"description": "Пить 2000 мл воды в день", "target_calories": 1600,
                      "restrictions": ["сахар", "жареное"]},
        "supplements_json": {"items": ["омега-3"]},
    }
    view = ao._plan_view(plan)
    assert view["title"] == "Снижение веса"
    assert view["target_calories"] == 1600
    assert view["restrictions"] == ["сахар", "жареное"]
    assert view["description"] == "Пить 2000 мл воды в день"
    assert view["supplements"] == ["омега-3"]


def test_plan_view_fallback_to_top_level():
    # старые записи/тесты с плоскими полями по-прежнему читаются
    view = ao._plan_view({"target_calories": 1800, "restrictions": ["алкоголь"]})
    assert view["target_calories"] == 1800
    assert view["restrictions"] == ["алкоголь"]


def test_prescriptions_block_included_in_system_prompt():
    state = {
        "client_profile": {"name": "Катя"},
        "active_plan": {"title": "План", "plan_json": {
            "description": "Норма воды 2 л/день", "target_calories": 1600, "restrictions": ["сахар"]}},
        "client": {"nutritionist_notes": "следить за железом"},
    }
    system = ao._system_prompt(state)
    assert "Назначения нутрициолога" in system
    assert "Норма воды 2 л/день" in system
    assert "1600 ккал" in system
    assert "следить за железом" in system


def test_prescriptions_block_honest_when_plan_empty():
    system = ao._system_prompt({"client_profile": {"name": "Катя"}, "active_plan": None})
    assert "ещё не заполнен" in system or "не назначил" in system


# ── Цикл агента ──────────────────────────────────────────────────────────────
def test_run_agent_loop_sets_state_and_returns_text():
    state = {"client_id": "cid", "client_profile": {"name": "Катя"}, "conversation_history": []}

    def fake_call(**kw):
        assert kw["task_type"] == "orchestrator"
        assert "tools" in kw and "tool_handlers" in kw
        return {"content": "Привет, Катя!", "model": "claude-sonnet-4-6",
                "usage": {"total_tokens": 10},
                "tool_calls": [{"name": "log_water", "input": {}, "is_error": False}]}

    with patch("agents.client.agent_orchestrator.call_llm", side_effect=fake_call):
        text = ao._run_agent_loop(state)

    assert text == "Привет, Катя!"
    assert state["agent_used"] == "orchestrator"
    assert state["llm_model"] == "claude-sonnet-4-6"
    assert state["metadata"]["tool_calls"] == ["log_water"]


def test_run_agent_loop_empty_content_has_fallback():
    state = {"client_id": "cid", "client_profile": {}, "conversation_history": []}
    with patch("agents.client.agent_orchestrator.call_llm",
               return_value={"content": "", "model": "m", "usage": {}}):
        text = ao._run_agent_loop(state)
    assert text  # не пусто — есть фолбэк-приглашение


# ── Полный проход + откат на граф ────────────────────────────────────────────
def test_process_runs_loop_persists_and_finalizes():
    def fake_call(**kw):
        kw["tool_handlers"]["log_weight"]({"weight_kg": 70})
        return {"content": "Записал вес 70 кг ✅", "model": "claude-sonnet-4-6", "usage": {}}

    with patch("agents.client.agent_orchestrator.call_llm", side_effect=fake_call), \
         patch("agents.client.agent_orchestrator._load_base_context"), \
         patch("agents.client.agent_orchestrator.intake_store.persist_record", return_value="weight") as pr, \
         patch("agents.client.orchestrator.ingest_node", side_effect=lambda s: s), \
         patch("agents.client.orchestrator.save_to_db_node", side_effect=lambda s: s):
        out = ao.process("cid", "мой вес 70", "telegram", "text", {}, {"mode": "full_program"})

    assert pr.call_args.args[1]["kind"] == "weight"
    assert "Записал" in out["message"]
    assert out["agent_used"] == "orchestrator"


def test_process_client_message_uses_orchestrator_when_enabled():
    from agents.client import orchestrator as orch
    sentinel = {"message": "ok", "agent_used": "orchestrator"}
    with patch("agents.client.agent_orchestrator.should_use", return_value=True), \
         patch("agents.client.agent_orchestrator.process", return_value=sentinel) as proc:
        out = orch.process_client_message("cid", "hi", "telegram", "text", {}, {"mode": "x"})
    proc.assert_called_once()
    assert out["message"] == "ok"


def test_process_client_message_falls_back_to_graph_on_unavailable():
    from agents.client import orchestrator as orch
    from utils.llm import LLMUnavailableError

    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {"final_message": "из графа", "agent_used": "diary"}
    with patch("agents.client.agent_orchestrator.should_use", return_value=True), \
         patch("agents.client.agent_orchestrator.process", side_effect=LLMUnavailableError("down")), \
         patch("agents.client.orchestrator.create_client_graph", return_value=fake_graph):
        out = orch.process_client_message("cid", "hi", "telegram", "text", {}, {"mode": "x"})

    assert out["message"] == "из графа"
    fake_graph.invoke.assert_called_once()
