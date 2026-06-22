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
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


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

    except Exception as e:
        logger.error(f"analyze_against_plan error: {e}", exc_info=True)

    return alerts


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
