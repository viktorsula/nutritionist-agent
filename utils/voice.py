"""
Voice — транскрипция голосовых сообщений через OpenAI Whisper (Этап 6)

Назначение:
- Голосовое сообщение клиента (Telegram .ogg / .mp3 / .wav) → текст (UC-6).
- Дальше текст идёт в обычный роутинг агентов.

Архитектура:
1. transcribe_voice(audio_bytes, file_name) → текст

Ключи: OPENAI_API_KEY из os.environ.get (НИКОГДА load_dotenv).
Модель: whisper-1.

Примечание: Telegram присылает голос в формате OGG/Opus — Whisper его принимает.

TODO v1.1:
- Определение языка и возврат вместе с текстом
- Обработка длинных аудио (нарезка)
"""

import os
import io
import logging
from typing import Optional

# Импорт SDK (устанавливается через requirements.txt)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)


# ========================================
# КОНФИГУРАЦИЯ
# ========================================

WHISPER_MODEL = "whisper-1"
"""Модель транскрипции OpenAI."""


# ========================================
# ТРАНСКРИПЦИЯ
# ========================================

def transcribe_voice(
    audio_bytes: bytes,
    file_name: str = "voice.ogg",
    language: Optional[str] = None,
) -> str:
    """
    Транскрибирует голосовое сообщение в текст через OpenAI Whisper.

    Args:
        audio_bytes: Бинарное содержимое аудиофайла (ogg/mp3/wav/m4a)
        file_name: Имя файла с расширением (важно — Whisper определяет формат по нему)
        language: ISO-код языка ('ru', 'en', ...) для подсказки; None = автоопределение

    Returns:
        Распознанный текст (пустая строка, если речи нет)

    Raises:
        RuntimeError: Если SDK не установлен или нет OPENAI_API_KEY
        ValueError: Если аудио пустое
    """
    if OpenAI is None:
        raise RuntimeError(
            "OpenAI SDK не установлен. Установите: pip install openai"
        )

    if not audio_bytes:
        raise ValueError("transcribe_voice(): передано пустое аудио")

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY не найден в переменных окружения. "
            "Добавьте в .env или Render Environment Variables"
        )

    try:
        client = OpenAI(api_key=api_key)

        # Whisper определяет формат по имени файла → задаём .name у потока
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = file_name

        params = {
            "model": WHISPER_MODEL,
            "file": audio_file,
        }
        if language:
            params["language"] = language

        response = client.audio.transcriptions.create(**params)

        text = getattr(response, "text", "") or ""
        logger.info(f"transcribe_voice: распознано {len(text)} символов из {file_name}")
        return text.strip()

    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        raise RuntimeError(f"Ошибка транскрипции голоса: {str(e)}") from e
