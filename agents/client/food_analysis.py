"""
Food Analysis — общий анализ состава еды против рациона клиента

Переиспользуется агентами клиента (vision_agent — фото, diary_agent — текст),
чтобы логика сверки с рационом была в одном месте (DRY).

Проверяет состав на:
- аллергены клиента (critical);
- запрещённые планом продукты (food_forbidden);
- несочетаемые продукты (food_incompatible, pgvector).

Возвращает список алертов (пустой — если всё в порядке).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "all_day")


def resolve_meal_type(text: str = "", explicit: Optional[str] = None) -> str:
    """
    Тип приёма пищи: breakfast | lunch | dinner | snack | all_day.

    Приоритет: явное значение (из extraction) → явные маркеры в тексте →
    по времени суток (сервера; TODO: timezone клиента).
    """
    if explicit in MEAL_TYPES:
        return explicit

    low = (text or "").lower()
    if any(w in low for w in ("на весь день", "весь день", "рацион на день", "за день")):
        return "all_day"
    if any(w in low for w in ("завтрак", "с утра", "утром")):
        return "breakfast"
    if "обед" in low:
        return "lunch"
    if any(w in low for w in ("ужин", "вечером")):
        return "dinner"
    if any(w in low for w in ("перекус", "снек")):
        return "snack"

    hour = datetime.now().hour
    if hour < 12:
        return "breakfast"
    if hour < 17:
        return "lunch"
    if hour < 22:
        return "dinner"
    return "snack"


def analyze_against_plan(
    client_id: str,
    ingredients: List[str],
    mode: str = "full_program",
) -> List[Dict[str, Any]]:
    """
    Сверяет распознанный состав с рационом клиента.

    Args:
        client_id: UUID клиента
        ingredients: список продуктов (названия)
        mode: режим работы клиента ('full_program' | 'ai_support')

    Returns:
        Список алертов: [{type, severity, message, details}], пустой если отклонений нет.
    """
    from business_rules.medical_rules import check_allergies, check_medical_alerts

    alerts: List[Dict[str, Any]] = []

    if not ingredients:
        return alerts

    try:
        # Аллергены (critical) — отдельная проверка
        allergy = check_allergies(client_id, ingredients)
        if allergy.get('has_allergen'):
            alerts.append({
                'type': 'allergen',
                'severity': allergy.get('severity', 'critical'),
                'message': allergy.get('message', ''),
                'details': {'allergens': allergy.get('allergens_found', [])},
            })

        # Запрещённые планом + несочетаемые (pgvector)
        food_alerts = check_medical_alerts(
            client_id=client_id,
            food_items=ingredients,
            mode=mode,
        )
        for a in food_alerts:
            if a.get('type') in ('food_forbidden', 'food_incompatible'):
                alerts.append(a)

        # Смысловая проверка (P1-13, шаг 2). Подстрочные проверки выше ловят только
        # буквальные совпадения: «булгур» не содержит слова «глютен», «кешью» — слова
        # «орехи». Эта проверка смотрит на суть, с опорой на назначения нутрициолога и
        # его базу знаний. Направление 'incoming': клиент уже съел, отменить нельзя —
        # задача просигналить нутрициологу, а не пугать клиента.
        alerts.extend(_semantic_food_alerts(client_id, ingredients))

    except Exception as e:
        logger.error(f"analyze_against_plan error: {e}", exc_info=True)

    return alerts


def _semantic_food_alerts(client_id: str, ingredients: List[str]) -> List[Dict[str, Any]]:
    """
    Алерты по итогам смысловой проверки съеденного (P1-13).

    `violates` → high: нарушение назначений, нутрициолог должен узнать.
    `unclear`  → low: система не смогла ответить уверенно (состав блюда неизвестен,
      формулировка ограничения неоднозначна, нужна врачебная оценка). Это НЕ нарушение,
      но и не «чисто» — нутрициолог видит вопрос у себя, а клиента не тревожим.
    """
    from business_rules.food_check import check_food

    out: List[Dict[str, Any]] = []
    try:
        result = check_food(client_id, ingredients, direction="incoming")
    except Exception as e:
        logger.warning(f"semantic food check failed: {e}")
        return out

    if not result.get("checked"):
        return out

    if result.get("violations"):
        details = "; ".join(
            f"{v['item']} — {v['reason']}" for v in result["violations"] if v.get("item")
        )
        out.append({
            "type": "food_violation",
            "severity": "high",
            "message": f"Нарушение назначений: {details}",
            "details": {"verdicts": result["violations"]},
        })

    if result.get("unclear"):
        details = "; ".join(
            f"{v['item']} — {v['reason']}" for v in result["unclear"] if v.get("item")
        )
        out.append({
            "type": "food_unclear",
            "severity": "low",
            "message": f"Требует вашей оценки: {details}",
            "details": {"verdicts": result["unclear"]},
        })

    return out


def determine_food_routing(alerts: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    """Определяет, уведомлять ли нутрициолога об отклонениях по еде."""
    from business_rules.medical_rules import determine_routing

    try:
        return determine_routing(alerts, mode)
    except Exception as e:
        logger.error(f"determine_food_routing error: {e}")
        return {'route_to': 'llm', 'notify_nutritionist': False}


def highest_severity(alerts: List[Dict[str, Any]]) -> Any:
    """Максимальная severity среди алертов (или None, если алертов нет)."""
    if not alerts:
        return None
    from business_rules.medical_rules import get_highest_severity
    try:
        return get_highest_severity([a.get('severity', 'low') for a in alerts])
    except Exception:
        return 'medium'
