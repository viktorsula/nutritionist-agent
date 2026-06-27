"""
Intake — определитель темы входящего «хода» клиента (Фаза 1).

Ход (turn) = одна или несколько частей: текст / фото / голос / PDF (за окно сбора —
Фаза 2; пока ход может состоять из одной части). Определитель разбивает ход на
СЕГМЕНТЫ по 3 верхнеуровневым веткам (intake | profile | advice, см. branches.py)
и решает, нужен ли содержательный ответ (ack | answer). Под-тип хранения внутри
intake (куда сохранять) определяется позже, детерминированно, в обработчике.

Контракт результата:
    {
      "segments": [
        {"branch": "intake | profile | advice",
         "parts": [<индексы частей хода>],
         "needs_answer": "ack" | "answer"}
      ],
      "needs_answer": "ack" | "answer"   # агрегат по ходу: answer, если есть хоть один answer
    }

Инструкция для LLM: prompts/system/intake_determiner.md (редактируемая).
LLM: дешёвый классификатор (task_type='dialog').
"""

import json
import logging
from typing import Any, Dict, List, Optional

from utils.llm import call_llm
from prompts import load_prompt
from .branches import (
    ACK,
    ANSWER,
    CLARIFY,
    FALLBACK_BRANCH,
    default_answer,
    is_valid_branch,
)

logger = logging.getLogger(__name__)

# Человекочитаемые подписи типа части для рендера хода в промпт.
_HUMAN_KIND = {
    "text": "текст",
    "photo": "фото",
    "voice": "голос",
    "document": "документ/PDF",
}


def build_turn_view(parts: List[Dict[str, Any]]) -> str:
    """
    Рендерит части хода в нумерованный список для определителя.

    Каждая часть: {"kind": "text|photo|voice|document", "text": str,
                   "image_kind": "food|lab_document|fridge|other" (опц., для фото)}.
    """
    lines: List[str] = []
    for i, part in enumerate(parts):
        kind = part.get("kind", "text")
        human = _HUMAN_KIND.get(kind, kind)
        if kind == "photo" and part.get("image_kind"):
            human = f"фото: распознано как {part['image_kind']}"
        text = (part.get("text") or "").strip() or "—"
        lines.append(f"Часть {i} [{human}]: {text}")
    return "\n".join(lines)


def determine_turn(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Определяет сегменты хода и потребность в ответе.

    Best-effort: при сбое LLM/парсинга → один сегмент dialog/answer (безопасно —
    лучше ответить, чем молча «принять» возможный вопрос).
    """
    if not parts:
        return {"segments": [], "needs_answer": ANSWER}

    n = len(parts)
    view = build_turn_view(parts)

    try:
        response = call_llm(
            task_type="dialog",
            messages=[
                {"role": "system", "content": load_prompt("system/intake_determiner")},
                {"role": "user", "content": view},
            ],
        )
        parsed = _safe_parse_json(response.get("content", "")) or {}
    except Exception as e:
        logger.error(f"intake determiner failed: {e}")
        parsed = {}

    segments = _validate_segments(parsed.get("segments"), n)
    if not segments:
        # Не смогли разобрать ход (пусто/ошибка LLM) → не угадываем, спрашиваем клиента.
        segments = [{"branch": FALLBACK_BRANCH, "parts": list(range(n)), "needs_answer": CLARIFY}]

    needs_answer = _aggregate_needs(segments)
    return {"segments": segments, "needs_answer": needs_answer}


def _aggregate_needs(segments: List[Dict[str, Any]]) -> str:
    """Агрегат по ходу: answer > clarify > ack."""
    values = {s["needs_answer"] for s in segments}
    if ANSWER in values:
        return ANSWER
    if CLARIFY in values:
        return CLARIFY
    return ACK


def _validate_segments(raw: Any, n: int) -> List[Dict[str, Any]]:
    """Чистит вывод модели: валидные ветки, корректные индексы частей, ack|answer."""
    if not isinstance(raw, list):
        return []

    result: List[Dict[str, Any]] = []
    for seg in raw:
        if not isinstance(seg, dict):
            continue

        branch = seg.get("branch")
        if not is_valid_branch(branch):
            branch = FALLBACK_BRANCH

        parts = [p for p in (seg.get("parts") or []) if isinstance(p, int) and 0 <= p < n]
        if not parts:
            parts = list(range(n))

        needs = seg.get("needs_answer")
        if needs not in (ACK, ANSWER, CLARIFY):
            needs = default_answer(branch)

        result.append({"branch": branch, "parts": parts, "needs_answer": needs})

    return result


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Извлекает JSON из ответа модели (со снятием markdown-обёртки)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None
