"""
LLM-оркестратор ветки НУТРИЦИОЛОГА на общем ядре run_agent (за фиче-флагом).

«Один движок, две роли»: тот же `agents/core/agent_engine.py::run_agent`, что и у клиента,
но с ролевыми промптом/инструментами/обработчиками нутрициолога (аналитик/контролёр/репортёр).
Граф Части B остаётся fallback: при LLMUnavailableError/ошибке вызывающий (router) откатывается
на `process_nutritionist_message`.

БЕЗОПАСНОСТЬ ЗАПИСИ ОСТАЁТСЯ ДЕТЕРМИНИРОВАННОЙ (решение Р1):
- write-инструменты НЕ пишут в БД — они ГОТОВЯТ `pending_action` (→ conversations.metadata_json);
- детект «да»/«нет» и ИСПОЛНЕНИЕ идут ВНЕ модели (регулярки + `_execute_action` из графа + audit),
  ровно как в текущем two-step. Модель не может записать в карту сама.

Централизация: модель — только через `task_type='nutritionist_orchestrator'` → llm_config
(кабинет); промпт — `load_prompt('nutritionist/orchestrator_system')` (БД-приоритет → файл).
"""

import os
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from prompts import load_prompt
from agents.core.agent_engine import run_agent
from database import queries
from .state import create_initial_state, extract_response, nutritionist_thread_id
from . import analytics_agent
from .orchestrator import _load_pending_action, _resolve_client, _AFFIRM, _NEGATE, save_to_db_node
from .management_agent import _execute_action, CLIENT_SCOPED

logger = logging.getLogger(__name__)

_SUPPORTED_TYPES = ("text", "voice")


# ==========================================
# ФИЧЕ-ФЛАГ
# ==========================================

def should_use(nutritionist_id: str, message_type: str = "text") -> bool:
    """
    Включён ли LLM-оркестратор нутрициолога.

    ENV:
    - NUTRITIONIST_ORCHESTRATOR_ENABLED — глобальный тумблер (1/true/yes/on);
    - NUTRITIONIST_ORCHESTRATOR_IDS — белый список nutritionist_id через запятую (пусто = все).
    """
    if os.environ.get("NUTRITIONIST_ORCHESTRATOR_ENABLED", "").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    if message_type not in _SUPPORTED_TYPES:
        return False
    allow = os.environ.get("NUTRITIONIST_ORCHESTRATOR_IDS", "").strip()
    if allow:
        allowed = {x.strip() for x in allow.split(",") if x.strip()}
        return nutritionist_id in allowed
    return True


# ==========================================
# ПЕР-НУТРИЦИОЛОГ БЛОКИРОВКА
# ==========================================

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(nutritionist_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(nutritionist_id)
        if lock is None:
            lock = threading.Lock()
            _locks[nutritionist_id] = lock
        return lock


# ==========================================
# ГЛАВНЫЙ ВХОД
# ==========================================

def process(
    nutritionist_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Полный проход оркестратора нутрициолога. Возвращает тот же контракт, что и граф
    (extract_response). Может бросить LLMUnavailableError/др. — ловит вызывающий → граф.
    """
    start = datetime.now()
    with _lock_for(nutritionist_id):
        state = create_initial_state(
            nutritionist_id=nutritionist_id,
            message=message,
            channel=channel,
            message_type=message_type,
            metadata=metadata,
        )

        # ── ДЕТЕРМИНИРОВАННЫЙ ШАГ ПОДТВЕРЖДЕНИЯ (safety, до любого LLM) ──────────
        if _handle_confirmation(state):
            _finalize(state)
            save_to_db_node(state)
            state["processing_time_ms"] = int((datetime.now() - start).total_seconds() * 1000)
            return extract_response(state)

        # ── LLM-оркестратор ────────────────────────────────────────────────────
        _load_context(state)
        reply = _run_agent_loop(state)
        state["agent_response"] = reply
        _finalize(state)
        save_to_db_node(state)

        state["processing_time_ms"] = int((datetime.now() - start).total_seconds() * 1000)
        logger.info(
            f"Nutritionist orchestrator handled {nutritionist_id}: "
            f"tools={(state.get('metadata') or {}).get('tool_calls')}, intent={state.get('intent')}"
        )
        return extract_response(state)


# ==========================================
# ПОДТВЕРЖДЕНИЕ ЗАПИСИ (детерминированное, вне модели — Р1)
# ==========================================

def _handle_confirmation(state: Dict[str, Any]) -> bool:
    """
    Если в треде есть ожидающее pending_action и сообщение — «да»/«нет», обрабатываем
    детерминированно (исполнение через _execute_action + audit / отмена), БЕЗ вызова модели.
    Возвращает True, если ход обработан здесь.
    """
    nid = state.get("nutritionist_id")
    message = (state.get("message") or "").strip()
    pending = _load_pending_action(nid)
    if not pending:
        return False

    if _AFFIRM.match(message):
        params = pending.get("params") or {}
        state["target_client_id"] = params.get("client_id")
        state["target_client_name"] = params.get("client_name")
        state["intent"] = "confirm"
        state["agent_used"] = "management_execute"
        state["agent_response"] = _execute_action(pending, nid)
        state["pending_action"] = None
        return True

    if _NEGATE.match(message):
        state["intent"] = "cancel"
        state["agent_used"] = "management_cancel"
        state["agent_response"] = "Действие отменено."
        state["pending_action"] = None
        return True

    return False  # новая команда — pending будет перезаписан обычным ходом


# ==========================================
# КОНТЕКСТ
# ==========================================

def _load_context(state: Dict[str, Any]) -> None:
    """История треда нутрициолога → conversation_history для движка."""
    nid = state.get("nutritionist_id")
    history: List[Dict[str, str]] = []
    try:
        thread = queries.get_conversation_thread(nutritionist_thread_id(nid)) if nid else []
        for msg in (thread or [])[-10:]:
            text = (msg.get("message_text") or "").strip()
            if not text:
                continue
            role = "assistant" if msg.get("role") == "agent" else "user"
            history.append({"role": role, "content": text})
    except Exception as e:
        logger.warning(f"nutritionist orchestrator: history load failed: {e}")
    state["conversation_history"] = history


# ==========================================
# ЦИКЛ АГЕНТА
# ==========================================

def _run_agent_loop(state: Dict[str, Any]) -> str:
    result = run_agent(
        system_prompt=_system_prompt(),
        history=state.get("conversation_history"),
        user_message=state.get("message"),
        tools=_tool_schemas(),
        tool_handlers=_build_handlers(state),
        task_type="nutritionist_orchestrator",
    )
    state["llm_model"] = state.get("llm_model") or result.model  # analytics-инструмент мог задать
    state["llm_usage"] = result.usage
    state["agent_used"] = state.get("agent_used") or "nutritionist_orchestrator"
    if result.tool_calls:
        md = state.get("metadata") or {}
        md["tool_calls"] = [t.get("name") for t in result.tool_calls]
        state["metadata"] = md
    return result.content or "Готово."


def _system_prompt() -> str:
    try:
        return load_prompt("nutritionist/orchestrator_system")
    except Exception as e:
        logger.error(f"nutritionist orchestrator prompt error: {e}")
        return (
            "Ты — ИИ-ассистент нутрициолога (аналитик/контролёр/репортёр). Используй инструменты "
            "для аналитики и чтения; запись в карту — только через подтверждение. Не выдумывай факты."
        )


# ==========================================
# ИНСТРУМЕНТЫ: схемы
# ==========================================

def _tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "name": "find_client",
            "description": "Найти клиента по имени (подстрока). Верни client_id или список совпадений.",
            "input_schema": {"type": "object", "properties": {"name": {"type": "string"}},
                             "required": ["name"]},
        },
        {
            "name": "run_analytics",
            "description": "Подготовить аналитику (открывается в панели «Аналитика»): по клиенту "
                           "(если задан client_id — RAG-конвейер + графики) или по всей базе (без client_id).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "period_days": {"type": "integer"},
                },
            },
        },
        {
            "name": "get_client_data",
            "description": "Точечные данные клиента для короткого фактического ответа.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "scope": {"type": "string",
                              "enum": ["measurements", "labs", "plan", "wellness", "tasks", "events", "summary"]},
                },
                "required": ["client_id", "scope"],
            },
        },
        {
            "name": "search_knowledge",
            "description": "Поиск по базе знаний нутрициолога и документам клиента (pgvector).",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "client_id": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "create_task",
            "description": "ПОДГОТОВИТЬ создание задачи клиенту (запись — после подтверждения нутрициолога).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"}, "title": {"type": "string"},
                    "description": {"type": "string"}, "due_date": {"type": "string"},
                },
                "required": ["client_id", "title"],
            },
        },
        {
            "name": "create_nutrition_plan",
            "description": "ПОДГОТОВИТЬ создание плана питания (запись — после подтверждения).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"}, "title": {"type": "string"},
                    "target_calories": {"type": "number"},
                    "restrictions": {"type": "array", "items": {"type": "string"}},
                    "effective_from": {"type": "string"},
                },
                "required": ["client_id", "title"],
            },
        },
        {
            "name": "update_client_status",
            "description": "ПОДГОТОВИТЬ смену статусов клиента (запись — после подтверждения).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "client_status": {"type": "string"},
                    "payment_status": {"type": "string"},
                    "access_status": {"type": "string"},
                },
                "required": ["client_id"],
            },
        },
        {
            "name": "add_trusted_source",
            "description": "ПОДГОТОВИТЬ добавление доверенного источника (запись — после подтверждения).",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string"}, "name": {"type": "string"}},
                "required": ["url"],
            },
        },
    ]


# ==========================================
# ИНСТРУМЕНТЫ: обработчики
# ==========================================

def _build_handlers(state: Dict[str, Any]) -> Dict[str, Any]:
    nid = state.get("nutritionist_id")

    def find_client(inp: Dict[str, Any]) -> str:
        name = inp.get("name") or ""
        client_id, candidates = _resolve_client(name)
        if client_id:
            client = queries.get_client_by_id(client_id) or {}
            state["target_client_id"] = client_id
            state["target_client_name"] = client.get("name") or name
            return f"client_id={client_id}, имя={client.get('name') or name}"
        if candidates:
            names = "; ".join(f"{c.get('name')} (id={c.get('id')})" for c in candidates[:5])
            return f"несколько совпадений, уточни: {names}"
        return f"клиент по имени «{name}» не найден"

    def run_analytics(inp: Dict[str, Any]) -> str:
        client_id = inp.get("client_id")
        state["target_client_id"] = client_id
        if client_id and not state.get("target_client_name"):
            state["target_client_name"] = (queries.get_client_by_id(client_id) or {}).get("name")
        if inp.get("period_days"):
            state["period_days"] = int(inp["period_days"])
        analytics_agent.analytics_node(state)  # заполняет state["analysis"] + agent_response
        analysis = state.get("analysis") or {}
        state["intent"] = "analytics"
        return f"аналитика подготовлена и открыта в панели: {analysis.get('title', 'обзор')}"

    def get_client_data(inp: Dict[str, Any]) -> Any:
        cid, scope = inp.get("client_id"), inp.get("scope")
        state["target_client_id"] = cid
        if scope == "measurements":
            return queries.get_latest_measurement(cid)
        if scope == "labs":
            return queries.get_recent_lab_results(cid, limit=20)
        if scope == "plan":
            return queries.get_active_nutrition_plan(cid)
        if scope == "wellness":
            return queries.get_wellness_plan(cid)
        if scope == "tasks":
            return queries.get_pending_tasks(cid)
        if scope == "events":
            return queries.get_client_events(cid, limit=20)
        if scope == "summary":
            return queries.get_client_summary(cid, days=state.get("period_days") or 30)
        return f"неизвестный scope: {scope}"

    def search_knowledge(inp: Dict[str, Any]) -> str:
        from utils.knowledge import (
            search_knowledge_base, search_client_documents, build_context_from_chunks,
        )
        query = inp.get("query") or ""
        chunks = list(search_knowledge_base(query, match_count=4))
        cid = inp.get("client_id")
        if cid:
            chunks += search_client_documents(query, cid, match_count=4)
        return build_context_from_chunks(chunks) or "по базе знаний ничего релевантного не найдено"

    # ── write-инструменты: ГОТОВЯТ pending_action (не пишут) ──────────────────
    def _stage(action_type: str, params: Dict[str, Any], summary: str) -> str:
        if action_type in CLIENT_SCOPED:
            cid = params.get("client_id")
            if not cid:
                return "не подготовлено: не указан client_id (сначала найди клиента через find_client)"
            params.setdefault("client_name",
                               state.get("target_client_name")
                               or (queries.get_client_by_id(cid) or {}).get("name"))
            state["target_client_id"] = cid
            state["target_client_name"] = params.get("client_name")
        state["pending_action"] = {"action_type": action_type, "params": params, "human_summary": summary}
        state["intent"] = "management"
        return f"подготовлено (нужно подтверждение нутрициолога): {summary}"

    def create_task(inp: Dict[str, Any]) -> str:
        params = {"client_id": inp.get("client_id"), "title": inp.get("title"),
                  "description": inp.get("description"), "due_date": inp.get("due_date")}
        return _stage("create_task", params, f"Создать задачу «{inp.get('title')}» клиенту")

    def create_nutrition_plan(inp: Dict[str, Any]) -> str:
        params = {"client_id": inp.get("client_id"), "title": inp.get("title"),
                  "target_calories": inp.get("target_calories"),
                  "restrictions": inp.get("restrictions"),
                  "effective_from": inp.get("effective_from")}
        return _stage("create_nutrition_plan", params, f"Создать план питания «{inp.get('title')}» клиенту")

    def update_client_status(inp: Dict[str, Any]) -> str:
        fields = {k: inp.get(k) for k in ("client_status", "payment_status", "access_status")
                  if inp.get(k) is not None}
        if not fields:
            return "не подготовлено: не указан ни один статус"
        params = {"client_id": inp.get("client_id"), **fields}
        changes = ", ".join(f"{k}={v}" for k, v in fields.items())
        return _stage("update_client_status", params, f"Изменить статусы клиента: {changes}")

    def add_trusted_source(inp: Dict[str, Any]) -> str:
        params = {"url": inp.get("url"), "name": inp.get("name")}
        return _stage("add_trusted_source", params,
                      f"Добавить доверенный источник: {inp.get('name') or inp.get('url')}")

    return {
        "find_client": find_client,
        "run_analytics": run_analytics,
        "get_client_data": get_client_data,
        "search_knowledge": search_knowledge,
        "create_task": create_task,
        "create_nutrition_plan": create_nutrition_plan,
        "update_client_status": update_client_status,
        "add_trusted_source": add_trusted_source,
    }


# ==========================================
# ФИНАЛИЗАЦИЯ (view + final_message)
# ==========================================

def _finalize(state: Dict[str, Any]) -> None:
    """Директива вида для веб-центра + финальный текст (зеркало format_response графа)."""
    state["final_message"] = state.get("agent_response") or "Готово."
    if state.get("analysis"):
        state["view"] = {"type": "analytics"}
    elif state.get("target_client_id"):
        state["view"] = {
            "type": "client_card",
            "client_id": state.get("target_client_id"),
            "client_name": state.get("target_client_name"),
            "period_days": state.get("period_days", 7),
        }
    else:
        state["view"] = None
