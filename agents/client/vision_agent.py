"""
Vision Agent — агент обработки фото еды клиента

Главный смысл (по требованию владельца):
снять с нутрициолога рутину ежедневного контроля питания. Агент фиксирует, ЧТО
реально ест клиент, сверяет с назначенным рационом и эскалирует только отклонения.

Поток:
1. Достать изображение из state['metadata'] (image_bytes + mime_type).
2. Распознать состав через utils.vision.analyze_food_plate (ингредиенты — первично,
   КБЖУ — вторично).
3. Развилка по исходу:
   - нет фото / нечитаемо / еда не распознана → попросить переснять или описать словами;
   - распознано → подтвердить получение, пригласить дополнить.
4. Анализ состава против рациона (business_rules): аллергены, запрещённые, несочетаемые.
5. Отклонения → событие + флаг уведомления нутрициолога; клиенту — мягкое предупреждение
   (аллерген — строго).
6. Сохранить распознанное в память (client_events: calories_logged).

Промпт: prompts/client/vision_system.md
LLM: Groq llama-3.3-70b (task_type='dialog') — только для тёплой формулировки ответа
при успешном распознавании.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from utils.llm import call_llm
import re

from utils.vision import (
    analyze_food_plate,
    extract_ingredient_names,
    classify_image,
    analyze_lab_document,
)
from prompts import load_prompt
from .state import ClientState
from .food_analysis import analyze_against_plan, determine_food_routing, highest_severity

logger = logging.getLogger(__name__)


# ==========================================
# УЗЕЛ LANGGRAPH
# ==========================================

def vision_node(state: ClientState) -> ClientState:
    """
    Узел обработки фото еды клиента.

    Устанавливает в state: agent_response, agent_used, food_items, alerts, routing,
    llm_model. Алерты добавляются в общий список и далее форматируются в
    format_response_node оркестратора.
    """
    state['agent_used'] = 'vision_agent'

    # 1. Получение изображения
    image_bytes, mime_type = _get_image_from_state(state)

    if not image_bytes:
        state['agent_response'] = (
            "Кажется, фото не дошло 🙈 Пришли его, пожалуйста, ещё раз — "
            "или просто опиши словами, что и как приготовлено."
        )
        return state

    # 1b. Тип изображения: документ-анализы обрабатываем отдельной веткой,
    # еда/прочее — пищевым путём (исторически).
    try:
        kind = classify_image(image_bytes, mime_type=mime_type)
    except Exception as e:
        logger.warning(f"Vision classify failed, fallback to food: {e}")
        kind = 'food'

    if kind == 'document':
        return _handle_lab_document(state, image_bytes, mime_type)

    # 2. Распознавание состава
    try:
        food_analysis = analyze_food_plate(image_bytes, mime_type=mime_type)
    except Exception as e:
        logger.error(f"Vision agent recognition error: {e}", exc_info=True)
        state['agent_response'] = (
            "Не получилось обработать фото 🙈 Попробуй прислать его ещё раз "
            "или опиши блюдо словами — я всё запишу."
        )
        state['agent_used'] = 'vision_agent_error'
        state['error'] = str(e)
        return state

    ingredients = extract_ingredient_names(food_analysis)
    confidence = (food_analysis.get('confidence') or 'low').lower()

    # 3. Исход: не распознано → переснять / описать словами
    if not ingredients or confidence == 'low':
        state['agent_response'] = (
            "Не удалось уверенно разобрать, что на фото 🙈 "
            "Пришли, пожалуйста, ещё раз при хорошем освещении — "
            "или опиши словами, что и как приготовлено. Я всё зафиксирую."
        )
        return state

    # 4. Исход: распознано → сохраняем состав и анализируем рацион
    state['food_items'] = ingredients

    mode = state.get('access_info', {}).get('mode', 'full_program')
    alerts = analyze_against_plan(state['client_id'], ingredients, mode)
    state['alerts'] = (state.get('alerts') or []) + alerts

    # Маршрутизация (уведомлять ли нутрициолога об отклонениях)
    state['routing'] = determine_food_routing(state['alerts'], mode)

    # 5. Ответ клиенту (тёплый, через LLM; предупреждения добавит format_response)
    outcome = 'recognized_deviation' if alerts else 'recognized_ok'
    state['agent_response'] = _build_response(state, food_analysis, outcome)

    # 6. Память: зафиксировать приём пищи
    _log_meal_event(state, food_analysis, alerts)

    return state


# ==========================================
# ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ
# ==========================================

def _get_image_from_state(state: ClientState) -> Tuple[Optional[bytes], str]:
    """
    Достаёт байты изображения и mime-тип из metadata.

    Ожидаемый контракт (заполняется Telegram/веб на Шаге 3):
        metadata['image_bytes']: bytes
        metadata['mime_type']: str (по умолчанию image/jpeg)
    """
    metadata = state.get('metadata') or {}
    image_bytes = metadata.get('image_bytes')
    mime_type = metadata.get('mime_type', 'image/jpeg')

    if not image_bytes:
        return None, mime_type

    return image_bytes, mime_type


# ==========================================
# ОТВЕТ КЛИЕНТУ (LLM)
# ==========================================

def _build_response(
    state: ClientState,
    food_analysis: Dict[str, Any],
    outcome: str,
) -> str:
    """
    Формирует тёплый ответ клиенту через dialog-LLM на основе распознанного состава.

    Детерминированные предупреждения (аллерген/отклонения) добавляются позже в
    format_response_node оркестратора из state['alerts'] — здесь только дружелюбное
    подтверждение и приглашение дополнить.
    """
    try:
        system_prompt = _build_system_prompt(state)
        user_content = _build_facts_message(state, food_analysis, outcome)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        response = call_llm(task_type='dialog', messages=messages)
        state['llm_model'] = response.get('model')
        state['llm_usage'] = response.get('usage', {})
        return response['content']

    except Exception as e:
        logger.error(f"Vision agent response build error: {e}", exc_info=True)
        # Детерминированный fallback — подтверждение получения
        return _fallback_ack(food_analysis)


def _build_system_prompt(state: ClientState) -> str:
    """Загружает и заполняет prompts/client/vision_system.md."""
    profile = state.get('client_profile') or {}
    plan = state.get('active_plan') or {}

    try:
        template = load_prompt('client/vision_system')
        return template.format(
            client_name=profile.get('name', 'Клиент'),
            restrictions=_format_list(plan.get('restrictions')),
            allergies=_format_allergies(profile),
            language='русский',  # TODO: определять из profile/channel
        )
    except Exception as e:
        logger.error(f"Error building vision system prompt: {e}")
        return (
            "Ты ИИ-ассистент нутрициолога. Клиент прислал фото еды, состав уже распознан. "
            "Тепло подтверди получение, кратко перечисли записанное и пригласи дополнить. "
            "Не выдумывай продукты. Отвечай на русском."
        )


def _build_facts_message(
    state: ClientState,
    food_analysis: Dict[str, Any],
    outcome: str,
) -> str:
    """Формирует пользовательское сообщение с распознанными фактами для LLM."""
    lines = [f"СЦЕНАРИЙ: {outcome}"]

    dish = food_analysis.get('dish_name')
    if dish:
        lines.append(f"Блюдо: {dish}")

    lines.append("Распознанный состав:")
    lines.append(_format_ingredients(food_analysis))

    nutrition_text = _format_nutrition(food_analysis)
    if nutrition_text:
        lines.append(f"Примерно КБЖУ (справочно): {nutrition_text}")

    # Подпись/комментарий клиента к фото, если был
    caption = (state.get('message') or '').strip()
    if caption:
        lines.append(f"Комментарий клиента к фото: {caption}")

    alerts = state.get('alerts') or []
    if alerts:
        lines.append("Выявленные отклонения от рациона (упомяни мягко, аллерген — серьёзно):")
        for a in alerts:
            lines.append(f"- [{a.get('severity', 'low')}] {a.get('type')}: {a.get('message', '')}")

    lines.append("\nСформулируй короткий тёплый ответ клиенту по сценарию.")
    return "\n".join(lines)


def _fallback_ack(food_analysis: Dict[str, Any]) -> str:
    """Детерминированное подтверждение, если LLM недоступен."""
    ingredients = _format_ingredients(food_analysis)
    return (
        "Спасибо, фото получил ✅ Записал:\n"
        f"{ingredients}\n"
        "Если что-то распозналось неточно — напиши, поправлю."
    )


# ==========================================
# ВЕТКА: ДОКУМЕНТ-АНАЛИЗЫ (фото бланка → lab_results)
# ==========================================

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _handle_lab_document(state: ClientState, image_bytes: bytes, mime_type: str) -> ClientState:
    """Фото распознано как документ-анализы: извлекаем показатели в lab_results."""
    from database import queries

    state['agent_used'] = 'vision_agent_labs'

    try:
        result = analyze_lab_document(image_bytes, mime_type=mime_type)
    except Exception as e:
        logger.error(f"Vision lab-document recognition error: {e}", exc_info=True)
        state['agent_response'] = (
            "Не получилось разобрать документ 🙈 Пришли фото почётче при хорошем "
            "освещении — или просто напиши показатели текстом (например, «холестерин 5.2»)."
        )
        state['agent_used'] = 'vision_agent_error'
        state['error'] = str(e)
        return state

    labs = result.get('labs') or []
    measured_at = result.get('measured_at') if _DATE_RE.match(str(result.get('measured_at') or '')) else None

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
                client_id=state['client_id'],
                indicator=indicator,
                value=value,
                unit=unit,
                source='client',
                measured_at=measured_at,
            )
            saved.append({"indicator": indicator, "value": value, "unit": unit})
        except Exception as e:
            logger.error(f"Vision failed to insert lab result '{indicator}': {e}")

    if not saved:
        state['agent_response'] = (
            "Похоже, на фото документ, но числовые показатели разобрать не удалось 🙈 "
            "Пришли фото почётче — или напиши показатели текстом."
        )
        return state

    state['saved_labs'] = saved
    recorded = ", ".join(
        f"{l['indicator']} {l['value']}{(' ' + l['unit']) if l.get('unit') else ''}" for l in saved
    )
    state['agent_response'] = (
        f"Записал результаты анализов в твою карту ✅\n{recorded}\n"
        "Нутрициолог их увидит. Если что-то распозналось неточно — поправь текстом."
    )
    return state


def _to_float(value: Any) -> Optional[float]:
    """Приводит значение к float (поддержка '5,2'); иначе None."""
    if value is None:
        return None
    try:
        return float(str(value).replace(',', '.').strip())
    except (ValueError, TypeError):
        return None


# ==========================================
# ПАМЯТЬ (client_events)
# ==========================================

def _log_meal_event(
    state: ClientState,
    food_analysis: Dict[str, Any],
    alerts: List[Dict[str, Any]],
) -> None:
    """Сохраняет распознанный приём пищи в client_events (calories_logged)."""
    from database import queries

    severity = highest_severity(alerts)

    payload = {
        "dish_name": food_analysis.get('dish_name', ''),
        "ingredients": food_analysis.get('ingredients', []),
        "nutrition": food_analysis.get('nutrition', {}),
        "confidence": food_analysis.get('confidence', ''),
        "deviations": [
            {"type": a.get('type'), "severity": a.get('severity'), "message": a.get('message')}
            for a in alerts
        ],
        "channel": state.get('channel'),
    }

    try:
        queries.log_client_event(
            client_id=state['client_id'],
            event_type='calories_logged',
            severity=severity,
            payload=payload,
        )
    except Exception as e:
        logger.error(f"Vision agent failed to log meal event: {e}")


# ==========================================
# ФОРМАТИРОВАНИЕ
# ==========================================

def _format_ingredients(food_analysis: Dict[str, Any]) -> str:
    """Человекочитаемый список ингредиентов с формой приготовления."""
    ingredients = food_analysis.get('ingredients') or []
    if not ingredients:
        return "—"

    lines = []
    for ing in ingredients:
        if isinstance(ing, dict):
            name = ing.get('name', '')
            form = ing.get('form')
            amount = ing.get('approx_amount')
            extra = ", ".join(x for x in [form, amount] if x)
            lines.append(f"- {name}" + (f" ({extra})" if extra else ""))
        elif isinstance(ing, str):
            lines.append(f"- {ing}")
    return "\n".join(lines)


def _format_nutrition(food_analysis: Dict[str, Any]) -> str:
    """Строка с суммарным КБЖУ (справочно), если есть."""
    total = (food_analysis.get('nutrition') or {}).get('total') or {}
    if not total or not any(total.values()):
        return ""
    return (
        f"{total.get('calories', 0)} ккал, "
        f"Б {total.get('protein', 0)} / Ж {total.get('fats', 0)} / У {total.get('carbs', 0)}"
    )


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
