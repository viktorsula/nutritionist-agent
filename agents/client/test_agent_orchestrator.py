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


def test_should_use_photo_handled_by_orchestrator():
    # Ф1.5: фото обрабатывается оркестратором (мультимодальность), не уходит на граф.
    with patch.dict(os.environ, {"CLIENT_ORCHESTRATOR_ENABLED": "on",
                                 "CLIENT_ORCHESTRATOR_CLIENT_IDS": ""}, clear=False):
        assert ao.should_use("cid", "photo") is True
        assert ao.should_use("cid", "voice") is True
        # неподдерживаемый тип (документ) — на граф
        assert ao.should_use("cid", "document") is False


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


def test_log_meal_warns_model_on_serious_alert():
    # P0-3: обнаруженное нарушение плана (high/critical) должно вернуться модели,
    # чтобы она предупредила клиента прямо в ответе, а не молчала («Записал ✅»).
    state = {"client_id": "cid"}

    def fake_persist(state_arg, record):
        state_arg["alerts"] = (state_arg.get("alerts") or []) + [
            {"type": "food_forbidden", "severity": "high",
             "message": "Козий сыр — молочный продукт, в ограничениях"},
        ]
        return "meal"

    with patch("agents.client.agent_orchestrator.intake_store.persist_record",
               side_effect=fake_persist):
        out = ao._build_handlers(state)["log_meal"]({"items": [{"name": "козий сыр"}]})
    assert out.startswith("записано: meal")
    assert "Козий сыр" in out
    assert "предупреди" in out.lower()


def test_log_meal_no_warning_when_no_serious_alert():
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record",
               return_value="meal"):
        out = ao._build_handlers(state)["log_meal"]({"items": [{"name": "яблоко"}]})
    assert out == "записано: meal"


def test_log_meal_ignores_alerts_accumulated_before_this_call():
    # Алерты, накопленные РАНЕЕ в этом же ходе (другим тулом), не должны триггерить
    # повторное предупреждение при следующем log_meal без своих алертов.
    state = {"client_id": "cid",
             "alerts": [{"type": "old", "severity": "high", "message": "старый алерт"}]}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record",
               return_value="meal"):
        out = ao._build_handlers(state)["log_meal"]({"items": [{"name": "яблоко"}]})
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


def test_log_measurement_and_sleep_records():
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record") as pr:
        handlers = ao._build_handlers(state)
        pr.return_value = "measurement"
        handlers["log_measurement"]({"metric_key": "waist", "value": 80, "unit": "см"})
        assert pr.call_args.args[1]["measurement"] == {"metric_key": "waist", "value": 80, "unit": "см"}

        pr.return_value = "sleep"
        handlers["log_sleep"]({"bedtime": "23:30", "wake": "07:00"})
        assert pr.call_args.args[1]["sleep"] == {"bedtime": "23:30", "wake": "07:00"}


def test_measurement_sleep_tools_registered():
    names = {t["name"] for t in ao._tool_schemas()}
    assert {"log_measurement", "log_sleep"} <= names
    handlers = ao._build_handlers({"client_id": "cid"})
    assert "log_measurement" in handlers and "log_sleep" in handlers


def test_log_meal_empty_items_blocked_by_validate():
    # Пустой приём пищи не доходит до persist: validate-гейт → просим уточнить.
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record") as pr:
        out = ao._build_handlers(state)["log_meal"]({"items": []})
    pr.assert_not_called()
    assert out.startswith("не записал")


# ── Ф1.5: мультимодальность (расшифровка фото, шов A/B) ──────────────────────
def test_log_meal_source_photo_when_photo_turn():
    # На фото-ходе записанный приём помечается source='photo'.
    state = {"client_id": "cid", "message_type": "photo"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record",
               return_value="meal") as pr:
        ao._build_handlers(state)["log_meal"]({"items": [{"name": "салат"}]})
    assert pr.call_args.args[1]["source"] == "photo"


def test_prepare_vision_direct_returns_image_block():
    state = {"client_id": "cid", "message_type": "photo", "image_kind": "food",
             "metadata": {"image_bytes": b"\x00\x01\x02", "mime_type": "image/png"}}
    with patch("utils.vision.resolve_vision_strategy", return_value="direct"):
        blocks = ao._prepare_vision(state)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[0]["source"]["type"] == "base64"


def test_prepare_vision_gemini_tool_injects_note_and_no_images():
    state = {"client_id": "cid", "message_type": "photo", "image_kind": "food",
             "message": "посмотри обед",
             "metadata": {"image_bytes": b"\x00", "mime_type": "image/jpeg"}}
    with patch("utils.vision.resolve_vision_strategy", return_value="gemini_tool"), \
         patch("utils.vision.analyze_food_plate",
               return_value={"items": [{"name": "курица"}, {"name": "рис"}]}):
        blocks = ao._prepare_vision(state)
    assert blocks == []                          # image-блоков нет (B)
    assert "курица" in state["message"]          # распознанное подмешано в контекст хода
    assert "посмотри обед" in state["message"]   # исходная подпись сохранена


def test_prepare_vision_non_photo_returns_empty():
    assert ao._prepare_vision({"client_id": "c", "message_type": "text"}) == []


def test_get_client_data_dispatches_scopes():
    state = {"client_id": "cid", "active_plan": {"target_calories": 1800}}
    handlers = ao._build_handlers(state)
    with patch("database.queries.get_latest_measurement", return_value={"weight": 70}) as m:
        assert handlers["get_client_data"]({"scope": "measurements"}) == {"weight": 70}
        m.assert_called_once_with("cid")
    # plan берётся из уже загруженного state (нормализованный вид), без обращения в БД
    assert handlers["get_client_data"]({"scope": "plan"})["target_calories"] == 1800
    assert "неизвестный scope" in handlers["get_client_data"]({"scope": "wat"})


def test_get_client_data_diary_reads_events():
    # scope='diary' отдаёт недавние записи дневника (еда/вода/вес/самочувствие),
    # чтобы клиент мог спросить «что я вчера ел / сколько воды выпил».
    state = {"client_id": "cid"}
    handlers = ao._build_handlers(state)
    events = [{"event_type": "calories_logged"}, {"event_type": "water_logged"}]
    with patch("database.queries.get_client_events", return_value=events) as e:
        assert handlers["get_client_data"]({"scope": "diary"}) == events
        e.assert_called_once()


# ── Fix B: уведомление нутрициолога + чистый ответ (E2E-дебаг) ────────────────
def test_log_wellbeing_bad_tells_model_nutritionist_notified():
    # При плохом самочувствии обработчик сообщает модели, что нутрициолог УЖЕ уведомлён,
    # чтобы она сказала «я уже сообщил(а)», а не «будет в курсе».
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record", return_value="wellbeing"):
        out = ao._build_handlers(state)["log_wellbeing"]({"status": "bad", "reason": "болит печень"})
    assert "уже уведомлён" in out
    assert "Telegram" in out


def test_log_wellbeing_good_has_no_notification_note():
    state = {"client_id": "cid"}
    with patch("agents.client.agent_orchestrator.intake_store.persist_record", return_value="wellbeing"):
        out = ao._build_handlers(state)["log_wellbeing"]({"status": "good"})
    assert "уведомлён" not in out


def test_finalize_uses_model_reply_verbatim():
    # _finalize не дописывает сырой текст алертов — ответ модели идёт как есть
    # (модель сама вплетает предупреждения; безопасность — в persist/routing/scheduler).
    state = {"alerts": [{"type": "bad_wellbeing", "severity": "medium",
                         "message": "Клиент сообщает о плохом самочувствии: Болит печень"}],
             "routing": {"notify_nutritionist": False}}
    ao._finalize(state, "Записала обед и самочувствие. Уже сообщила нутрициологу.")
    assert state["final_message"] == "Записала обед и самочувствие. Уже сообщила нутрициологу."
    assert "Обратите внимание" not in state["final_message"]
    assert "Клиент сообщает" not in state["final_message"]


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


# ── Профиль клиента (P0-5/P1-2) ───────────────────────────────────────────────
def test_client_profile_block_included_in_system_prompt():
    state = {
        "client_profile": {
            "name": "Катя", "birth_date": "1990-01-01", "gender": "female",
            "goals": "снижение веса", "weight": 70, "target_weight": 60,
            "chronic_conditions": ["гипотиреоз"],
        },
        "active_plan": None,
        "latest_measurement": None,
        "wellness_plan": {"sleep_target": "22-8", "stress_management": "медитации"},
    }
    system = ao._system_prompt(state)
    assert "Профиль клиента" in system
    assert "снижение веса" in system
    assert "70 кг → цель 60 кг" in system
    assert "гипотиреоз" in system
    assert "медитации" in system


def test_client_profile_block_absent_when_no_data():
    system = ao._system_prompt({"client_profile": {"name": "Катя"}, "active_plan": None})
    assert "Профиль клиента" not in system


def test_client_profile_prefers_latest_measurement_over_questionnaire_weight():
    state = {
        "client_profile": {"name": "Катя", "weight": 70, "target_weight": 60},
        "active_plan": None,
        "latest_measurement": {"weight": 65},
    }
    system = ao._system_prompt(state)
    assert "65 кг → цель 60 кг" in system
    assert "70 кг" not in system


def test_client_profile_includes_questionnaire_extra():
    state = {
        "client_profile": {
            "name": "Катя",
            "questionnaire_json": {"medications": "витамин D", "stress": "высокий перед сном"},
        },
        "active_plan": None,
    }
    system = ao._system_prompt(state)
    assert "Принимаемые препараты: витамин D" in system
    assert "Стресс/настроение: высокий перед сном" in system


def test_client_profile_prefers_summary_over_raw_questionnaire():
    # Миграция 017: если questionnaire_summary есть — используем его, построчный
    # формат questionnaire_json в промпт не идёт (экономия контекста на каждый ход).
    state = {
        "client_profile": {
            "name": "Катя",
            "questionnaire_summary": "Катя, 34 года, ведёт активный образ жизни.",
            "questionnaire_json": {"medications": "витамин D"},
        },
        "active_plan": None,
    }
    system = ao._system_prompt(state)
    assert "Катя, 34 года, ведёт активный образ жизни." in system
    assert "Принимаемые препараты" not in system


def test_client_profile_falls_back_to_raw_when_no_summary():
    # Старый клиент до миграции 017 (или разовый сбой генерации) — построчный откат.
    state = {
        "client_profile": {
            "name": "Катя",
            "questionnaire_summary": None,
            "questionnaire_json": {"medications": "витамин D"},
        },
        "active_plan": None,
    }
    system = ao._system_prompt(state)
    assert "Принимаемые препараты: витамин D" in system


def test_load_base_context_loads_wellness_plan():
    with patch("database.queries.get_client_by_id", return_value={"name": "Катя"}), \
         patch("database.queries.get_client_profile", return_value={}), \
         patch("database.queries.get_active_nutrition_plan", return_value=None), \
         patch("database.queries.get_conversations", return_value=[]), \
         patch("database.queries.get_latest_measurement", return_value=None), \
         patch("database.queries.get_controlled_metrics", return_value=[]), \
         patch("database.queries.get_wellness_plan",
               return_value={"sleep_target": "22-8"}) as wp:
        state = {"client_id": "cid"}
        ao._load_base_context(state)
    wp.assert_called_once_with("cid")
    assert state["wellness_plan"] == {"sleep_target": "22-8"}


def test_load_base_context_wellness_plan_failure_is_best_effort():
    # Сбой загрузки ЗОЖ не должен ронять весь базовый контекст (best-effort, как measurement).
    with patch("database.queries.get_client_by_id", return_value={"name": "Катя"}), \
         patch("database.queries.get_client_profile", return_value={}), \
         patch("database.queries.get_active_nutrition_plan", return_value=None), \
         patch("database.queries.get_conversations", return_value=[]), \
         patch("database.queries.get_latest_measurement", return_value=None), \
         patch("database.queries.get_controlled_metrics", return_value=[]), \
         patch("database.queries.get_wellness_plan", side_effect=RuntimeError("db down")):
        state = {"client_id": "cid"}
        ao._load_base_context(state)
    assert state["wellness_plan"] is None
    assert state["client"] == {"name": "Катя"}  # остальной контекст загрузился


def test_controlled_metrics_block_gives_exact_keys():
    state = {
        "client_profile": {"name": "Катя"}, "active_plan": None,
        "controlled_metrics": [
            {"key": "waist", "label_ru": "Талия", "unit": "см"},
            {"key": "пульс", "label_ru": "Пульс", "unit": "уд/мин"},
            {"key": "sleep", "label_ru": "Сон"},
        ],
    }
    system = ao._system_prompt(state)
    assert "Контролируемые показатели клиента" in system
    assert 'log_measurement(metric_key="пульс"' in system  # точный ключ для custom
    assert "log_sleep" in system


def test_controlled_metrics_block_absent_when_empty():
    system = ao._system_prompt({"client_profile": {"name": "Катя"}, "active_plan": None})
    assert "Контролируемые показатели клиента" not in system


# ── Цикл агента ──────────────────────────────────────────────────────────────
def test_run_agent_loop_sets_state_and_returns_text():
    state = {"client_id": "cid", "client_profile": {"name": "Катя"}, "conversation_history": []}

    def fake_call(**kw):
        assert kw["task_type"] == "orchestrator"
        assert "tools" in kw and "tool_handlers" in kw
        return {"content": "Привет, Катя!", "model": "claude-sonnet-4-6",
                "usage": {"total_tokens": 10},
                "tool_calls": [{"name": "log_water", "input": {}, "is_error": False}]}

    with patch("agents.core.agent_engine.call_llm", side_effect=fake_call):
        text = ao._run_agent_loop(state)

    assert text == "Привет, Катя!"
    assert state["agent_used"] == "orchestrator"
    assert state["llm_model"] == "claude-sonnet-4-6"
    assert state["metadata"]["tool_calls"] == ["log_water"]


def test_run_agent_loop_empty_content_has_fallback():
    state = {"client_id": "cid", "client_profile": {}, "conversation_history": []}
    with patch("agents.core.agent_engine.call_llm",
               return_value={"content": "", "model": "m", "usage": {}}):
        text = ao._run_agent_loop(state)
    assert text  # не пусто — есть фолбэк-приглашение


# ── Полный проход + откат на граф ────────────────────────────────────────────
def test_process_runs_loop_persists_and_finalizes():
    def fake_call(**kw):
        kw["tool_handlers"]["log_weight"]({"weight_kg": 70})
        return {"content": "Записал вес 70 кг ✅", "model": "claude-sonnet-4-6", "usage": {}}

    with patch("agents.core.agent_engine.call_llm", side_effect=fake_call), \
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
