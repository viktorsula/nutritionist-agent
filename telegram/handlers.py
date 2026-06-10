"""
Обработчики сообщений Telegram бота
Текст, фото, голос
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from database.queries import get_client_by_telegram_id
from agents import route_message

logger = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка текстовых сообщений
    Перенаправляет в agents.route_message()
    """
    telegram_id = update.effective_user.id
    message_text = update.message.text
    username = update.effective_user.username or "unknown"

    logger.info(f"Текстовое сообщение от telegram_id={telegram_id}, username={username}")

    # Проверяем регистрацию
    client = get_client_by_telegram_id(telegram_id)
    if not client:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе.\n"
            "Используйте /start для получения инструкций."
        )
        return

    # Показываем индикатор "печатает..."
    await update.message.chat.send_action("typing")

    try:
        # Маршрутизация через единый роутер
        result = route_message(
            user_id=str(client.user_id),
            message=message_text,
            channel="telegram",
            metadata={
                "telegram_id": telegram_id,
                "username": username,
                "message_id": update.message.message_id
            }
        )

        if result.get("success"):
            response_text = result.get("message", "Сообщение обработано")

            # Отправляем ответ (разбиваем если длинный)
            await _send_long_message(update, response_text)

            logger.info(f"Ответ отправлен telegram_id={telegram_id}")
        else:
            # Обработка ошибок
            error_type = result.get("error")
            error_message = result.get("message", "Произошла ошибка")

            logger.error(f"Ошибка роутера: {error_type}, telegram_id={telegram_id}")

            if error_type == "access_denied":
                await update.message.reply_text(
                    "🔒 Доступ ограничен.\n"
                    f"{error_message}\n\n"
                    "Обратитесь к вашему нутрициологу."
                )
            elif error_type == "no_response_alert":
                # Алерт отправлен нутрициологу, клиент получил ответ
                await update.message.reply_text(error_message)
            else:
                await update.message.reply_text(
                    "⚠️ Возникла проблема при обработке сообщения.\n"
                    "Попробуйте ещё раз или обратитесь к нутрициологу."
                )

    except Exception as e:
        logger.exception(f"Ошибка обработки сообщения telegram_id={telegram_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже или обратитесь к нутрициологу."
        )


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка фото еды
    TODO: интеграция с vision_agent (Этап 6)
    """
    telegram_id = update.effective_user.id

    logger.info(f"Фото от telegram_id={telegram_id}")

    # Проверяем регистрацию
    client = get_client_by_telegram_id(telegram_id)
    if not client:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе.\n"
            "Используйте /start для получения инструкций."
        )
        return

    # TODO Этап 6: интеграция vision_agent
    await update.message.reply_text(
        "📸 Анализ фото пока в разработке.\n"
        "Пока опишите текстом, что на фото, и я помогу!"
    )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка голосовых сообщений
    TODO: интеграция с utils/voice.py + Whisper (Этап 6)
    """
    telegram_id = update.effective_user.id

    logger.info(f"Голосовое от telegram_id={telegram_id}")

    # Проверяем регистрацию
    client = get_client_by_telegram_id(telegram_id)
    if not client:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе.\n"
            "Используйте /start для получения инструкций."
        )
        return

    # TODO Этап 6: интеграция voice.py + Whisper
    await update.message.reply_text(
        "🎤 Распознавание голоса пока в разработке.\n"
        "Пока напишите текстом!"
    )


async def _send_long_message(update: Update, text: str, max_length: int = 4000) -> None:
    """
    Отправка длинного сообщения (разбивка если > max_length)
    Telegram ограничение: 4096 символов
    """
    if len(text) <= max_length:
        await update.message.reply_text(text)
    else:
        # Разбиваем по параграфам
        chunks = []
        current_chunk = ""

        for paragraph in text.split("\n\n"):
            if len(current_chunk) + len(paragraph) + 2 <= max_length:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        # Отправляем по частям
        for i, chunk in enumerate(chunks):
            if i == 0:
                await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(f"...продолжение:\n\n{chunk}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Глобальный обработчик ошибок
    """
    logger.error(f"Необработанная ошибка: {context.error}", exc_info=context.error)

    # Если есть update с сообщением — отправляем пользователю
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла системная ошибка.\n"
            "Наша команда уже в курсе. Попробуйте позже."
        )
