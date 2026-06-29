"""
Domain-слой записи приёма: единая персистентность из IntakeRecord (Слайс 2).

`persist_record(state, record)` — ЕДИНСТВЕННОЕ место, где захваченный факт пишется в БД и
гоняются алерты, независимо от модальности (текст/фото/голос). diary/vision строят
IntakeRecord адаптерами (intake_schema) и зовут эту функцию. Возвращает под-тип захвата
('meal'|'water'|'weight'|'wellbeing'|'labs') для квитанции, либо None (не захватили → clarify).

Поведение эквивалентно прежним diary._handle_* и vision._log_meal_event — логика собрана в
одно место и теперь питается канонической структурой, а не ad-hoc словарями.
"""

import logging
from typing import Any, Dict, List, Optional

from .intake_schema import normalize
from .food_analysis import (
    analyze_against_plan,
    determine_food_routing,
    highest_severity,
)

logger = logging.getLogger(__name__)


def persist_record(state: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Пишет факт из IntakeRecord в БД + алерты. Возвращает под-тип захвата или None."""
    record = normalize(record)
    kind = record.get("kind")
    mode = (state.get("access_info") or {}).get("mode", "full_program")

    if kind == "meal":
        return _persist_meal(state, record, mode)
    if kind == "water":
        return _persist_water(state, record)
    if kind == "weight":
        return _persist_weight(state, record, mode)
    if kind == "wellbeing":
        return _persist_wellbeing(state, record, mode)
    if kind == "lab":
        return _persist_lab(state, record)
    return None


def _persist_meal(state: Dict[str, Any], record: Dict[str, Any], mode: str) -> Optional[str]:
    """Приём пищи: сверка состава с рационом + событие calories_logged (payload из record)."""
    from database import queries

    client_id = state["client_id"]
    meal = record.get("meal") or {}
    items = meal.get("items") or []
    names = [it["name"] for it in items if it.get("name")]

    if not names:
        return None  # не поняли ЧТО съедено → clarify

    state["food_items"] = names

    alerts = analyze_against_plan(client_id, names, mode)
    if alerts:
        state["alerts"] = (state.get("alerts") or []) + alerts
        state["routing"] = determine_food_routing(state["alerts"], mode)

    try:
        queries.log_client_event(
            client_id=client_id,
            event_type="calories_logged",
            severity=highest_severity(alerts),
            payload={
                "source": record.get("source"),
                "meal_type": meal.get("meal_type"),
                "dish_name": meal.get("dish_name"),
                "ingredients": names,
                "items": items,
                "total": meal.get("total"),
                "deviations": [
                    {"type": a.get("type"), "severity": a.get("severity"), "message": a.get("message")}
                    for a in alerts
                ],
                "channel": state.get("channel"),
            },
        )
    except Exception as e:
        logger.error(f"persist_meal failed to log event: {e}")

    return "meal"


def _persist_water(state: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Вода → событие water_logged (мл)."""
    from database import queries

    ml = record.get("water_ml")
    if not ml or ml <= 0:
        return None

    try:
        queries.log_client_event(
            client_id=state["client_id"],
            event_type="water_logged",
            severity=None,
            payload={"water_ml": ml, "channel": state.get("channel")},
        )
    except Exception as e:
        logger.error(f"persist_water failed: {e}")
        return None

    return "water"


def _persist_weight(state: Dict[str, Any], record: Dict[str, Any], mode: str) -> Optional[str]:
    """Вес → measurements (точка ряда) + проверка алерта weight_increase."""
    from database import queries
    from business_rules.medical_rules import check_medical_alerts

    client_id = state["client_id"]
    weight = record.get("weight_kg")
    if weight is None:
        return None

    try:
        queries.insert_measurement(
            client_id=client_id, weight=weight, notes=f"channel={state.get('channel')}"
        )
    except Exception as e:
        logger.error(f"persist_weight failed to insert measurement: {e}")

    try:
        alerts = [
            a for a in check_medical_alerts(client_id=client_id, mode=mode)
            if a.get("type") == "weight_increase"
        ]
    except Exception as e:
        logger.error(f"persist_weight alert check error: {e}")
        alerts = []

    if alerts:
        state["alerts"] = (state.get("alerts") or []) + alerts
        state["routing"] = determine_food_routing(state["alerts"], mode)
        try:
            top = alerts[0]
            queries.log_client_event(
                client_id=client_id,
                event_type="weight_increase",
                severity=top.get("severity") or "high",
                payload={"weight": weight, "message": top.get("message"), "details": top.get("details")},
            )
        except Exception as e:
            logger.error(f"persist_weight failed to log alert: {e}")

    return "weight"


def _persist_wellbeing(state: Dict[str, Any], record: Dict[str, Any], mode: str) -> Optional[str]:
    """Самочувствие → событие; при status='bad' — алерт нутрициологу."""
    from database import queries

    client_id = state["client_id"]
    wb = record.get("wellbeing") or {}
    status = wb.get("status")
    reason = (wb.get("reason") or "").strip()
    is_bad = status == "bad"

    try:
        queries.log_client_event(
            client_id=client_id,
            event_type="bad_wellbeing" if is_bad else "wellbeing_logged",
            severity="medium" if is_bad else None,
            payload={"status": status, "reason": reason, "channel": state.get("channel")},
        )
    except Exception as e:
        logger.error(f"persist_wellbeing failed: {e}")

    if is_bad:
        alert = {
            "type": "bad_wellbeing",
            "severity": "medium",
            "message": f"Клиент сообщает о плохом самочувствии: {reason or status}",
            "details": {"status": status, "reason": reason},
        }
        state["alerts"] = (state.get("alerts") or []) + [alert]
        state["routing"] = determine_food_routing(state["alerts"], mode)

    return "wellbeing"


def _persist_lab(state: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Анализы → lab_results (source='client'). measured_at берётся из записи (если есть)."""
    from database import queries

    client_id = state["client_id"]
    saved: List[Dict[str, Any]] = []
    for item in (record.get("labs") or []):
        try:
            queries.insert_lab_result(
                client_id=client_id,
                indicator=item["indicator"],
                value=item["value"],
                unit=item.get("unit"),
                source="client",
                measured_at=item.get("measured_at"),
            )
            saved.append({"indicator": item["indicator"], "value": item["value"], "unit": item.get("unit")})
        except Exception as e:
            logger.error(f"persist_lab failed for '{item.get('indicator')}': {e}")

    if not saved:
        return None

    state["saved_labs"] = saved
    return "labs"
