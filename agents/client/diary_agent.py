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
from .food_analysis import analyze_against_plan, determine_food_routing, highest_severity

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

    extracted = _extract(state)
    kind = extracted.get('kind', 'other')

    mode = state.get('access_info', {}).get('mode', 'full_program')

    if kind == 'weight':
        outcome = _handle_weight(state, extracted, mode)
    elif kind == 'wellbeing':
        outcome = _handle_wellbeing(state, extracted, mode)
    elif kind == 'meal':
        outcome = _handle_meal(state, extracted, mode)
    elif kind == 'lab':
        outcome = _handle_lab(state, extracted, mode)
    else:
        outcome = 'other'

    state['agent_response'] = _build_response(state, extracted, outcome)
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
# ОБРАБОТЧИКИ ПО ТИПУ
# ==========================================

def _handle_weight(state: ClientState, extracted: Dict[str, Any], mode: str) -> str:
    """Фиксирует вес и проверяет алерт резкого изменения."""
    from database import queries
    from business_rules.medical_rules import check_medical_alerts

    client_id = state['client_id']
    weight = extracted.get('weight_kg')

    if weight is None:
        return 'other'

    # Вес — это точка временного ряда → measurements (для графиков/динамики),
    # а НЕ событие. Событие в client_events пишем только если сработает алерт (ниже).
    try:
        queries.insert_measurement(
            client_id=client_id,
            weight=weight,
            notes=f"channel={state.get('channel')}",
        )
    except Exception as e:
        logger.error(f"Diary failed to insert measurement: {e}")

    # Проверка алерта weight_increase (сравнивает события за 24ч)
    try:
        alerts = [
            a for a in check_medical_alerts(client_id=client_id, mode=mode)
            if a.get('type') == 'weight_increase'
        ]
    except Exception as e:
        logger.error(f"Diary weight alert check error: {e}")
        alerts = []

    if alerts:
        state['alerts'] = (state.get('alerts') or []) + alerts
        state['routing'] = determine_food_routing(state['alerts'], mode)
        # Персистим алерт как событие с severity, чтобы он попал в панель
        # алертов нутрициолога (сам вес выше уходит в measurements, не в события).
        try:
            top = alerts[0]
            queries.log_client_event(
                client_id=client_id,
                event_type='weight_increase',
                severity=top.get('severity') or 'high',
                payload={
                    "weight": weight,
                    "message": top.get('message'),
                    "details": top.get('details'),
                },
            )
        except Exception as e:
            logger.error(f"Diary failed to log weight_increase alert: {e}")

    return 'weight'


def _handle_wellbeing(state: ClientState, extracted: Dict[str, Any], mode: str) -> str:
    """Фиксирует самочувствие; при негативном — уведомляет нутрициолога."""
    from database import queries

    client_id = state['client_id']
    wb = extracted.get('wellbeing') or {}
    answer = (wb.get('answer') or '').strip()
    reason = (wb.get('reason') or '').strip()

    # Негативное самочувствие → алерт bad_wellbeing
    negative_markers = ('плох', 'хуже', 'нехорош', 'тошн', 'боль', 'болит', 'устал', 'слаб')
    is_bad = any(m in (answer + ' ' + reason).lower() for m in negative_markers)

    severity = 'medium' if is_bad else None

    try:
        queries.log_client_event(
            client_id=client_id,
            event_type='bad_wellbeing' if is_bad else 'wellbeing_logged',
            severity=severity,
            payload={"answer": answer, "reason": reason, "channel": state.get('channel')},
        )
    except Exception as e:
        logger.error(f"Diary failed to log wellbeing: {e}")

    if is_bad:
        alert = {
            'type': 'bad_wellbeing',
            'severity': 'medium',
            'message': f"Клиент сообщает о плохом самочувствии: {reason or answer}",
            'details': {"answer": answer, "reason": reason},
        }
        state['alerts'] = (state.get('alerts') or []) + [alert]
        state['routing'] = determine_food_routing(state['alerts'], mode)

    return 'wellbeing'


def _handle_meal(state: ClientState, extracted: Dict[str, Any], mode: str) -> str:
    """Фиксирует приём пищи (текстом) и сверяет состав с рационом."""
    from database import queries

    client_id = state['client_id']
    ingredients = [str(i) for i in (extracted.get('ingredients') or []) if i]

    if not ingredients:
        return 'other'

    state['food_items'] = ingredients

    alerts = analyze_against_plan(client_id, ingredients, mode)
    if alerts:
        state['alerts'] = (state.get('alerts') or []) + alerts
        state['routing'] = determine_food_routing(state['alerts'], mode)

    try:
        queries.log_client_event(
            client_id=client_id,
            event_type='calories_logged',
            severity=highest_severity(alerts),
            payload={
                "source": "text",
                "ingredients": ingredients,
                "deviations": [
                    {"type": a.get('type'), "severity": a.get('severity'), "message": a.get('message')}
                    for a in alerts
                ],
                "channel": state.get('channel'),
            },
        )
    except Exception as e:
        logger.error(f"Diary failed to log meal: {e}")

    return 'meal'


def _handle_lab(state: ClientState, extracted: Dict[str, Any], mode: str) -> str:
    """Фиксирует названные клиентом результаты анализов в lab_results (source='client')."""
    from database import queries

    client_id = state['client_id']
    labs = extracted.get('labs') or []

    saved: List[Dict[str, Any]] = []
    for item in labs:
        if not isinstance(item, dict):
            continue
        indicator = str(item.get('indicator') or '').strip().lower()
        value = _to_float(item.get('value'))
        if not indicator or value is None:
            continue
        unit = (str(item.get('unit')).strip() or None) if item.get('unit') else None
        try:
            queries.insert_lab_result(
                client_id=client_id,
                indicator=indicator,
                value=value,
                unit=unit,
                source='client',
            )
            saved.append({"indicator": indicator, "value": value, "unit": unit})
        except Exception as e:
            logger.error(f"Diary failed to insert lab result '{indicator}': {e}")

    if not saved:
        return 'other'

    state['saved_labs'] = saved
    return 'lab'


def _to_float(value: Any) -> Optional[float]:
    """Аккуратно приводит значение к float (поддержка '5,2' и '5.2'); иначе None."""
    if value is None:
        return None
    try:
        return float(str(value).replace(',', '.').strip())
    except (ValueError, TypeError):
        return None


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
