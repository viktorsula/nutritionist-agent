"""
Обработчики команд Telegram бота
/start, /help, /status
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from database.queries import get_client_by_telegram_id

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /start — приветствие и регистрация
    """
    telegram_id = update.effective_user.id
    username = update.effective_user.username or "друг"
    first_name = update.effective_user.first_name or ""

    logger.info(f"Команда /start от telegram_id={telegram_id}, username={username}")

    # Проверяем есть ли клиент в БД
    client = get_client_by_telegram_id(telegram_id)

    if client:
        # Существующий клиент
        message = f"👋 С возвращением, {client.name}!\n\n"
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

    # Формируем статус
    message = f"📊 **Ваш статус**\n\n"
    message += f"**Имя:** {client.name}\n"
    message += f"**Статус:** {_format_client_status(client.client_status)}\n"
    message += f"**Оплата:** {_format_payment_status(client.payment_status)}\n"
    message += f"**Доступ:** {_format_access_status(client.access_status)}\n\n"

    # Профиль
    profile = get_client_profile(client.id)
    if profile and profile.weight:
        message += f"**Вес:** {profile.weight} кг"
        if profile.target_weight:
            message += f" → цель: {profile.target_weight} кг"
        message += "\n\n"

    # Текущий план
    plan = get_active_nutrition_plan(client.id)
    if plan:
        message += f"📋 **Текущий план:**\n"
        message += f"• {plan.title}\n"
        message += f"• Версия: {plan.version}\n"
        message += f"• С {plan.effective_from.strftime('%d.%m.%Y')}\n\n"
    else:
        message += "📋 **План питания:** не назначен\n\n"

    # Активные задачи
    tasks = get_pending_tasks(client.id)
    if tasks:
        message += f"✅ **Активные задачи:** {len(tasks)}\n"
        for task in tasks[:3]:  # Показываем первые 3
            message += f"• {task.title}\n"
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
