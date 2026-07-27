"""
Telegram Bot — основной модуль
Использует python-telegram-bot и единый роутер agents.route_message()
"""

import os
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters
)

from .commands import start_command, help_command, status_command
from .handlers import (
    handle_text_message,
    handle_photo_message,
    handle_voice_message,
    handle_document_message,
    handle_unsupported_message,
    error_handler
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def build_application(token: str = None) -> Application:
    """
    Собирает и настраивает PTB Application (регистрирует команды и обработчики).

    Общий билдер для двух режимов запуска: polling (start_bot) и webhook
    (api.telegram_webhook). Токен — из аргумента или TELEGRAM_BOT_TOKEN.
    """
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

    application = Application.builder().token(token).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))

    # Сообщения
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    application.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message)
    )
    application.add_handler(
        MessageHandler(filters.Document.ALL, handle_document_message)
    )
    # Catch-all (P2-3) — ТОЛЬКО последним: ловит то, что не разобрали обработчики выше
    # (стикер/видео/кружок/геолокация/контакт/опрос). Раньше такие сообщения молча
    # терялись, и для клиента это выглядело как «бот не отвечает».
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_unsupported_message)
    )

    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    return application


def start_bot():
    """Запуск Telegram бота в режиме polling (локально/воркер)."""
    logger.info("Запуск Telegram бота (polling)...")
    application = build_application()
    logger.info("Бот запущен и ожидает сообщений...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    start_bot()
