"""
Labs — извлечение числовых показателей анализов из текста документа (Шаг C).

Используется при загрузке PDF/текстовых анализов клиента: из извлечённого текста
дешёвым LLM выделяем показатели (indicator/value/unit) для записи в lab_results.

Это best-effort: модель может ошибиться (например, принять референсный диапазон за
значение), поэтому источник помечается отдельно (source='client_pdf'), а нутрициолог
сверяет. Парсинг значения — терпимый к запятой ('5,2' → 5.2).

LLM: дешёвый (task_type='dialog'); ключи берёт utils.llm (os.environ).
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from utils.llm import call_llm
from prompts import load_prompt

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 6000
"""Ограничение длины текста для извлечения (стоимость/латентность)."""


def extract_labs_from_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> List[Dict[str, Any]]:
    """
    Извлекает показатели анализов из текста через дешёвый LLM.

    Returns:
        Список [{"indicator": str, "value": float, "unit": str|None}, ...].
        Пустой список при отсутствии/ошибке (best-effort, не бросает).
    """
    text = (text or "").strip()
    if not text:
        return []

    try:
        response = call_llm(
            task_type="dialog",
            messages=[
                {"role": "system", "content": load_prompt("system/labs_extraction")},
                {"role": "user", "content": text[:max_chars]},
            ],
        )
        parsed = _safe_parse_json(response.get("content", "")) or {}
    except Exception as e:
        logger.warning(f"extract_labs_from_text failed: {e}")
        return []

    result: List[Dict[str, Any]] = []
    for item in parsed.get("labs", []) or []:
        if not isinstance(item, dict):
            continue
        indicator = str(item.get("indicator") or "").strip().lower()
        value = parse_lab_value(item.get("value"))
        if not indicator or value is None:
            continue
        unit = (str(item.get("unit")).strip() or None) if item.get("unit") else None
        result.append({"indicator": indicator, "value": value, "unit": unit})
    return result


def parse_lab_value(value: Any) -> Optional[float]:
    """Приводит значение к float (поддержка '5,2' и '5.2'); иначе None."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


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
