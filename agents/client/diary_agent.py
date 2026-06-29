"""
Diary Agent — дневник: фиксация того, что клиент сообщает текстом

Обрабатывает текстовые сообщения-факты (не фото, не общий вопрос):
- приём пищи словами ("на обед была курица с рисом");
- вес ("вешу 82", "вес 81.5");
- самочувствие ("чувствую себя плохо, болит голова").

Поток:
1. Извлечь структуру одним LLM-вызовом (JSON): {kind, ingredients, weight_kg, wellbeing}.
2. Ветвление по kind:
   - weight    → запись в measurements + проверка алерта weight_increase;
   - wellbeing → событие bad_wellbeing + уведомление нутрициолога;
   - meal      → анализ состава против рациона + событие calories_logged;
   - other     → мягкий уточняющий ответ.
3. Тёплый ответ клиенту (dialog-LLM); предупреждения добавит format_response_node.

Промпт: prompts/client/diary_system.md
LLM: Groq llama-3.3-70b (task_type='dialog').
"""

import json
import logging
from typing import Any, Dict, List, Optional

from utils.llm import call_llm
from prompts import load_prompt
from .state import ClientState
from .food_analysis import resolve_meal_type
from .intake_schema import from_diary_extract
from .intake_store import persist_record
from .intake_present import present

logger = logging.getLogger(__name__)


# ==========================================
# УЗЕЛ LANGGRAPH
# ==========================================

def diary_node(state: ClientState) -> ClientState:
    """
    Узел дневника: классифицирует текстовый факт и фиксирует его.

    Устанавливает agent_response, agent_used, alerts, routing, llm_model.
    """
    state['agent_used'] = 'diary_agent'

    # 1. Извлечь структуру → канонический IntakeRecord (тип приёма резолвим тут).
    extracted = _extract(state)
    meal_type = resolve_meal_type(state.get('message', ''), extracted.get('meal_type'))
    record = from_diary_extract(extracted, meal_type=meal_type)

    # 2. Единая запись в БД + алерты (domain-слой). Возвращает под-тип захвата или None.
    subtype = persist_record(state, record)
    state['intake_subtype'] = subtype

    # 3. ack_only + успешный захват → тёплый ответ не нужен (заменит квитанция).
    #    При неудаче захвата (subtype None) строим поясняющий текст (clarify).
    if state.get('ack_only') and subtype is not None:
        state['agent_response'] = ''
        return state

    state['agent_response'] = present(state, record, prompt_name='client/diary_system')
    return state


# ==========================================
# ИЗВЛЕЧЕНИЕ СТРУКТУРЫ (LLM → JSON)
# ==========================================

def _extract(state: ClientState) -> Dict[str, Any]:
    """Извлекает структуру из сообщения клиента через LLM (с безопасным fallback)."""
    message = (state.get('message') or '').strip()
    if not message:
        return {"kind": "other"}

    try:
        response = call_llm(
            task_type='dialog',
            messages=[
                {"role": "system", "content": load_prompt("system/diary_extraction")},
                {"role": "user", "content": message},
            ],
        )
        state['llm_model'] = response.get('model')
        parsed = _safe_parse_json(response.get('content', ''))
        if not parsed or 'kind' not in parsed:
            return {"kind": "other"}
        return parsed

    except Exception as e:
        logger.error(f"Diary extraction error: {e}", exc_info=True)
        return {"kind": "other"}


# ==========================================
# ФОРМАТИРОВАНИЕ / ПАРСИНГ
# ==========================================

def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Безопасно извлекает JSON из ответа модели (со снятием markdown-обёртки)."""
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

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None

    return None
