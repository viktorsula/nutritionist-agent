"""
Ingestion — наполнение векторной памяти (Блок 2, keystone RAG)

Превращает документ (PDF/текст) в чанки с эмбеддингами и пишет их в pgvector:
- knowledge_base   — библиотека нутрициолога (труды, методички, научные работы)
- client_documents — документы конкретного клиента (анализы, выписки)

Конвейер:
    extract_text → chunk_text → get_embedding (ada-002) → insert_*_chunk

Это ядро БЕЗ привязки к каналу/хранилищу: на вход даётся уже готовый текст (или
байты+mime), document_id и (для клиента) client_id. Скачивание из Storage, создание
document_metadata и эндпоинты — слой выше (next step), он переиспользует это ядро.

Ключи: OPENAI_API_KEY берётся внутри utils.knowledge.get_embedding (os.environ,
НИКОГДА load_dotenv).
"""

import io
import logging
import re
from typing import List, Optional

from utils.knowledge import get_embedding
from database import queries
from database.models import KnowledgeBaseChunk, ClientDocumentChunk

logger = logging.getLogger(__name__)


# ========================================
# КОНФИГУРАЦИЯ ЧАНКИНГА
# ========================================

DEFAULT_CHUNK_SIZE = 1000
"""Целевой размер чанка в символах (~250 токенов — хорошая гранулярность для поиска)."""

DEFAULT_OVERLAP = 150
"""Перекрытие соседних чанков в символах (контекст не рвётся на границе)."""


# ========================================
# 1. ИЗВЛЕЧЕНИЕ ТЕКСТА
# ========================================

def extract_text(file_bytes: bytes, mime_type: str = "", file_name: str = "") -> str:
    """
    Извлекает текст из файла по mime-типу/расширению.

    Поддержка: PDF (pypdf), text/plain, markdown. Неподдерживаемый тип → ValueError.

    Args:
        file_bytes: Содержимое файла
        mime_type: MIME (например, 'application/pdf', 'text/plain')
        file_name: Имя файла (используется как fallback по расширению)

    Returns:
        Извлечённый текст (может быть пустым, если документ без текстового слоя).
    """
    if not file_bytes:
        return ""

    name = (file_name or "").lower()
    mime = (mime_type or "").lower()

    is_pdf = "pdf" in mime or name.endswith(".pdf")
    is_text = (
        mime.startswith("text/")
        or name.endswith((".txt", ".md", ".markdown", ".csv"))
    )

    if is_pdf:
        return _extract_pdf_text(file_bytes)
    if is_text:
        return file_bytes.decode("utf-8", errors="replace")

    raise ValueError(
        f"extract_text: неподдерживаемый тип документа (mime={mime_type!r}, file={file_name!r}). "
        "Поддерживаются PDF и текстовые форматы."
    )


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Извлекает текст из PDF через pypdf (постранично)."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf не установлен. Установите: pip install pypdf") from e

    reader = PdfReader(io.BytesIO(file_bytes))
    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:  # отдельная страница не должна валить весь документ
            logger.warning(f"PDF: не удалось извлечь текст со страницы: {e}")
    return "\n\n".join(p for p in pages if p.strip())


# ========================================
# 2. ЧАНКИНГ
# ========================================

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[str]:
    """
    Режет текст на перекрывающиеся чанки фиксированного размера (по символам).

    Перенос строк/пробелы нормализуются. Окно сдвигается на (chunk_size - overlap).
    Детерминированно (важно для тестов). Пустые/пробельные чанки отбрасываются.

    TODO v1.1: резка по границам предложений/абзацев (semantic chunking).
    """
    if not text or not text.strip():
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size должен быть > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap должен быть в диапазоне [0, chunk_size)")

    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= chunk_size:
        return [normalized]

    step = chunk_size - overlap
    chunks: List[str] = []
    for start in range(0, len(normalized), step):
        piece = normalized[start:start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        if start + chunk_size >= len(normalized):
            break
    return chunks


# ========================================
# 3. ЗАПИСЬ В ВЕКТОРНУЮ ПАМЯТЬ
# ========================================

def ingest_into_knowledge_base(
    document_id: str,
    text: str,
    source: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> int:
    """
    Чанкит текст и пишет его в knowledge_base (библиотека нутрициолога).

    Args:
        document_id: UUID документа (из document_metadata)
        text: Уже извлечённый текст документа
        source: Метка источника (например, имя труда/издание)

    Returns:
        Количество записанных чанков.
    """
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        logger.info(f"ingest_into_knowledge_base: документ {document_id} без текста — 0 чанков")
        return 0

    written = 0
    for index, chunk in enumerate(chunks):
        embedding = get_embedding(chunk)
        queries.insert_knowledge_base_chunk(
            KnowledgeBaseChunk(
                document_id=document_id,
                chunk_index=index,
                chunk_text=chunk,
                embedding=embedding,
                source=source,
            )
        )
        written += 1

    logger.info(f"ingest_into_knowledge_base: документ {document_id} → {written} чанков")
    return written


def ingest_into_client_documents(
    client_id: str,
    document_id: str,
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> int:
    """
    Чанкит текст и пишет его в client_documents (документы конкретного клиента).

    Изоляция по client_id — на уровне строки чанка и RLS/RPC при чтении.

    Args:
        client_id: UUID клиента
        document_id: UUID документа (из document_metadata)
        text: Уже извлечённый текст документа

    Returns:
        Количество записанных чанков.
    """
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        logger.info(f"ingest_into_client_documents: документ {document_id} без текста — 0 чанков")
        return 0

    written = 0
    for index, chunk in enumerate(chunks):
        embedding = get_embedding(chunk)
        queries.insert_client_document_chunk(
            ClientDocumentChunk(
                client_id=client_id,
                document_id=document_id,
                chunk_index=index,
                chunk_text=chunk,
                embedding=embedding,
            )
        )
        written += 1

    logger.info(
        f"ingest_into_client_documents: клиент {client_id}, документ {document_id} "
        f"→ {written} чанков"
    )
    return written
