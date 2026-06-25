"""
Планировщик уведомлений (APScheduler) — timezone-aware чек-ины/напоминания.

Решение v1: вместо n8n уведомления гонит встроенный AsyncIOScheduler внутри FastAPI
(тот же процесс, что и Telegram-webhook). Раз в минуту проверяем активные расписания
(notification_schedule) и для тех, у кого по локальному времени клиента наступил
scheduled_time, шлём сообщение в Telegram.

Дедупликация: матчим точную минуту HH:MM в часовом поясе клиента (интервал 60с →
одно срабатывание в день) + in-memory guard на случай повторов внутри минуты/процесса.

Инертность: если Telegram-бот не настроен (нет токена) — рассылка пропускается.
Полное отключение: NOTIFICATIONS_ENABLED=0.

ENV: NOTIFICATIONS_ENABLED (по умолч. включено).
"""

import logging
import os
from datetime import datetime
from typing import Optional, Tuple

import pytz

logger = logging.getLogger(__name__)

_scheduler = None
_sent_guard: set = set()  # ключи "client_id:type:YYYY-MM-DD HH:MM" — анти-дубль
_alert_guard: set = set()  # id уже отправленных нутрициологу событий — анти-дубль

CHECK_INTERVAL_SECONDS = 60
# Окно выборки свежих алертов (минут). Чуть больше интервала прохода — на случай джиттера.
ALERT_LOOKBACK_MINUTES = 5

NOTIFICATION_TEMPLATES = {
    "morning": "Доброе утро! ☀️ Как самочувствие? Что планируете на завтрак?",
    "evening": "Добрый вечер! 🌙 Как прошёл день? Что ели сегодня?",
    "reminder": "Напоминание от вашего нутрициолога 🙂 Как ваши дела?",
    "custom": "У вас сообщение по плану сопровождения.",
}


def _message_for(notification_type: Optional[str]) -> str:
    """Текст уведомления по типу (TODO v1.1: брать из system_settings.notification_templates)."""
    return NOTIFICATION_TEMPLATES.get(notification_type, NOTIFICATION_TEMPLATES["reminder"])


def _is_due(
    scheduled_time: Optional[str],
    timezone_str: Optional[str],
    now_utc: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Наступило ли время уведомления в часовом поясе клиента (с точностью до минуты).

    Returns: (due, stamp) — stamp 'YYYY-MM-DD HH:MM' в зоне клиента (для анти-дубля).
    """
    if not scheduled_time:
        return False, ""
    try:
        tz = pytz.timezone(timezone_str or "UTC")
    except Exception:
        tz = pytz.UTC

    base = now_utc or datetime.utcnow().replace(tzinfo=pytz.UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=pytz.UTC)
    now_local = base.astimezone(tz)

    parts = str(scheduled_time).split(":")
    try:
        sh, sm = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return False, ""

    due = now_local.hour == sh and now_local.minute == sm
    return due, now_local.strftime("%Y-%m-%d %H:%M")


async def run_due_notifications() -> None:
    """Один проход: разослать наступившие уведомления через Telegram. Best-effort."""
    from api.telegram_webhook import is_configured, get_bot

    if not is_configured():
        return  # бот не настроен — слать некуда

    from database import queries

    try:
        schedules = queries.get_notifications_due_now()
    except Exception as e:
        logger.warning(f"scheduler: не удалось получить расписания: {e}")
        return

    bot = get_bot()
    if bot is None:
        return

    for s in schedules or []:
        client = s.get("clients") or {}
        telegram_id = client.get("telegram_id")
        if not telegram_id:
            continue

        tz_str = s.get("timezone") or client.get("timezone") or "UTC"
        due, stamp = _is_due(s.get("scheduled_time"), tz_str)
        if not due:
            continue

        key = f"{s.get('client_id')}:{s.get('notification_type')}:{stamp}"
        if key in _sent_guard:
            continue

        try:
            await bot.send_message(
                chat_id=telegram_id, text=_message_for(s.get("notification_type"))
            )
            _sent_guard.add(key)
            if len(_sent_guard) > 5000:  # не растём бесконечно
                _sent_guard.clear()
            logger.info(f"scheduler: отправлено уведомление client={s.get('client_id')} ({stamp})")
        except Exception as e:
            logger.warning(f"scheduler: отправка не удалась client={s.get('client_id')}: {e}")


async def run_nutritionist_alerts() -> None:
    """
    Один проход: пушит свежие критичные события (алерты) в Telegram нутрициологу.

    Источник — client_events (high/critical + bad_wellbeing). Дедуп по id события.
    Тихо пропускается, если бот не настроен или не задан NUTRITIONIST_TELEGRAM_ID
    (события всё равно остаются в веб-панели «Алерты» — это дублирующий канал).
    """
    from api.telegram_webhook import is_configured, get_bot
    from utils.notify import nutritionist_chat_id, format_alert

    if not is_configured():
        return

    chat_id = nutritionist_chat_id()
    if not chat_id:
        return  # некому слать — нутрициолог не привязал Telegram

    bot = get_bot()
    if bot is None:
        return

    from database import queries

    try:
        events = queries.get_recent_alert_events(ALERT_LOOKBACK_MINUTES)
    except Exception as e:
        logger.warning(f"scheduler: не удалось получить алерты: {e}")
        return

    for ev in events or []:
        ev_id = ev.get("id")
        if not ev_id or ev_id in _alert_guard:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=format_alert(ev))
            _alert_guard.add(ev_id)
            if len(_alert_guard) > 5000:  # не растём бесконечно
                _alert_guard.clear()
            logger.info(f"scheduler: алерт нутрициологу отправлен event={ev_id}")
        except Exception as e:
            logger.warning(f"scheduler: отправка алерта не удалась event={ev_id}: {e}")


async def run_scheduler_pass() -> None:
    """Один тик планировщика: напоминания клиентам + алерты нутрициологу (оба best-effort)."""
    await run_due_notifications()
    await run_nutritionist_alerts()


def start_scheduler() -> None:
    """Запускает AsyncIOScheduler в текущем event loop (вызывать из FastAPI lifespan)."""
    global _scheduler

    if os.environ.get("NOTIFICATIONS_ENABLED", "1").lower() not in ("1", "true", "yes"):
        logger.info("scheduler: отключён (NOTIFICATIONS_ENABLED=0)")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        logger.warning("scheduler: APScheduler не установлен — пропуск")
        return

    try:
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.add_job(
            run_scheduler_pass,
            "interval",
            seconds=CHECK_INTERVAL_SECONDS,
            id="due_notifications",
            max_instances=1,
            coalesce=True,
        )
        _scheduler.start()
        logger.info(f"scheduler: запущен (каждые {CHECK_INTERVAL_SECONDS}с)")
    except Exception as e:
        logger.error(f"scheduler: не удалось запустить: {e}", exc_info=True)
        _scheduler = None


def shutdown_scheduler() -> None:
    """Останавливает планировщик при остановке приложения."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"scheduler shutdown error: {e}")
        finally:
            _scheduler = None
