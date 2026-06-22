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
# СЕМАНТИЧЕСКИЙ ПОИСК
# ========================================

def search_knowledge_base(
    query: str,
    match_count: int = 5,
    similarity_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Ищет релевантные чанки в базе знаний нутрициолога.

    Args:
        query: Текст запроса (например, продукт для проверки сочетаемости)
        match_count: Сколько чанков вернуть
        similarity_threshold: Минимальная cosine-близость (0..1), 0 = без фильтра

    Returns:
        Список чанков:
        [{"id", "document_id", "chunk_index", "chunk_text", "source", "similarity"}, ...]
        Пустой список при ошибке или отсутствии совпадений.
    """
    try:
        embedding = get_embedding(query)
        results = queries.search_knowledge_base(
            query_embedding=embedding,
            match_count=match_count,
            similarity_threshold=similarity_threshold,
        )
        logger.info(
            f"search_knowledge_base('{query[:40]}...'): найдено {len(results)} чанков"
        )
        return results

    except Exception as e:
        logger.error(f"search_knowledge_base error: {e}")
        return []


def search_client_documents(
    query: str,
    client_id: str,
    match_count: int = 5,
    similarity_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Ищет релевантные чанки в документах конкретного клиента.

    Изоляция по client_id выполняется на уровне БД (RPC match_client_documents).

    Args:
        query: Текст запроса (например, вопрос клиента про свои анализы)
        client_id: UUID клиента
        match_count: Сколько чанков вернуть
        similarity_threshold: Минимальная cosine-близость (0..1)

    Returns:
        Список чанков:
        [{"id", "document_id", "chunk_index", "chunk_text", "similarity"}, ...]
        Пустой список при ошибке или отсутствии совпадений.
    """
    try:
        embedding = get_embedding(query)
        results = queries.search_client_documents(
            query_embedding=embedding,
            client_id=client_id,
            match_count=match_count,
            similarity_threshold=similarity_threshold,
        )
        logger.info(
            f"search_client_documents(client={client_id}, '{query[:40]}...'): "
            f"найдено {len(results)} чанков"
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
