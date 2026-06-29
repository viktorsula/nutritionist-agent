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
import re
from typing import Any, Dict, Optional, Tuple

from utils.vision import (
    analyze_food_plate,
    extract_ingredient_names,
    classify_image,
    analyze_lab_document,
)
from .state import ClientState
from .food_analysis import resolve_meal_type
from .intake_schema import from_food_plate, empty_record
from .intake_store import persist_record
from .intake_present import present

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

    # 1b. Тип изображения. Если фото уже распознано в нормализации (ingest) —
    # переиспользуем (без повторного вызова Gemini); иначе классифицируем здесь.
    kind = state.get('image_kind')
    if not kind:
        try:
            kind = classify_image(image_bytes, mime_type=mime_type)
        except Exception as e:
            logger.warning(f"Vision classify failed, fallback to food: {e}")
            kind = 'food'

    # Документ-анализы — отдельной веткой; еда / холодильник / прочее — пищевым путём.
    if kind == 'lab_document':
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

    # 4. Распознано → строим IntakeRecord и пишем единым domain-слоем
    #    (состав/food_items, анализ рациона, алерты, событие calories_logged).
    meal_type = resolve_meal_type(state.get('message', ''))
    record = from_food_plate(food_analysis, meal_type=meal_type)
    state['intake_subtype'] = persist_record(state, record)

    # 5. Ответ. При ack_only (захват удался) тёплый ответ не нужен — заменит квитанция.
    if state.get('ack_only'):
        state['agent_response'] = ''
        return state

    state['agent_response'] = present(state, record, prompt_name='client/vision_system')
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
# ВЕТКА: ДОКУМЕНТ-АНАЛИЗЫ (фото бланка → lab_results)
# ==========================================

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _handle_lab_document(state: ClientState, image_bytes: bytes, mime_type: str) -> ClientState:
    """Фото распознано как документ-анализы: извлекаем показатели в lab_results."""
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

    # Строим IntakeRecord(lab) и пишем единым domain-слоем (normalize чистит значения).
    record = empty_record('lab', 'photo')
    record['labs'] = [
        {"indicator": it.get('indicator'), "value": it.get('value'),
         "unit": it.get('unit'), "measured_at": measured_at}
        for it in labs if isinstance(it, dict)
    ]
    subtype = persist_record(state, record)

    if not subtype:
        state['agent_response'] = (
            "Похоже, на фото документ, но числовые показатели разобрать не удалось 🙈 "
            "Пришли фото почётче — или напиши показатели текстом."
        )
        return state

    saved = state.get('saved_labs') or []
    state['intake_subtype'] = subtype

    if state.get('ack_only'):
        state['agent_response'] = ''
        return state

    recorded = ", ".join(
        f"{l['indicator']} {l['value']}{(' ' + l['unit']) if l.get('unit') else ''}" for l in saved
    )
    state['agent_response'] = (
        f"Записал результаты анализов в твою карту ✅\n{recorded}\n"
        "Нутрициолог их увидит. Если что-то распозналось неточно — поправь текстом."
    )
    return state
