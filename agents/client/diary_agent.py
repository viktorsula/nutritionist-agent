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

    state['agent_response'] = _build_response(state, extracted, _present_outcome(subtype))
    return state


def _present_outcome(subtype: Optional[str]) -> str:
    """Под-тип захвата → сценарий для _build_response ('labs'→'lab', None→'other')."""
    return {'labs': 'lab'}.get(subtype, subtype or 'other')


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
# ОТВЕТ КЛИЕНТУ (LLM)
# ==========================================

def _build_response(state: ClientState, extracted: Dict[str, Any], outcome: str) -> str:
    """Формирует тёплый ответ через dialog-LLM по сценарию outcome."""
    try:
        system_prompt = _build_system_prompt(state)
        user_content = _build_facts_message(state, extracted, outcome)

        response = call_llm(
            task_type='dialog',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        state['llm_model'] = response.get('model')
        state['llm_usage'] = response.get('usage', {})
        return response['content']

    except Exception as e:
        logger.error(f"Diary response build error: {e}", exc_info=True)
        return _fallback_ack(outcome)


def _build_system_prompt(state: ClientState) -> str:
    profile = state.get('client_profile') or {}
    plan = state.get('active_plan') or {}

    try:
        template = load_prompt('client/diary_system')
        return template.format(
            client_name=profile.get('name', 'Клиент'),
            restrictions=_format_list(plan.get('restrictions')),
            allergies=_format_allergies(profile),
            language='русский',  # TODO: определять из profile/channel
        )
    except Exception as e:
        logger.error(f"Error building diary system prompt: {e}")
        return (
            "Ты ИИ-ассистент нутрициолога, ведёшь дневник клиента. "
            "Тепло подтверди, что записал сообщение, и при необходимости уточни. "
            "Не выдумывай. Отвечай на русском."
        )


def _build_facts_message(state: ClientState, extracted: Dict[str, Any], outcome: str) -> str:
    lines = [f"СЦЕНАРИЙ: {outcome}", f"Сообщение клиента: {state.get('message', '')}"]

    if outcome == 'meal':
        lines.append("Записанный состав: " + ", ".join(state.get('food_items') or []))
    elif outcome == 'weight':
        lines.append(f"Записанный вес: {extracted.get('weight_kg')} кг")
    elif outcome == 'wellbeing':
        wb = extracted.get('wellbeing') or {}
        lines.append(f"Самочувствие: {wb.get('answer', '')}; причина: {wb.get('reason', '') or '—'}")
    elif outcome == 'lab':
        labs = state.get('saved_labs') or []
        recorded = ", ".join(
            f"{l['indicator']} {l['value']}{(' ' + l['unit']) if l.get('unit') else ''}" for l in labs
        )
        lines.append(f"Записанные анализы: {recorded}")
        lines.append("Не интерпретируй медицински — просто подтверди, что внёс в карту.")

    alerts = state.get('alerts') or []
    if alerts:
        lines.append("Отклонения/алерты (упомяни мягко, аллерген — серьёзно):")
        for a in alerts:
            lines.append(f"- [{a.get('severity', 'low')}] {a.get('type')}: {a.get('message', '')}")

    lines.append("\nСформулируй короткий тёплый ответ клиенту по сценарию.")
    return "\n".join(lines)


def _fallback_ack(outcome: str) -> str:
    acks = {
        'meal': "Спасибо, записал твой приём пищи ✅ Если что-то не так — поправь.",
        'weight': "Записал твой вес ✅ Продолжай отмечать — так виднее динамика.",
        'wellbeing': "Спасибо, что поделился самочувствием 🙏 Я всё зафиксировал.",
        'lab': "Записал результаты анализов в твою карту ✅ Нутрициолог их увидит.",
        'other': "Не совсем понял 🙂 Хочешь записать приём пищи, вес или самочувствие?",
    }
    return acks.get(outcome, acks['other'])


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


def _format_list(values: Optional[List[Any]]) -> str:
    if not values:
        return "Нет"
    return ", ".join(str(v) for v in values)


def _format_allergies(profile: Dict[str, Any]) -> str:
    allergies = (profile or {}).get('allergies') or []
    if not allergies:
        return "Нет"
    names = [a.get('name', a) if isinstance(a, dict) else a for a in allergies]
    return ", ".join(str(n) for n in names)
