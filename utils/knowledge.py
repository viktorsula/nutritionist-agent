"""
Knowledge — семантический поиск по pgvector (Этап 6)

Назначение:
- Считать эмбеддинги текста через OpenAI text-embedding-ada-002 (1536).
- Искать релевантные чанки в базе знаний нутрициолога (knowledge_base).
- Искать релевантные чанки в документах конкретного клиента (client_documents).

Поиск выполняется RPC-функциями в Supabase (миграция 002_add_vector_search.sql):
- match_knowledge_base
- match_client_documents

Архитектура:
1. get_embedding(text) → вектор 1536 (OpenAI ada-002)
2. search_knowledge_base(query) → чанки базы знаний с similarity
3. search_client_documents(query, client_id) → чанки документов клиента

Ключи: OPENAI_API_KEY из os.environ.get (НИКОГДА load_dotenv).

TODO v1.1:
- Кэширование эмбеддингов частых запросов
- Гибридный поиск (вектор + полнотекст)
"""

import os
import logging
from typing import Any, Dict, List, Optional

# Импорт SDK (устанавливается через requirements.txt)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from database import queries

logger = logging.getLogger(__name__)


# ========================================
# КОНФИГУРАЦИЯ
# ========================================

EMBEDDING_MODEL = "text-embedding-ada-002"
"""Модель эмбеддингов. ada-002 → ровно 1536 измерений = схема БД vector(1536)."""

EMBEDDING_DIM = 1536
"""Ожидаемая размерность вектора (должна совпадать со схемой БД)."""


# ========================================
# ЭМБЕДДИНГИ
# ========================================

def get_embedding(text: str) -> List[float]:
    """
    Считает эмбеддинг текста через OpenAI text-embedding-ada-002.

    Args:
        text: Текст для векторизации (запрос или чанк документа)

    Returns:
        Список из 1536 float

    Raises:
        RuntimeError: Если SDK не установлен или нет OPENAI_API_KEY
        ValueError: Если текст пустой
    """
    if OpenAI is None:
        raise RuntimeError(
            "OpenAI SDK не установлен. Установите: pip install openai"
        )

    if not text or not text.strip():
        raise ValueError("get_embedding(): передан пустой текст")

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY не найден в переменных окружения. "
            "Добавьте в .env или Render Environment Variables"
        )

    try:
        client = OpenAI(api_key=api_key)
        # ada-002 принимает текст; переносы строк лучше схлопнуть
        cleaned = text.replace("\n", " ").strip()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=cleaned,
        )
        embedding = response.data[0].embedding

        if len(embedding) != EMBEDDING_DIM:
            logger.warning(
                f"Размерность эмбеддинга {len(embedding)} != ожидаемой {EMBEDDING_DIM}"
            )

        return embedding

    except Exception as e:
        logger.error(f"OpenAI embeddings error: {e}")
        raise RuntimeError(f"Ошибка получения эмбеддинга: {str(e)}") from e


# ========================================
# ПОРОГ РЕЛЕВАНТНОСТИ (P2-2)
# ========================================
# Раньше все вызовы шли с similarity_threshold=0.0 — то есть фильтра релевантности не было
# вообще: RPC возвращал match_count ближайших чанков ВСЕГДА, даже если ни один не имеет
# отношения к вопросу. На пустой/узкой базе знаний это давало модели заведомо посторонний
# контекст и провоцировало ответы «по мотивам» случайного документа.
#
# Значение подобрано под ada-002: у неё косинусная близость смещена вверх (даже несвязанные
# тексты дают ~0.7), поэтому осмысленная граница — около 0.75, а не 0.3-0.5 как у моделей
# с широким разбросом. Правится нутрициологом без кода — system_settings.rag_config.
DEFAULT_SIMILARITY_THRESHOLD = 0.75


def get_similarity_threshold() -> float:
    """
    Порог релевантности из system_settings.rag_config.similarity_threshold (P2-2).
    При отсутствии/ошибке — код-дефолт. Значение вне [0, 1] игнорируется.
    """
    try:
        cfg = queries.get_setting("rag_config")
        if isinstance(cfg, dict):
            value = cfg.get("similarity_threshold")
            # bool исключаем явно: в Python True — подкласс int, и JSON-значение `true`
            # прошло бы как порог 1.0, то есть «не находить вообще ничего» — молча.
            if isinstance(value, (int, float)) and not isinstance(value, bool) \
                    and 0.0 <= float(value) <= 1.0:
                return float(value)
    except Exception as e:
        logger.warning(f"rag_config недоступен, порог по умолчанию: {e}")
    return DEFAULT_SIMILARITY_THRESHOLD


# ========================================
# СЕМАНТИЧЕСКИЙ ПОИСК
# ========================================

def search_knowledge_base(
    query: str,
    match_count: int = 5,
    similarity_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Ищет релевантные чанки в базе знаний нутрициолога.

    Args:
        query: Текст запроса (например, продукт для проверки сочетаемости)
        match_count: Сколько чанков вернуть
        similarity_threshold: Минимальная cosine-близость (0..1). None (по умолчанию) —
            взять настроенный порог (см. get_similarity_threshold). Явный 0.0 отключает
            фильтр осознанно.

    Returns:
        Список чанков:
        [{"id", "document_id", "chunk_index", "chunk_text", "source", "similarity"}, ...]
        Пустой список при ошибке или отсутствии совпадений.
    """
    threshold = get_similarity_threshold() if similarity_threshold is None else similarity_threshold
    try:
        embedding = get_embedding(query)
        results = queries.search_knowledge_base(
            query_embedding=embedding,
            match_count=match_count,
            similarity_threshold=threshold,
        )
        logger.info(
            f"search_knowledge_base('{query[:40]}...'): найдено {len(results)} чанков "
            f"(порог {threshold})"
        )
        return results

    except Exception as e:
        logger.error(f"search_knowledge_base error: {e}")
        return []


def search_client_documents(
    query: str,
    client_id: str,
    match_count: int = 5,
    similarity_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Ищет релевантные чанки в документах конкретного клиента.

    Изоляция по client_id выполняется на уровне БД (RPC match_client_documents).

    Args:
        query: Текст запроса (например, вопрос клиента про свои анализы)
        client_id: UUID клиента
        match_count: Сколько чанков вернуть
        similarity_threshold: Минимальная cosine-близость (0..1). None (по умолчанию) —
            взять настроенный порог (см. get_similarity_threshold).

    Returns:
        Список чанков:
        [{"id", "document_id", "chunk_index", "chunk_text", "similarity"}, ...]
        Пустой список при ошибке или отсутствии совпадений.
    """
    threshold = get_similarity_threshold() if similarity_threshold is None else similarity_threshold
    try:
        embedding = get_embedding(query)
        results = queries.search_client_documents(
            query_embedding=embedding,
            client_id=client_id,
            match_count=match_count,
            similarity_threshold=threshold,
        )
        logger.info(
            f"search_client_documents(client={client_id}, '{query[:40]}...'): "
            f"найдено {len(results)} чанков (порог {threshold})"
        )
        return results

    except Exception as e:
        logger.error(f"search_client_documents error: {e}")
        return []


# ========================================
# ХЕЛПЕР: СБОРКА КОНТЕКСТА ДЛЯ LLM
# ========================================

def build_context_from_chunks(
    chunks: List[Dict[str, Any]],
    max_chars: int = 4000,
) -> str:
    """
    Собирает текстовый контекст из найденных чанков для передачи в LLM.

    Args:
        chunks: Результат search_knowledge_base / search_client_documents
        max_chars: Ограничение длины контекста

    Returns:
        Склеенный текст чанков (обрезанный до max_chars) или пустая строка.
    """
    if not chunks:
        return ""

    parts: List[str] = []
    total = 0

    for chunk in chunks:
        text = chunk.get("chunk_text", "")
        if not text:
            continue
        if total + len(text) > max_chars:
            parts.append(text[: max_chars - total])
            break
        parts.append(text)
        total += len(text)

    return "\n\n---\n\n".join(parts)
