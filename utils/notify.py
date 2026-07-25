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
    "questionnaire_updated": "Анкета обновлена",
    "meal_not_reported": "Приём пищи не отмечен",
    "reminder_unanswered": "Напоминание без ответа",
    "plan_exception_claimed": "Клиент заявил об исключении из плана",
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
    # calories_logged: детали лежат не в message/reason/answer, а в массиве alerts
    # (food_forbidden/несочетаемость/аллерген) — собираем текст оттуда.
    alerts_detail = "; ".join(
        str(a.get("message")) for a in (payload.get("alerts") or [])
        if isinstance(a, dict) and a.get("message")
    )
    # meal_not_reported/reminder_unanswered: своего message/reason нет — деталь
    # собирается из title/expected напоминания (см. api/scheduler.py::run_reminder_followups).
    reminder_detail = ""
    if event_type in ("meal_not_reported", "reminder_unanswered"):
        reminder_detail = " — ".join(
            str(payload[k]) for k in ("title", "expected") if payload.get(k)
        )
    # plan_exception_claimed (P1-10): свой payload item/client_claim, не message/reason.
    exception_detail = ""
    if event_type == "plan_exception_claimed":
        exception_detail = " — ".join(
            str(payload[k]) for k in ("item", "client_claim") if payload.get(k)
        )
    detail = (
        payload.get("message")
        or payload.get("reason")
        or payload.get("answer")
        or alerts_detail
        or reminder_detail
        or exception_detail
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


def format_telegram_linked(client_name: str, telegram_id: int) -> str:
    """
    Текст уведомления нутрициологу о факте привязки Telegram клиентом.

    Нужен для контроля: если привязался не тот человек (ссылка попала постороннему),
    нутрициолог увидит факт и сможет отвязать/перевыпустить ссылку в карточке клиента.
    """
    return (
        "🔗 Привязка Telegram\n"
        f"Клиент: {client_name or 'Клиент'}\n"
        f"Telegram ID: {telegram_id}\n"
        "Если это не тот человек — отвяжите в карточке клиента и создайте новую ссылку."
    )
