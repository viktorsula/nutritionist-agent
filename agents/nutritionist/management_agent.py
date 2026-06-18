"""
Management Agent (Нутрициолог) — управление по команде врача.

Запись в БД — ТОЛЬКО через подтверждение (two-step):
1. intent='management' → разобрать команду в структурированное действие (Claude,
   management_system.md), вернуть резюме на подтверждение, сохранить pending_action.
2. intent='confirm'    → исполнить pending_action (поднятый parse_request из истории).
3. intent='cancel'     → отменить pending_action.

Все write-операции выполняются с created_by='nutritionist'/actor_type='nutritionist'
и пишут запись в audit_logs. Агент не назначает ничего по своей инициативе.

Промпт: prompts/nutritionist/management_system.md
LLM: Claude (task_type='analysis').
"""

import json
import logging
from datetime import date
from typing import Any, Dict, Optional

from utils.llm import call_llm
from prompts import load_prompt
from database import queries
from .state import NutritionistState

logger = logging.getLogger(__name__)

CONFIRM_HINT = '\n\nОтветьте «да» для подтверждения или «нет» для отмены.'

# Действия, которым требуется привязка к клиенту
CLIENT_SCOPED = {"create_task", "create_nutrition_plan", "update_client_status"}


def management_node(state: NutritionistState) -> NutritionistState:
    """Узел управления. Ветвится по intent: management | confirm | cancel."""
    state["agent_used"] = "management_agent"
    intent = state.get("intent")

    try:
        if intent == "confirm":
            return _handle_confirm(state)
        if intent == "cancel":
            return _handle_cancel(state)
        return _handle_command(state)

    except Exception as e:
        logger.error(f"Management agent error: {e}", exc_info=True)
        state["agent_response"] = (
            "Не удалось обработать команду управления. Попробуйте переформулировать."
        )
        state["agent_used"] = "management_agent_error"
        state["error"] = str(e)
        return state


# ==========================================
# ШАГ 1: РАЗБОР КОМАНДЫ → pending_action
# ==========================================

def _handle_command(state: NutritionistState) -> NutritionistState:
    """Разбирает команду в действие и просит подтверждения (без записи)."""
    action = _parse_action(state.get("message", ""))

    if not action or action.get("action_type") in (None, "unknown"):
        summary = (action or {}).get("human_summary") if action else None
        state["agent_response"] = (
            summary
            or "Не понял команду. Уточните: что создать/изменить и для какого клиента."
        )
        state["pending_action"] = None
        return state

    action_type = action["action_type"]
    params = action.get("params") or {}

    # Действия, требующие клиента, — нужен разрешённый target_client_id
    if action_type in CLIENT_SCOPED:
        client_id = state.get("target_client_id")
        if not client_id:
            candidates = state.get("client_candidates") or []
            if candidates:
                names = ", ".join(c.get("name", "?") for c in candidates[:5])
                state["agent_response"] = (
                    f"Уточните клиента — под запрос подходят: {names}."
                )
            else:
                state["agent_response"] = (
                    "Не удалось определить клиента. Укажите имя клиента в команде."
                )
            state["pending_action"] = None
            return state
        params["client_id"] = client_id
        params["client_name"] = state.get("target_client_name")
        action["params"] = params

    # Сохраняем разобранное действие для подтверждения на следующем сообщении
    state["pending_action"] = action
    state["agent_response"] = action.get("human_summary", "Действие подготовлено.") + CONFIRM_HINT
    return state


def _parse_action(message: str) -> Optional[Dict[str, Any]]:
    """Разбирает команду нутрициолога в структурированное действие (Claude → JSON)."""
    message = (message or "").strip()
    if not message:
        return None

    system_prompt = _load_management_prompt()
    user_prompt = (
        f"Текущая дата: {date.today().isoformat()}.\n"
        f"Команда нутрициолога: {message}"
    )
    response = call_llm(
        task_type="analysis",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _safe_parse_json(response.get("content", ""))


def _load_management_prompt() -> str:
    try:
        return load_prompt("nutritionist/management_system")
    except Exception as e:
        logger.error(f"Error loading management prompt: {e}")
        return (
            "Разбери команду нутрициолога в строгий JSON "
            '{"action_type","params","human_summary"}. Только JSON.'
        )


# ==========================================
# ШАГ 2: ПОДТВЕРЖДЕНИЕ → ИСПОЛНЕНИЕ
# ==========================================

def _handle_confirm(state: NutritionistState) -> NutritionistState:
    """Исполняет pending_action (поднятый parse_request из истории)."""
    action = state.get("pending_action")
    if not action:
        state["agent_response"] = "Нет действия для подтверждения. Сформулируйте команду заново."
        return state

    result_msg = _execute_action(action, state.get("nutritionist_id"))
    state["agent_response"] = result_msg
    state["pending_action"] = None  # действие исполнено — снимаем
    return state


def _handle_cancel(state: NutritionistState) -> NutritionistState:
    state["agent_response"] = "Действие отменено."
    state["pending_action"] = None
    return state


def _execute_action(action: Dict[str, Any], nutritionist_id: Optional[str]) -> str:
    """Исполняет разобранное действие через queries.* + пишет audit_log."""
    action_type = action.get("action_type")
    params = action.get("params") or {}

    if action_type == "create_task":
        return _do_create_task(params, nutritionist_id)
    if action_type == "create_nutrition_plan":
        return _do_create_plan(params, nutritionist_id)
    if action_type == "update_client_status":
        return _do_update_status(params, nutritionist_id)
    if action_type == "add_trusted_source":
        return _do_add_trusted_source(params, nutritionist_id)

    return f"Неизвестный тип действия: {action_type}. Ничего не записано."


def _do_create_task(params: Dict[str, Any], nutritionist_id: Optional[str]) -> str:
    task = queries.create_task(
        client_id=params["client_id"],
        title=params["title"],
        created_by="nutritionist",
        description=params.get("description"),
        due_date=params.get("due_date"),
    )
    task_id = (task or {}).get("id")
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=nutritionist_id,
        action="assign_task",
        entity_type="task",
        entity_id=task_id,
        new_value=params,
    )
    who = params.get("client_name") or params["client_id"]
    return f"✅ Задача «{params['title']}» создана для клиента {who}."


def _do_create_plan(params: Dict[str, Any], nutritionist_id: Optional[str]) -> str:
    plan_json = {
        k: params[k] for k in ("target_calories", "restrictions") if params.get(k) is not None
    }
    plan = queries.create_nutrition_plan(
        client_id=params["client_id"],
        title=params["title"],
        created_by="nutritionist",
        effective_from=params.get("effective_from") or date.today().isoformat(),
        plan_json=plan_json,
    )
    plan_id = (plan or {}).get("id")
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=nutritionist_id,
        action="change_plan",
        entity_type="plan",
        entity_id=plan_id,
        new_value=params,
    )
    who = params.get("client_name") or params["client_id"]
    return f"✅ План питания «{params['title']}» создан для клиента {who} (старый деактивирован)."


def _do_update_status(params: Dict[str, Any], nutritionist_id: Optional[str]) -> str:
    status_fields = {
        k: params[k]
        for k in ("client_status", "payment_status", "access_status")
        if params.get(k) is not None
    }
    if not status_fields:
        return "Не указан ни один статус для изменения. Ничего не записано."

    old = queries.get_client_by_id(params["client_id"]) or {}
    queries.update_client_status(client_id=params["client_id"], **status_fields)
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=nutritionist_id,
        action="change_status",
        entity_type="client",
        entity_id=params["client_id"],
        old_value={k: old.get(k) for k in status_fields},
        new_value=status_fields,
    )
    who = params.get("client_name") or params["client_id"]
    changes = ", ".join(f"{k}={v}" for k, v in status_fields.items())
    return f"✅ Статусы клиента {who} обновлены: {changes}."


def _do_add_trusted_source(params: Dict[str, Any], nutritionist_id: Optional[str]) -> str:
    sources = queries.get_setting("trusted_sources")
    if not isinstance(sources, list):
        sources = []
    new_source = {"name": params.get("name"), "url": params["url"]}
    sources.append(new_source)

    queries.update_system_setting("trusted_sources", sources, updated_by=nutritionist_id)
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=nutritionist_id,
        action="update_threshold",
        entity_type="settings",
        entity_id="trusted_sources",
        new_value=new_source,
    )
    return f"✅ Доверенный источник добавлен: {new_source.get('name') or new_source['url']}."


# ==========================================
# УТИЛИТЫ
# ==========================================

def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Извлекает JSON из ответа модели (со снятием markdown-обёртки)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None
