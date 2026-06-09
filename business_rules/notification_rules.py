"""
Notification Rules — Правила отправки уведомлений

Проверяет:
1. Включены ли уведомления (is_enabled)
2. Находится ли текущее время в разрешённом диапазоне (timezone-aware)
3. Тип уведомления разрешён для клиента

Используется для ИСХОДЯЩИХ уведомлений от системы (n8n, cron, триггеры)
НЕ используется для входящих сообщений от клиента
"""

from typing import Dict, Any
from datetime import datetime, time
import pytz
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.queries import get_notification_schedule, get_client_by_id


def check_notification_allowed(
    client_id: str,
    notification_type: str
) -> Dict[str, Any]:
    """
    Проверка возможности отправки уведомления клиенту

    Args:
        client_id: UUID клиента
        notification_type: тип уведомления (например: 'daily_reminder', 'meal_prompt', 'weekly_report')

    Returns:
        {
            "allowed": bool,
            "reason": str,
            "next_allowed_time": str (ISO format) | None,
            "schedule": Dict (информация о расписании)
        }
    """
    try:
        # Получить расписание клиента
        schedule = get_notification_schedule(client_id)

        if not schedule:
            # Если расписания нет — по умолчанию запрещаем
            return {
                "allowed": False,
                "reason": "no_schedule",
                "next_allowed_time": None,
                "schedule": None
            }

        # [1] ПРОВЕРКА: Уведомления включены?
        if not schedule.get('is_enabled', True):
            return {
                "allowed": False,
                "reason": "notifications_disabled",
                "next_allowed_time": None,
                "schedule": schedule
            }

        # [2] ПРОВЕРКА: Находимся ли в разрешённом времени?
        client = get_client_by_id(client_id)
        timezone_str = client.get('timezone', 'UTC') if client else 'UTC'

        within_hours = is_within_allowed_hours(
            client_id=client_id,
            timezone_str=timezone_str,
            schedule=schedule
        )

        if not within_hours["within_hours"]:
            return {
                "allowed": False,
                "reason": "outside_allowed_hours",
                "next_allowed_time": within_hours.get("next_allowed_time"),
                "schedule": schedule
            }

        # [3] ВСЁ ОК — можно отправлять
        return {
            "allowed": True,
            "reason": "ok",
            "next_allowed_time": None,
            "schedule": schedule
        }

    except Exception as e:
        # В случае ошибки — безопасность: не отправляем
        return {
            "allowed": False,
            "reason": f"error: {str(e)}",
            "next_allowed_time": None,
            "schedule": None
        }


def is_within_allowed_hours(
    client_id: str,
    timezone_str: str = 'UTC',
    schedule: Dict = None
) -> Dict[str, Any]:
    """
    Проверяет, находится ли текущее время в разрешённом диапазоне

    Args:
        client_id: UUID клиента
        timezone_str: временная зона клиента (например: 'Asia/Dubai')
        schedule: расписание клиента (опционально, если None — получит из БД)

    Returns:
        {
            "within_hours": bool,
            "current_time": str (ISO format),
            "client_timezone": str,
            "allowed_start": str (HH:MM),
            "allowed_end": str (HH:MM),
            "next_allowed_time": str (ISO format) | None
        }
    """
    try:
        # Получить расписание если не передано
        if schedule is None:
            schedule = get_notification_schedule(client_id)

        if not schedule:
            # Если расписания нет — по умолчанию 08:00-22:00
            schedule = {
                'allowed_start_time': time(8, 0),
                'allowed_end_time': time(22, 0)
            }

        # Получить временную зону
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.UTC

        # Текущее время в зоне клиента
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_client = now_utc.astimezone(tz)

        # Разрешённый диапазон
        start_time = schedule.get('allowed_start_time')
        end_time = schedule.get('allowed_end_time')

        # Конвертируем из строки если нужно
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, '%H:%M:%S').time()
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, '%H:%M:%S').time()

        # Если времена не указаны — по умолчанию 08:00-22:00
        if not start_time:
            start_time = time(8, 0)
        if not end_time:
            end_time = time(22, 0)

        # Проверка: текущее время в диапазоне?
        current_time = now_client.time()

        # Обработка случая когда диапазон пересекает полночь (например: 22:00-08:00)
        if start_time <= end_time:
            # Обычный диапазон (например: 08:00-22:00)
            within = start_time <= current_time <= end_time
        else:
            # Диапазон через полночь (например: 22:00-08:00)
            within = current_time >= start_time or current_time <= end_time

        # Вычислить следующее разрешённое время
        next_allowed = None
        if not within:
            # Если сейчас до начала диапазона — следующее время = start_time сегодня
            if current_time < start_time:
                next_allowed = now_client.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0
                )
            else:
                # Если после конца диапазона — следующее время = start_time завтра
                from datetime import timedelta
                next_day = now_client + timedelta(days=1)
                next_allowed = next_day.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0
                )

        return {
            "within_hours": within,
            "current_time": now_client.isoformat(),
            "client_timezone": timezone_str,
            "allowed_start": start_time.strftime('%H:%M'),
            "allowed_end": end_time.strftime('%H:%M'),
            "next_allowed_time": next_allowed.isoformat() if next_allowed else None
        }

    except Exception as e:
        # В случае ошибки — возвращаем False (не отправляем)
        return {
            "within_hours": False,
            "current_time": datetime.utcnow().isoformat(),
            "client_timezone": timezone_str,
            "allowed_start": "unknown",
            "allowed_end": "unknown",
            "next_allowed_time": None,
            "error": str(e)
        }


def get_client_timezone(client_id: str) -> str:
    """
    Получить временную зону клиента

    Args:
        client_id: UUID клиента

    Returns:
        Строка временной зоны (например: 'Asia/Dubai')
        По умолчанию: 'UTC'
    """
    try:
        client = get_client_by_id(client_id)
        return client.get('timezone', 'UTC') if client else 'UTC'
    except Exception:
        return 'UTC'
