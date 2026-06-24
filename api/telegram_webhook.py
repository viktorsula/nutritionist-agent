"""
Telegram webhook — интеграция PTB-приложения в FastAPI (вариант «б»).

Бот живёт внутри FastAPI-процесса (не отдельный воркер): на старте приложения
инициализируем PTB Application и (если задан URL) ставим webhook; входящие
апдейты приходят в маршрут /telegram/webhook и отдаются application.process_update.

Безопасность: Telegram шлёт заголовок X-Telegram-Bot-Api-Secret-Token, если webhook
поставлен с secret_token — сверяем его с TELEGRAM_WEBHOOK_SECRET.

ИНЕРТНОСТЬ: без TELEGRAM_BOT_TOKEN ничего не запускается (маршрут отдаёт 503), чтобы
не влиять на текущий прод. Ошибки старта не роняют API (бот опционален).

ENV:
- TELEGRAM_BOT_TOKEN     — токен бота (без него интеграция выключена);
- TELEGRAM_WEBHOOK_URL   — полный публичный URL маршрута (если задан — webhook ставится автоматически);
- TELEGRAM_WEBHOOK_SECRET — секрет для проверки заголовка (рекомендуется).
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_application = None  # PTB Application | None


async def startup_telegram() -> None:
    """Инициализирует PTB Application и (опционально) ставит webhook. Без токена — no-op."""
    global _application

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.info("Telegram webhook: TELEGRAM_BOT_TOKEN не задан — интеграция выключена")
        return

    try:
        from tg_bot.bot import build_application

        application = build_application(token)
        await application.initialize()
        await application.start()
        _application = application

        webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL")
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if webhook_url:
            await application.bot.set_webhook(
                url=webhook_url,
                secret_token=secret or None,
                allowed_updates=["message"],
            )
            logger.info(f"Telegram webhook установлен: {webhook_url}")
        else:
            logger.info(
                "Telegram webhook: приложение запущено, но TELEGRAM_WEBHOOK_URL не задан — "
                "установите webhook вручную (setWebhook)"
            )
    except Exception as e:
        logger.error(f"Telegram startup failed: {e}", exc_info=True)
        _application = None


async def shutdown_telegram() -> None:
    """Останавливает PTB Application при остановке приложения."""
    global _application
    if _application is None:
        return
    try:
        await _application.stop()
        await _application.shutdown()
    except Exception as e:
        logger.warning(f"Telegram shutdown error: {e}")
    finally:
        _application = None


async def process_webhook_update(data: Dict[str, Any]) -> bool:
    """Обрабатывает один Telegram-апдейт. False, если интеграция не настроена."""
    if _application is None:
        return False
    from telegram import Update

    update = Update.de_json(data, _application.bot)
    await _application.process_update(update)
    return True


def webhook_secret_ok(header_value: Optional[str]) -> bool:
    """Сверяет секрет из заголовка. Если секрет не задан в env — не проверяем."""
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not secret:
        return True
    return header_value == secret


def is_configured() -> bool:
    """True, если PTB-приложение инициализировано (бот активен)."""
    return _application is not None


def get_bot():
    """PTB Bot активного приложения (для исходящих сообщений) или None."""
    return _application.bot if _application is not None else None
