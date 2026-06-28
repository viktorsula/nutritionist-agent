"""
Обработчики команд Telegram бота
/start, /help, /status
"""

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from database.queries import (
    get_client_by_link_token,
    get_client_by_telegram_id,
    get_user_by_telegram_id,
    link_client_telegram,
)

logger = logging.getLogger(__name__)


def _token_expired(expires_at) -> bool:
    """True, если срок токена привязки истёк. Пустой expires_at — трактуем как бессрочный."""
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp < datetime.now(timezone.utc)


async def _notify_nutritionist_linked(context, client_name: str, telegram_id: int) -> None:
    """Best-effort уведомление нутрициолога о факте привязки (для контроля)."""
    try:
        from utils.notify import format_telegram_linked, nutritionist_chat_id

        chat_id = nutritionist_chat_id()
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=format_telegram_linked(client_name, telegram_id),
            )
    except Exception as e:
        logger.warning(f"Не удалось уведомить нутрициолога о привязке: {e}")


async def _handle_link_token(update, context, token: str, telegram_id: int) -> bool:
    """
    Обрабатывает deep-link привязки (/start <token>). Возвращает True, если уже ответил
    (привязал ИЛИ объяснил отказ) — тогда start_command завершается.

    Контроль у нутрициолога: токен одноразовый и со сроком; чужой telegram_id не
    перепишет привязку другого клиента; о привязке шлём уведомление нутрициологу.
    """
    candidate = get_client_by_link_token(token)
    if not candidate:
        await update.message.reply_text(
            "⚠️ Ссылка привязки недействительна. Попросите нутрициолога создать новую."
        )
        return True

    if _token_expired(candidate.get("telegram_link_token_expires_at")):
        await update.message.reply_text(
            "⌛️ Срок действия ссылки истёк. Попросите нутрициолога создать новую."
        )
        return True

    # Этот Telegram уже привязан к ДРУГОМУ клиенту — не переписываем молча.
    existing = get_client_by_telegram_id(telegram_id)
    if existing and existing.get("id") != candidate.get("id"):
        await update.message.reply_text(
            "⚠️ Этот Telegram уже привязан к другому профилю. Обратитесь к нутрициологу."
        )
        return True

    link_client_telegram(candidate["id"], telegram_id)
    name = candidate.get("name") or "клиент"
    logger.info(f"Telegram привязан: client_id={candidate['id']} telegram_id={telegram_id}")
    await _notify_nutritionist_linked(context, name, telegram_id)
    await update.message.reply_text(
        f"✅ Готово, {name}! Ваш Telegram привязан.\n\n"
        "Теперь пишите мне что угодно:\n"
        "• что ели сегодня\n"
        "• как себя чувствуете\n"
        "• вопрос о питании\n"
        "• фото еды\n\n"
        "Используйте /help для списка команд."
    )
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /start — приветствие, привязка по ссылке (/start <token>) и подсказка регистрации.
    """
    telegram_id = update.effective_user.id
    username = update.effective_user.username or "друг"
    first_name = update.effective_user.first_name or ""

    logger.info(f"Команда /start от telegram_id={telegram_id}, username={username}")

    # Нутрициолог (по NUTRITIONIST_TELEGRAM_ID) — отдельное приветствие
    user = get_user_by_telegram_id(telegram_id)
    if user and user.get("role") == "nutritionist":
        message = (
            "👋 Здравствуйте! Это ваш агент-ассистент.\n\n"
            "В этом чате можно работать так же, как в кабинете:\n"
            "• задать аналитический вопрос по клиенту или базе\n"
            "• дать команду (задача, план, статус — с подтверждением)\n\n"
            "Сюда же я буду присылать важные алерты по клиентам.\n"
            "Используйте /help для списка команд."
        )
        await update.message.reply_text(message, parse_mode="Markdown")
        return

    # Deep-link привязки: /start <token>
    token = context.args[0] if getattr(context, "args", None) else None
    if token and await _handle_link_token(update, context, token, telegram_id):
        return

    # Проверяем есть ли клиент в БД
    client = get_client_by_telegram_id(telegram_id)

    if client:
        # Существующий клиент (queries возвращает dict)
        message = f"👋 С возвращением, {client.get('name') or first_name}!\n\n"
        message += "Я ваш персональный ассистент по питанию.\n"
        message += "Можете написать мне что угодно:\n"
        message += "• Что ели сегодня\n"
        message += "• Как себя чувствуете\n"
        message += "• Задать вопрос о питании\n"
        message += "• Отправить фото еды\n\n"
        message += "Используйте /help для списка команд."
    else:
        # Новый пользователь
        message = f"👋 Привет, {first_name}!\n\n"
        message += "Я — агент-ассистент для нутрициолога.\n\n"
        message += "🔐 Для начала работы вам нужно зарегистрироваться:\n"
        message += "1. Обратитесь к вашему нутрициологу\n"
        message += "2. Нутрициолог добавит вас в систему\n"
        message += "3. После этого я смогу с вами общаться\n\n"
        message += f"Ваш Telegram ID: `{telegram_id}`\n"
        message += "(передайте этот ID нутрициологу)"

        logger.warning(f"Незарегистрированный пользователь telegram_id={telegram_id}")

    await update.message.reply_text(message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /help — список команд и возможностей
    """
    telegram_id = update.effective_user.id
    client = get_client_by_telegram_id(telegram_id)

    if not client:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе.\n"
            "Используйте /start для получения инструкций."
        )
        return

    message = "📋 **Доступные команды:**\n\n"
    message += "/start — перезапуск бота\n"
    message += "/help — это сообщение\n"
    message += "/status — ваш статус и текущий план\n\n"
    message += "💬 **Что я умею:**\n\n"
    message += "• Вести дневник питания\n"
    message += "• Анализировать фото еды\n"
    message += "• Отвечать на вопросы о питании\n"
    message += "• Напоминать о задачах\n"
    message += "• Отслеживать ваше самочувствие\n\n"
    message += "Просто пишите мне как обычному человеку!"

    await update.message.reply_text(message, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /status — информация о клиенте и текущем плане
    """
    telegram_id = update.effective_user.id
    client = get_client_by_telegram_id(telegram_id)

    if not client:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе.\n"
            "Используйте /start для получения инструкций."
        )
        return

    # Импортируем здесь чтобы избежать circular import
    from database.queries import (
        get_active_nutrition_plan,
        get_client_profile,
        get_pending_tasks
    )

    # Формируем статус (queries возвращают dict)
    client_id = client.get("id")
    message = f"📊 **Ваш статус**\n\n"
    message += f"**Имя:** {client.get('name')}\n"
    message += f"**Статус:** {_format_client_status(client.get('client_status'))}\n"
    message += f"**Оплата:** {_format_payment_status(client.get('payment_status'))}\n"
    message += f"**Доступ:** {_format_access_status(client.get('access_status'))}\n\n"

    # Профиль
    profile = get_client_profile(client_id)
    if profile and profile.get("weight"):
        message += f"**Вес:** {profile.get('weight')} кг"
        if profile.get("target_weight"):
            message += f" → цель: {profile.get('target_weight')} кг"
        message += "\n\n"

    # Текущий план
    plan = get_active_nutrition_plan(client_id)
    if plan:
        message += f"📋 **Текущий план:**\n"
        message += f"• {plan.get('title')}\n"
        message += f"• Версия: {plan.get('version')}\n"
        effective_from = str(plan.get("effective_from") or "")[:10]
        if effective_from:
            message += f"• С {effective_from}\n"
        message += "\n"
    else:
        message += "📋 **План питания:** не назначен\n\n"

    # Активные задачи
    tasks = get_pending_tasks(client_id)
    if tasks:
        message += f"✅ **Активные задачи:** {len(tasks)}\n"
        for task in tasks[:3]:  # Показываем первые 3
            message += f"• {task.get('title')}\n"
        if len(tasks) > 3:
            message += f"• ... ещё {len(tasks) - 3}\n"
    else:
        message += "✅ **Активные задачи:** нет\n"

    await update.message.reply_text(message, parse_mode="Markdown")


def _format_client_status(status: str) -> str:
    """Форматирование статуса клиента"""
    mapping = {
        'lead': '🆕 Лид',
        'onboarding': '📝 Онбординг',
        'active': '✅ Активный',
        'paused': '⏸️ На паузе',
        'completed': '✔️ Завершён',
        'archived': '📦 Архив'
    }
    return mapping.get(status, status)


def _format_payment_status(status: str) -> str:
    """Форматирование статуса оплаты"""
    mapping = {
        'trial': '🎁 Триал',
        'active': '💳 Оплачено',
        'inactive': '⏳ Неактивно'
    }
    return mapping.get(status, status)


def _format_access_status(status: str) -> str:
    """Форматирование статуса доступа"""
    mapping = {
        'active': '🟢 Активен',
        'frozen': '🔴 Заморожен'
    }
    return mapping.get(status, status)
