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
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pytz

logger = logging.getLogger(__name__)

_scheduler = None
_sent_guard: set = set()  # ключи "client_id:type:YYYY-MM-DD HH:MM" — анти-дубль
_alert_guard: set = set()  # id уже отправленных нутрициологу событий — анти-дубль
_no_response_guard: set = set()  # "client_id:YYYY-MM-DD" — один алерт молчания в день
_last_no_response_at: Optional[datetime] = None
NO_RESPONSE_CHECK_EVERY_MIN = 30

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


def _reminder_due_today(reminder: dict, now_local: datetime) -> bool:
    """Совпадает ли текущий локальный день клиента с регулярностью напоминания."""
    rec = reminder.get("recurrence")
    if rec == "daily":
        return True
    if rec == "weekly":
        return now_local.weekday() == reminder.get("weekday")
    if rec == "once":
        rd = reminder.get("remind_date")
        return bool(rd) and str(rd) == now_local.strftime("%Y-%m-%d")
    return False


def _fallback_reminder_text(titles: list) -> str:
    """Детерминированный текст пакета напоминаний (если LLM недоступен)."""
    if len(titles) == 1:
        return f"🔔 Напоминание: {titles[0]}"
    lines = "\n".join(f"• {t}" for t in titles)
    return f"🔔 Напоминания на сегодня:\n{lines}"


def compose_reminder_message(titles: list) -> str:
    """
    Тёплый текст ОДНОГО сообщения на пакет напоминаний. Лёгкий LLM
    (task_type='reminder', редактируемый промпт client/reminder_message) →
    при любом сбое откат на детерминированный шаблон-список.
    """
    fallback = _fallback_reminder_text(titles)
    try:
        from utils.llm import call_llm
        from prompts import load_prompt

        system = load_prompt("client/reminder_message")
        user = "Напоминания на сейчас:\n" + "\n".join(f"- {t}" for t in titles)
        resp = call_llm(
            task_type="reminder",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = (resp.get("content") or "").strip()
        return text or fallback
    except Exception as e:
        logger.warning(f"scheduler: LLM-текст напоминаний не удался, шаблон: {e}")
        return fallback


async def run_reminders() -> None:
    """
    Один проход: разослать наступившие напоминания клиентам. Все напоминания клиента
    на одно и то же локальное время идут ОДНИМ сообщением (пакет). Best-effort.

    Дедуп — durable через reminder_occurrences (UNIQUE reminder_id+due_date).
    """
    from collections import defaultdict
    from api.telegram_webhook import is_configured, get_bot

    if not is_configured():
        return

    from database import queries

    try:
        reminders = queries.get_active_reminders()
    except Exception as e:
        logger.warning(f"scheduler: не удалось получить напоминания: {e}")
        return

    bot = get_bot()
    if bot is None:
        return

    # Собрать наступившие в пакеты по (client_id, telegram_id, локальная дата).
    buckets: dict = defaultdict(list)
    for r in reminders or []:
        client = r.get("clients") or {}
        telegram_id = client.get("telegram_id")
        if not telegram_id:
            continue

        try:
            tz = pytz.timezone(client.get("timezone") or "UTC")
        except Exception:
            tz = pytz.UTC
        now_local = datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(tz)

        parts = str(r.get("remind_at") or "").split(":")
        try:
            sh, sm = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            continue
        if now_local.hour != sh or now_local.minute != sm:
            continue
        if not _reminder_due_today(r, now_local):
            continue

        due_date = now_local.strftime("%Y-%m-%d")
        try:
            if queries.occurrence_exists(r["id"], due_date):
                continue  # уже отправляли сегодня
        except Exception as e:
            logger.warning(f"scheduler: проверка occurrence не удалась reminder={r.get('id')}: {e}")
            continue

        buckets[(r["client_id"], telegram_id, due_date)].append(r)

    for (client_id, telegram_id, due_date), items in buckets.items():
        titles = [r.get("title", "").strip() for r in items if r.get("title")]
        if not titles:
            continue
        text = compose_reminder_message(titles)
        try:
            await bot.send_message(chat_id=telegram_id, text=text)
        except Exception as e:
            logger.warning(f"scheduler: отправка напоминаний не удалась client={client_id}: {e}")
            continue
        # Фиксируем срабатывания только после успешной отправки (UNIQUE защитит от дублей).
        # Для ждущих ответа сразу проставляем время первого повтора (контур ответа, Слайс 2B).
        now_utc = datetime.utcnow()
        for r in items:
            try:
                queries.record_occurrence(
                    r["id"], client_id, due_date, next_followup_at=_initial_followup_at(r, now_utc)
                )
            except Exception:
                pass
        logger.info(
            f"scheduler: напоминания отправлены client={client_id} count={len(items)} ({due_date})"
        )


# ==========================================================================
# Контроль ответа на напоминания (Слайс 2B) — детект / догон / «сдались»
# ==========================================================================

# Профили кадэнса догона по типу ожидаемого ответа (часы). Правятся без кода через
# system_settings.reminder_cadence; здесь — дефолты. give_up_hours подобран короче
# интервала recurrence (для ежедневных <24ч), поэтому догон не заходит за следующее
# плановое срабатывание (единая формула min(окно, следующее срабатывание)).
MEAL_TYPES = ("breakfast", "lunch", "dinner")

DEFAULT_REMINDER_CADENCE = {
    "weight":      {"followup_hours": 3,  "max_followups": 1, "give_up_hours": 14},
    "measurement": {"followup_hours": 24, "max_followups": 2, "give_up_hours": 72},
    "labs":        {"followup_hours": 72, "max_followups": 1, "give_up_hours": 168},
    "sleep":       {"followup_hours": 3,  "max_followups": 1, "give_up_hours": 14},
    "water":       {"followup_hours": 3,  "max_followups": 1, "give_up_hours": 14},
    "meals":       {"followup_hours": 2,  "max_followups": 1, "give_up_hours": 12},
    "text":        {"followup_hours": 3,  "max_followups": 1, "give_up_hours": 14},
    "default":     {"followup_hours": 24, "max_followups": 1, "give_up_hours": 72},
}


def _cadence_key(expected: Optional[str]) -> str:
    """Ключ профиля кадэнса по ожидаемому ответу."""
    if not expected or expected == "none":
        return "text"
    if expected == "weight":
        return "weight"
    if expected in ("waist", "neck", "hips", "chest"):
        return "measurement"
    if expected == "sleep":
        return "sleep"
    if expected == "water":
        return "water"
    if expected in MEAL_TYPES:
        return "meals"
    if expected in ("labs", "lab"):
        return "labs"
    if expected == "text":
        return "text"
    return "default"  # произвольный контролируемый показатель


def resolve_cadence(expected: Optional[str]) -> dict:
    """Профиль догона по типу ответа: БД-override (reminder_cadence) → код-дефолт."""
    profiles = {k: dict(v) for k, v in DEFAULT_REMINDER_CADENCE.items()}
    try:
        from database import queries

        override = queries.get_setting("reminder_cadence")
        if isinstance(override, dict):
            for key, val in override.items():
                if isinstance(val, dict):
                    profiles[key] = {**profiles.get(key, {}), **val}
    except Exception:
        pass
    return profiles.get(_cadence_key(expected), profiles["default"])


def _item_cadence(reminder: dict) -> dict:
    """Профиль кадэнса с per-элемент переопределением (followup_after_hours/max_followups)."""
    profile = dict(resolve_cadence(reminder.get("expected_response")))
    fa = reminder.get("followup_after_hours")
    mf = reminder.get("max_followups")
    if fa is not None:
        profile["followup_hours"] = fa
    if mf is not None:
        profile["max_followups"] = mf
    return profile


def _initial_followup_at(reminder: dict, now_utc: datetime) -> Optional[str]:
    """Время первого повтора для ждущего ответа напоминания (иначе None — без догона)."""
    if not reminder.get("requires_response"):
        return None
    profile = _item_cadence(reminder)
    return (now_utc + timedelta(hours=profile["followup_hours"])).isoformat()


def _deadline_utc(due_date: str, deadline: str, tz_str: Optional[str]) -> Optional[datetime]:
    """Дедлайн отчёта: локальные due_date+deadline (HH:MM) → наивный UTC. None при ошибке."""
    try:
        tz = pytz.timezone(tz_str or "UTC")
    except Exception:
        tz = pytz.UTC
    try:
        y, m, d = (int(x) for x in str(due_date).split("-"))
        hh, mm = (int(x) for x in str(deadline).split(":")[:2])
        local = tz.localize(datetime(y, m, d, hh, mm))
    except (ValueError, IndexError):
        return None
    return local.astimezone(pytz.UTC).replace(tzinfo=None)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """ISO-таймстамп (с tz или без) → наивный datetime в UTC. None при ошибке."""
    if not value:
        return None
    s = str(value).replace("Z", "+00:00").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s.split(".")[0])
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)
    return dt


def _detect_response(client_id: str, expected: Optional[str], since: str) -> bool:
    """Пришёл ли ожидаемый ответ после отправки (по типу показателя)."""
    from database import queries

    if not expected or expected in ("text", "none"):
        return queries.has_client_message_since(client_id, since)
    if expected == "weight" or expected in ("waist", "neck", "hips", "chest"):
        return queries.has_measurement_since(client_id, expected, since)
    if expected in ("labs", "lab"):
        return queries.has_lab_result_since(client_id, since)
    if expected == "water":
        return queries.has_event_since(client_id, "water_logged", since)
    if expected in MEAL_TYPES:
        return queries.has_meal_event_since(client_id, expected, since)
    return queries.has_client_metric_since(client_id, expected, since)  # sleep / custom


async def run_reminder_followups() -> None:
    """
    Один проход контроля ответа: для открытых срабатываний ждущих ответа напоминаний —
    детект ответа (закрыть), догон (повтор), «сдались» (просрочка → low-severity алерт).
    """
    from api.telegram_webhook import is_configured, get_bot

    if not is_configured():
        return

    from database import queries

    try:
        occurrences = queries.get_open_occurrences()
    except Exception as e:
        logger.warning(f"scheduler: не удалось получить открытые срабатывания: {e}")
        return

    bot = get_bot()
    if bot is None:
        return

    now = datetime.utcnow()
    for occ in occurrences or []:
        reminder = occ.get("reminders") or {}
        if not reminder.get("requires_response") or not reminder.get("active"):
            continue

        client_id = occ.get("client_id")
        expected = reminder.get("expected_response")
        sent_dt = _parse_ts(occ.get("sent_at"))
        if not client_id or sent_dt is None:
            continue

        # 1) Ответ пришёл → закрываем срабатывание.
        try:
            answered = _detect_response(client_id, expected, occ.get("sent_at"))
        except Exception as e:
            logger.warning(f"scheduler: детект ответа не удался occ={occ.get('id')}: {e}")
            answered = False
        if answered:
            queries.mark_occurrence_answered(occ["id"], {"expected": expected})
            logger.info(f"scheduler: напоминание закрыто ответом occ={occ['id']} expected={expected}")
            continue

        profile = _item_cadence(reminder)

        # Срок «сдаться»: дедлайн отчёта (напр. еда 12/17/22 локально), иначе sent + окно профиля.
        deadline = reminder.get("response_deadline")
        tz_str = (occ.get("clients") or {}).get("timezone")
        give_up_at = None
        if deadline:
            give_up_at = _deadline_utc(occ.get("due_date"), deadline, tz_str)
        if give_up_at is None:
            give_up_at = sent_dt + timedelta(hours=profile["give_up_hours"])

        # 2) Срок вышел → «сдались». Пропуск ЕДЫ — важен нутрициологу (medium + пуш в Telegram);
        #    прочее (вес/сон/…) — low в панель.
        if now >= give_up_at:
            queries.mark_occurrence_expired(occ["id"])
            is_meal = expected in MEAL_TYPES
            try:
                queries.log_client_event(
                    client_id=client_id,
                    event_type="meal_not_reported" if is_meal else "reminder_unanswered",
                    severity="medium" if is_meal else "low",
                    payload={"reminder_id": occ.get("reminder_id"),
                             "title": reminder.get("title"), "expected": expected},
                )
            except Exception as e:
                logger.warning(f"scheduler: алерт просрочки не записан occ={occ.get('id')}: {e}")
            logger.info(f"scheduler: напоминание просрочено (без ответа) occ={occ['id']} meal={is_meal}")
            continue

        # 3) Пора повторить (не превысив макс повторов).
        telegram_id = (occ.get("clients") or {}).get("telegram_id")
        nfu = _parse_ts(occ.get("next_followup_at"))
        if telegram_id and nfu and now >= nfu and (occ.get("followups_sent") or 0) < profile["max_followups"]:
            title = (reminder.get("title") or "").strip()
            try:
                await bot.send_message(chat_id=telegram_id, text=compose_reminder_message([title]))
            except Exception as e:
                logger.warning(f"scheduler: повтор напоминания не отправлен occ={occ.get('id')}: {e}")
                continue
            next_at = (now + timedelta(hours=profile["followup_hours"])).isoformat()
            queries.bump_occurrence_followup(occ["id"], next_at)
            logger.info(f"scheduler: повтор напоминания отправлен occ={occ['id']}")


async def run_no_response_check() -> None:
    """
    Периодически: активные клиенты, молчащие дольше порога → событие `no_response`
    (severity из medical_rules; high пушится нутрициологу). Дедуп — один алерт в день на клиента.

    Оживляет алерт молчания: медицинское правило существовало, но джоб не был на расписании.
    Порог — `system_settings.no_response_threshold_hours`. Тротлинг — раз в NO_RESPONSE_CHECK_EVERY_MIN.
    """
    global _last_no_response_at
    now = datetime.utcnow()
    if _last_no_response_at and (now - _last_no_response_at).total_seconds() < NO_RESPONSE_CHECK_EVERY_MIN * 60:
        return
    _last_no_response_at = now

    from database import queries
    from business_rules import medical_rules

    try:
        clients = queries.get_all_clients(status="active")
    except Exception as e:
        logger.warning(f"scheduler: no_response — список клиентов не получен: {e}")
        return

    today = now.strftime("%Y-%m-%d")
    for c in clients or []:
        cid = c.get("id")
        if not cid:
            continue
        key = f"{cid}:{today}"
        if key in _no_response_guard:
            continue
        try:
            alert = medical_rules._check_no_response(cid)
        except Exception:
            alert = None
        if not alert:
            continue
        try:
            queries.log_client_event(
                client_id=cid, event_type="no_response",
                severity=alert.get("severity") or "medium", payload=alert.get("details"),
            )
            _no_response_guard.add(key)
            if len(_no_response_guard) > 5000:
                _no_response_guard.clear()
            logger.info(f"scheduler: no_response алерт создан client={cid}")
        except Exception as e:
            logger.warning(f"scheduler: no_response событие не записано client={cid}: {e}")


async def run_scheduler_pass() -> None:
    """Один тик планировщика: напоминания клиентам + алерты нутрициологу (оба best-effort)."""
    await run_due_notifications()
    await run_reminders()
    await run_reminder_followups()
    await run_no_response_check()
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
