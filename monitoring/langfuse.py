"""
LangFuse трейсинг вызовов LLM (Этап 9).

Единая точка трейсинга: подключается в utils/llm.call_llm(), поэтому все агенты
(клиент и нутрициолог) получают наблюдаемость автоматически.

Принцип безопасности (КРИТИЧНО):
- Если SDK `langfuse` не установлен ИЛИ нет ключей (LANGFUSE_PUBLIC_KEY /
  LANGFUSE_SECRET_KEY) — модуль работает как no-op.
- Любая ошибка трейсинга подавляется и логируется: трейсинг НИКОГДА не должен
  ронять основной вызов LLM.

Ключи окружения:
- LANGFUSE_PUBLIC_KEY
- LANGFUSE_SECRET_KEY
- LANGFUSE_HOST (опц., по умолчанию https://cloud.langfuse.com)
"""

import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Ленивый синглтон клиента: None — не инициализирован, False — недоступен.
_client: Any = None


def _get_client():
    """
    Ленивая инициализация клиента LangFuse.
    Возвращает клиент или None (если SDK не установлен / нет ключей / ошибка).
    """
    global _client

    if _client is not None:
        return _client or None  # _client может быть False (недоступен)

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        logger.debug("LangFuse отключён: нет LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY")
        _client = False
        return None

    try:
        from langfuse import Langfuse
    except ImportError:
        logger.debug("LangFuse отключён: пакет langfuse не установлен")
        _client = False
        return None

    try:
        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        logger.info("LangFuse инициализирован")
        return _client
    except Exception as e:
        logger.warning(f"Не удалось инициализировать LangFuse: {e}")
        _client = False
        return None


def is_enabled() -> bool:
    """True, если трейсинг активен (SDK установлен и ключи заданы)."""
    return _get_client() is not None


def trace_llm_call(
    *,
    task_type: Optional[str],
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    response: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    latency_ms: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Отправляет трейс вызова LLM в LangFuse (generation).

    No-op, если трейсинг отключён. Никогда не выбрасывает исключение.

    Args:
        task_type: тип задачи (dialog/analysis/vision/...), может быть None
        provider: провайдер (groq/claude/gemini)
        model: модель
        messages: входные сообщения (формат OpenAI)
        response: результат call_llm (content/usage/...) при успехе
        error: текст ошибки при неудаче
        latency_ms: латентность в мс
        metadata: дополнительные поля
    """
    client = _get_client()
    if client is None:
        return

    try:
        usage = (response or {}).get("usage") or {}
        meta = {
            "provider": provider,
            "task_type": task_type,
            "latency_ms": latency_ms,
            **(metadata or {}),
        }
        if error:
            meta["error"] = error

        client.generation(
            name=f"llm:{task_type or provider}",
            model=model,
            input=messages,
            output=(response or {}).get("content") if not error else None,
            usage={
                "input": usage.get("input_tokens"),
                "output": usage.get("output_tokens"),
                "total": usage.get("total_tokens"),
            },
            metadata=meta,
            level="ERROR" if error else "DEFAULT",
            status_message=error,
        )
    except Exception as e:
        # Трейсинг не должен ломать основной поток
        logger.debug(f"LangFuse trace failed (подавлено): {e}")


def flush() -> None:
    """Сбрасывает буфер событий (для коротко живущих процессов/скриптов)."""
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:
        logger.debug(f"LangFuse flush failed (подавлено): {e}")


def _reset_for_tests() -> None:
    """Сброс синглтона (только для тестов)."""
    global _client
    _client = None
