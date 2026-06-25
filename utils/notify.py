"""
Уведомления нутрициологу в Telegram.

Канал нутрициолога (NUTRITIONIST_TELEGRAM_ID) — двусторонний: входящие сообщения
обрабатывает оркестратор нутрициолога (router → analytics/management), а сюда вынесена
ИСХОДЯЩАЯ часть: форматирование и адрес для пуша критичных событий (алертов).

Ключи: NUTRITIONIST_TELEGRAM_ID из os.environ.get (НИКОГДА load_dotenv).
Доставку выполняет планировщик (api/scheduler.py) через активного бота — здесь только
чистые функции (текст + chat_id), без сетевых вызовов, чтобы было легко тестировать.
"""

import os
from typing import Any, Dict, Optional

# Иконки по уровню важности — для быстрого визуального восприятия в чате.
_SEVERITY_ICON = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "⚪️",
}

# Человекочитаемые названия типов событий.
_EVENT_LABEL = {
    "bad_wellbeing": "Плохое самочувствие",
    "weight_increase": "Превышение веса",
    "food_forbidden": "Запрещённый продукт",
    "food_incompatible": "Несочетаемые продукты",
    "no_response": "Нет ответа клиента",
}


def nutritionist_chat_id() -> Optional[str]:
    """Telegram chat_id нутрициолога из NUTRITIONIST_TELEGRAM_ID (или None, если не задан)."""
    value = (os.environ.get("NUTRITIONIST_TELEGRAM_ID") or "").strip()
    return value or None


def format_alert(event: Dict[str, Any]) -> str:
    """
    Текст уведомления об одном событии-алерте для нутрициолога.

    event — строка client_events (с join clients(name)): event_type, severity,
    payload_json, clients{name}.
    """
    severity = (event.get("severity") or "medium").lower()
    icon = _SEVERITY_ICON.get(severity, "🟡")

    event_type = event.get("event_type") or "event"
    label = _EVENT_LABEL.get(event_type, event_type)

    client = event.get("clients") or {}
    client_name = client.get("name") or "Клиент"

    payload = event.get("payload_json") or {}
    detail = (
        payload.get("message")
        or payload.get("reason")
        or payload.get("answer")
        or ""
    ).strip()

    lines = [
        f"{icon} Алерт: {label}",
        f"Клиент: {client_name}",
        f"Уровень: {severity}",
    ]
    if detail:
        lines.append(f"Детали: {detail}")
    lines.append("Подробнее — в кабинете, панель «Алерты».")
    return "\n".join(lines)
