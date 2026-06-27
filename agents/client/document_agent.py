"""
Document Agent — приём документов клиента (PDF/текст), напр. из Telegram.

Поток (message_type='document', metadata: file_bytes + mime_type + file_name):
1. extract_text (PDF/текст);
2. document_metadata (source='client_telegram') + векторизация в client_documents (RAG);
3. извлечение числовых показателей в lab_results (best-effort);
4. тёплое подтверждение клиенту.

Скан-картинки без текстового слоя сюда не подходят — для них фото-путь (vision).
"""

import logging
from typing import Any, Dict, List, Optional

from utils.ingestion import extract_text, ingest_into_client_documents
from utils.labs import extract_labs_from_text
from .state import ClientState

logger = logging.getLogger(__name__)


def document_node(state: ClientState) -> ClientState:
    """Узел обработки документа клиента. Устанавливает agent_response, agent_used, saved_labs."""
    from database import queries
    from database.models import DocumentMetadata

    state['agent_used'] = 'document_agent'

    metadata = state.get('metadata') or {}
    file_bytes = metadata.get('file_bytes')
    mime = metadata.get('mime_type') or ''
    name = metadata.get('file_name') or 'document'

    if not file_bytes:
        state['agent_response'] = "Файл не дошёл 🙈 Пришли его, пожалуйста, ещё раз."
        return state

    # 1. Извлечение текста
    try:
        text = extract_text(file_bytes, mime, name)
    except ValueError:
        state['agent_response'] = (
            "Такой тип файла я пока не читаю 🙈 Пришли PDF или текст — "
            "или напиши показатели прямо сообщением (например, «холестерин 5.2»)."
        )
        return state
    except Exception as e:
        logger.error(f"Document extract error: {e}", exc_info=True)
        state['agent_response'] = "Не получилось обработать файл 🙈 Попробуй прислать ещё раз."
        state['agent_used'] = 'document_agent_error'
        state['error'] = str(e)
        return state

    if not text.strip():
        state['agent_response'] = (
            "Не удалось извлечь текст из документа 🙈 Если это скан-картинка, "
            "пришли его как фото — распознаю как изображение."
        )
        return state

    client_id = state['client_id']

    # 2. Метаданные + векторизация (RAG) — best-effort
    doc_id: Optional[str] = None
    try:
        rows = queries.insert_document_metadata(
            DocumentMetadata(
                source='client_telegram',
                client_id=client_id,
                document_type='client_document',
                file_name=name,
                mime_type=mime or None,
            )
        )
        doc_id = (rows or [{}])[0].get('id')
        if doc_id:
            ingest_into_client_documents(client_id, doc_id, text)
    except Exception as e:
        logger.warning(f"Document ingest failed: {e}")

    # 3. Числовые показатели → lab_results — best-effort
    saved: List[Dict[str, Any]] = []
    try:
        for lab in extract_labs_from_text(text):
            queries.insert_lab_result(
                client_id=client_id,
                indicator=lab['indicator'],
                value=lab['value'],
                unit=lab.get('unit'),
                source='client_pdf',
                document_id=doc_id,
            )
            saved.append(lab)
    except Exception as e:
        logger.warning(f"Document lab extraction failed: {e}")

    state['saved_labs'] = saved
    state['intake_subtype'] = 'document'

    if state.get('ack_only'):
        state['agent_response'] = ''
        return state

    # 4. Ответ клиенту
    parts = ["Документ получил и сохранил в твою карту ✅"]
    if saved:
        recorded = ", ".join(
            f"{l['indicator']} {l['value']}{(' ' + l['unit']) if l.get('unit') else ''}" for l in saved
        )
        parts.append(f"Распознал показатели: {recorded}")
    parts.append("Нутрициолог его увидит.")
    state['agent_response'] = "\n".join(parts)
    return state
