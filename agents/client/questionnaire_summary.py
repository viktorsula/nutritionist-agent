"""
Саммари анкеты онбординга (миграция 017) — компактная выжимка для системного промпта
LLM-оркестратора клиента, генерируется ОДИН РАЗ при отправке анкеты (первичной или
повторной), а не на каждый ход диалога.

build_questionnaire_summary(profile) — чистая функция: профиль клиента → саммари (LLM).
Вызывается из api/main.py::questionnaire_summary при POST /questionnaire-summary.
"""

import logging
from typing import Any, Dict, Optional

from utils.llm import call_llm
from prompts import load_prompt
from .questionnaire_context import build_summary_input

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 800
"""Ограничение длины саммари (держим компактным для промпта)."""


def build_questionnaire_summary(profile: Dict[str, Any]) -> Optional[str]:
    """
    Строит компактное саммари анкеты (LLM, task_type='summary'). При пустых данных или
    сбое LLM — None (вызывающий откатывается на построчный формат questionnaire_json).
    """
    input_text = build_summary_input(profile)
    if not input_text.strip():
        return None

    try:
        response = call_llm(
            task_type="summary",
            messages=[
                {"role": "system", "content": load_prompt("system/questionnaire_summary")},
                {"role": "user", "content": input_text},
            ],
        )
        summary = (response.get("content") or "").strip()
        return summary[:MAX_SUMMARY_CHARS] if summary else None
    except Exception as e:
        logger.warning(f"build_questionnaire_summary failed: {e}")
        return None
