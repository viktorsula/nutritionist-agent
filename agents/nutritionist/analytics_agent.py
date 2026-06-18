"""
Analytics Agent (Нутрициолог) — аналитик/контролёр/репортёр.

Read-only: собирает данные из БД и формирует профессиональный анализ через Claude.
Ничего не записывает. Финальное решение всегда за нутрициологом.

Два режима:
- по клиенту (target_client_id задан): сводка + события за период → анализ;
- по всей базе (клиент не определён): воронка по статусам + критичные алерты.

Промпт: prompts/nutritionist/analytics_system.md
LLM: Claude (task_type='analysis').
"""

import logging
from typing import Any, Dict, List

from utils.llm import call_llm
from prompts import load_prompt
from database import queries
from .state import NutritionistState

logger = logging.getLogger(__name__)


def analytics_node(state: NutritionistState) -> NutritionistState:
    """Узел аналитики. Устанавливает agent_response, agent_used, llm_model."""
    state["agent_used"] = "analytics_agent"

    try:
        data_context = _gather_data(state)
        system_prompt = _build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_prompt(state, data_context)},
        ]

        response = call_llm(task_type="analysis", messages=messages)

        state["agent_response"] = response["content"]
        state["llm_model"] = response.get("model")
        state["llm_usage"] = response.get("usage", {})
        return state

    except Exception as e:
        logger.error(f"Analytics agent error: {e}", exc_info=True)
        state["agent_response"] = (
            "Не удалось подготовить аналитику. Попробуйте уточнить запрос "
            "(имя клиента и период) или повторите позже."
        )
        state["agent_used"] = "analytics_agent_error"
        state["error"] = str(e)
        return state


# ==========================================
# СБОР ДАННЫХ ИЗ БД (read-only)
# ==========================================

def _gather_data(state: NutritionistState) -> str:
    """Собирает данные из БД в текстовый контекст для модели."""
    client_id = state.get("target_client_id")
    period_days = state.get("period_days") or 7

    if client_id:
        return _gather_client_data(client_id, period_days)
    return _gather_base_data()


def _gather_client_data(client_id: str, period_days: int) -> str:
    """Данные по конкретному клиенту: сводка + последние события."""
    summary = queries.get_client_summary(client_id, days=period_days)
    if not summary:
        return "Клиент не найден или данных нет."

    client = summary.get("client", {})
    events = queries.get_client_events(client_id, limit=20)

    lines = [
        f"Клиент: {client.get('name', 'без имени')} "
        f"(статус: {client.get('client_status', '—')})",
        f"Период анализа: {period_days} дн.",
        f"Сообщений за период: {summary.get('message_count', 0)}",
        f"Событий всего: {summary.get('total_events', 0)} "
        f"(critical: {summary.get('critical_alerts', 0)}, high: {summary.get('high_alerts', 0)})",
        f"Задачи: выполнено {summary.get('completed_tasks', 0)}, "
        f"в работе {summary.get('pending_tasks', 0)}",
    ]

    if events:
        lines.append("\nПоследние события:")
        for e in events[:15]:
            lines.append(
                f"- {e.get('event_date', '')}: {e.get('event_type', '')} "
                f"[{e.get('severity') or 'n/a'}] {_short(e.get('payload_json'))}"
            )

    return "\n".join(lines)


def _gather_base_data() -> str:
    """Данные по всей базе: воронка по статусам + критичные алерты за 24 часа."""
    clients = queries.get_all_clients()
    funnel: Dict[str, int] = {}
    for c in clients:
        status = c.get("client_status", "unknown")
        funnel[status] = funnel.get(status, 0) + 1

    lines = [
        f"Всего клиентов: {len(clients)}",
        "Воронка по статусам: "
        + ", ".join(f"{k}: {v}" for k, v in sorted(funnel.items())),
    ]

    alerts = queries.get_critical_alerts(hours=24)
    if alerts:
        lines.append(f"\nКритичные алерты за 24ч ({len(alerts)}):")
        for a in alerts[:15]:
            client = a.get("clients") or {}
            name = client.get("name", a.get("client_id", "?"))
            lines.append(f"- {name}: {a.get('event_type', '')} {_short(a.get('payload_json'))}")
    else:
        lines.append("\nКритичных алертов за 24ч нет.")

    return "\n".join(lines)


def _short(value: Any, limit: int = 120) -> str:
    """Короткое строковое представление payload для контекста."""
    if not value:
        return ""
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


# ==========================================
# ПОСТРОЕНИЕ ПРОМПТА
# ==========================================

def _build_system_prompt() -> str:
    try:
        return load_prompt("nutritionist/analytics_system")
    except Exception as e:
        logger.error(f"Error loading analytics prompt: {e}")
        return (
            "Ты эксперт-аналитик нутрициолога. Анализируй данные клиентов "
            "структурированно, с цифрами и конкретными рекомендациями. "
            "Финальное решение за нутрициологом. Отвечай на русском."
        )


def _build_user_prompt(state: NutritionistState, data_context: str) -> str:
    request = (state.get("message") or "").strip()
    return (
        f"Запрос нутрициолога: {request}\n\n"
        f"Данные из базы:\n{data_context}\n\n"
        "Сделай профессиональный анализ по структуре из системного промпта."
    )
