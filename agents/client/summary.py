"""
Rolling-summary — скользящая сводка диалога клиента (долговременная память).

Вместо жёсткого окна «последние 10 реплик» агент дополнительно получает краткую
сводку прошлых разговоров. Сводка обновляется по схеме summary-буфера: каждые
SUMMARY_EVERY новых сообщений старые сворачиваются в обновлённую сводку.

- build_rolling_summary(prev, msgs) — чистая функция: prev-сводка + новые реплики → новая сводка (LLM).
- update_rolling_summary(state)     — оркестрация: счётчик → решение → запись в clients.

Хранение: clients.conversation_summary / summary_message_count (миграция 009).
LLM: дешёвый (task_type='dialog').
"""

import logging
from typing import Any, Dict, List

from utils.llm import call_llm
from prompts import load_prompt

logger = logging.getLogger(__name__)

SUMMARY_EVERY = 10
"""Порог: обновлять сводку каждые N новых сообщений диалога."""

RECENT_FETCH_CAP = 40
"""Максимум реплик, поднимаемых для одного обновления сводки (стоимость/латентность)."""

MAX_SUMMARY_CHARS = 1500
"""Ограничение длины сводки (держим компактной для промпта)."""


def build_rolling_summary(previous_summary: str, new_messages: List[str]) -> str:
    """Строит обновлённую сводку из предыдущей + новых реплик (LLM). При сбое — возвращает prev."""
    if not new_messages:
        return previous_summary or ""

    user_content = (
        f"ПРЕДЫДУЩАЯ СВОДКА:\n{previous_summary or '(пусто)'}\n\n"
        f"НОВЫЕ РЕПЛИКИ:\n" + "\n".join(new_messages)
    )
    try:
        response = call_llm(
            task_type="dialog",
            messages=[
                {"role": "system", "content": load_prompt("system/client_summary")},
                {"role": "user", "content": user_content},
            ],
        )
        summary = (response.get("content") or "").strip()
        return summary[:MAX_SUMMARY_CHARS] if summary else (previous_summary or "")
    except Exception as e:
        logger.warning(f"build_rolling_summary failed: {e}")
        return previous_summary or ""


def update_rolling_summary(state: Dict[str, Any]) -> None:
    """
    Обновляет сводку клиента, если накопилось ≥ SUMMARY_EVERY новых сообщений.

    Вызывается best-effort после сохранения диалога (save_to_db). Никогда не бросает.
    """
    from database import queries

    client_id = state.get("client_id")
    client = state.get("client") or {}
    if not client_id:
        return

    prev_summary = client.get("conversation_summary") or ""
    prev_count = client.get("summary_message_count") or 0

    try:
        total = queries.count_client_dialog_messages(client_id)
    except Exception as e:
        logger.warning(f"update_rolling_summary: count failed: {e}")
        return

    if total - prev_count < SUMMARY_EVERY:
        return

    delta = min(total - prev_count, RECENT_FETCH_CAP)
    try:
        rows = queries.get_conversations(
            client_id=client_id, limit=delta, conversation_type="client_dialog"
        )
    except Exception as e:
        logger.warning(f"update_rolling_summary: fetch failed: {e}")
        return

    # get_conversations отдаёт свежие сверху → разворачиваем в хронологию
    msgs: List[str] = []
    for row in reversed(rows or []):
        text = (row.get("message_text") or "").strip()
        if not text:
            continue
        who = "Клиент" if row.get("role") == "client" else "Ассистент"
        msgs.append(f"{who}: {text}")

    if not msgs:
        return

    new_summary = build_rolling_summary(prev_summary, msgs)
    if new_summary and new_summary != prev_summary:
        try:
            queries.update_conversation_summary(client_id, new_summary, total)
            logger.info(f"Rolling summary updated for client {client_id} (count={total})")
        except Exception as e:
            logger.warning(f"update_rolling_summary: save failed: {e}")
