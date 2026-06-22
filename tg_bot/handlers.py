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


async def _ensure_registered(update: Update):
    """
    Проверяет регистрацию клиента по telegram_id.
    Если клиент не найден — отправляет инструкцию и возвращает None.
    """
    telegram_id = update.effective_user.id
    client = get_client_by_telegram_id(telegram_id)
    if not client:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы в системе.\n"
            "Используйте /start для получения инструкций."
        )
        return None
    return client


async def _dispatch_to_router(
    update: Update,
    client,
    message: str,
    message_type: str,
    metadata: dict,
) -> None:
    """
    Единая обработка для текста/фото/голоса:
    вызов route_message() и отправка результата (или ошибки) пользователю.

    Бинарь (фото/аудио) кладётся в metadata вызывающей стороной по контракту:
      фото:   metadata['image_bytes'], metadata['mime_type']
      голос:  metadata['audio_bytes'], metadata['audio_name']
    """
    telegram_id = update.effective_user.id

    try:
        result = route_message(
            user_id=str(client.user_id),
            message=message,
            channel="telegram",
            message_type=message_type,
            metadata=metadata,
        )

        if result.get("success"):
            response_text = result.get("message", "Сообщение обработано")
            await _send_long_message(update, response_text)
            logger.info(
                f"Ответ отправлен telegram_id={telegram_id} "
                f"(type={message_type}, agent={result.get('agent_used')})"
            )
        else:
            error_type = result.get("error")
            error_message = result.get("message", "Произошла ошибка")

            logger.error(
                f"Ошибка роутера: {error_type}, telegram_id={telegram_id}, type={message_type}"
            )

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
        logger.exception(
            f"Ошибка обработки сообщения telegram_id={telegram_id} (type={message_type}): {e}"
        )
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже или обратитесь к нутрициологу."
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка текстовых сообщений.
    Перенаправляет в agents.route_message() (message_type='text').
    """
    telegram_id = update.effective_user.id
    username = update.effective_user.username or "unknown"

    logger.info(f"Текстовое сообщение от telegram_id={telegram_id}, username={username}")

    client = await _ensure_registered(update)
    if not client:
        return

    await update.message.chat.send_action("typing")

    await _dispatch_to_router(
        update,
        client,
        message=update.message.text,
        message_type="text",
        metadata={
            "telegram_id": telegram_id,
            "username": username,
            "message_id": update.message.message_id,
        },
    )


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка фото еды.
    Скачивает фото наибольшего размера → bytes → vision_agent через граф.
    Подпись к фото (caption) передаётся как message.
    """
    telegram_id = update.effective_user.id
    username = update.effective_user.username or "unknown"

    logger.info(f"Фото от telegram_id={telegram_id}")

    client = await _ensure_registered(update)
    if not client:
        return

    await update.message.chat.send_action("typing")

    # Скачиваем фото наибольшего размера (последний элемент массива)
    try:
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        image_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        logger.exception(f"Не удалось скачать фото telegram_id={telegram_id}: {e}")
        await update.message.reply_text(
            "❌ Не удалось загрузить фото. Попробуйте отправить ещё раз."
        )
        return

    caption = update.message.caption or ""

    await _dispatch_to_router(
        update,
        client,
        message=caption,
        message_type="photo",
        metadata={
            "telegram_id": telegram_id,
            "username": username,
            "message_id": update.message.message_id,
            "image_bytes": image_bytes,
            "mime_type": "image/jpeg",
        },
    )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка голосовых сообщений.
    Скачивает .ogg → bytes → передаёт в граф; транскрипцию (Whisper)
    выполняет оркестратор в узле ingest. Хендлер только доставляет байты.
    """
    telegram_id = update.effective_user.id
    username = update.effective_user.username or "unknown"

    logger.info(f"Голосовое от telegram_id={telegram_id}")

    client = await _ensure_registered(update)
    if not client:
        return

    await update.message.chat.send_action("typing")

    # Голос (voice) или аудиофайл (audio) — берём то, что пришло
    media = update.message.voice or update.message.audio
    if media is None:
        await update.message.reply_text(
            "❌ Не удалось распознать аудио. Попробуйте записать голосовое ещё раз."
        )
        return

    try:
        tg_file = await media.get_file()
        audio_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        logger.exception(f"Не удалось скачать аудио telegram_id={telegram_id}: {e}")
        await update.message.reply_text(
            "❌ Не удалось загрузить голосовое. Попробуйте отправить ещё раз."
        )
        return

    # Имя файла с расширением — Whisper определяет формат по нему
    audio_name = getattr(media, "file_name", None) or "voice.ogg"

    await _dispatch_to_router(
        update,
        client,
        message="",
        message_type="voice",
        metadata={
            "telegram_id": telegram_id,
            "username": username,
            "message_id": update.message.message_id,
            "audio_bytes": audio_bytes,
            "audio_name": audio_name,
        },
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
