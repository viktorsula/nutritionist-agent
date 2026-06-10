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
    error_handler
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def start_bot():
    """
    Запуск Telegram бота
    """
    # Получаем токен из переменных окружения
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

    logger.info("Запуск Telegram бота...")

    # Создаём приложение
    application = Application.builder().token(token).build()

    # Регистрируем команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))

    # Регистрируем обработчики сообщений
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO, handle_photo_message)
    )
    application.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message)
    )

    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    logger.info("Бот запущен и ожидает сообщений...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    start_bot()
