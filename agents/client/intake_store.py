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
    if kind == "measurement":
        return _persist_measurement(state, record)
    if kind == "sleep":
        return _persist_sleep(state, record)
    return None


# Показатели, у которых есть колонка в measurements (пишем туда, а не в client_metrics).
PHYSICAL_METRIC_COLUMNS = ("weight", "waist", "neck", "hips", "chest")


def metric_category(metric_key: str) -> str:
    """Категория показателя по ключу → куда писать значение."""
    if metric_key in PHYSICAL_METRIC_COLUMNS:
        return "physical"
    if metric_key == "sleep":
        return "sleep"
    return "custom"


def _sleep_duration_hours(bedtime: str, wake: str) -> Optional[float]:
    """Продолжительность сна в часах по 'HH:MM' лёг/встал (учёт перехода через полночь)."""
    try:
        bh, bm = (int(x) for x in bedtime.split(":"))
        wh, wm = (int(x) for x in wake.split(":"))
    except (ValueError, AttributeError):
        return None
    bed = bh * 60 + bm
    up = wh * 60 + wm
    if up <= bed:
        up += 24 * 60  # встал на следующие сутки
    return round((up - bed) / 60.0, 2)


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
                "alerts": [
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


def _persist_measurement(state: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Контролируемый показатель → measurements (physical) или client_metrics (custom)."""
    from database import queries

    client_id = state["client_id"]
    m = record.get("measurement") or {}
    key = m.get("metric_key")
    value = m.get("value")
    if not key or value is None:
        return None

    category = metric_category(key)
    try:
        if category == "physical":
            queries.insert_measurement(client_id=client_id, **{key: value})
        else:
            queries.insert_client_metric(
                client_id=client_id, metric_key=key, category=category,
                value_num=value, unit=m.get("unit"),
            )
    except Exception as e:
        logger.error(f"persist_measurement failed for '{key}': {e}")
        return None

    state["saved_metric"] = {"metric_key": key, "value": value, "unit": m.get("unit")}
    return "measurement"


def _persist_sleep(state: Dict[str, Any], record: Dict[str, Any]) -> Optional[str]:
    """Сон: лёг/встал → client_metrics (metric_key='sleep', продолжительность в часах + meta)."""
    from database import queries

    client_id = state["client_id"]
    s = record.get("sleep") or {}
    bedtime = s.get("bedtime")
    wake = s.get("wake")
    if not bedtime or not wake:
        return None

    duration = _sleep_duration_hours(bedtime, wake)
    try:
        queries.insert_client_metric(
            client_id=client_id, metric_key="sleep", category="sleep",
            value_num=duration, unit="ч", meta={"bedtime": bedtime, "wake": wake},
        )
    except Exception as e:
        logger.error(f"persist_sleep failed: {e}")
        return None

    state["saved_sleep"] = {"bedtime": bedtime, "wake": wake, "duration_h": duration}
    return "sleep"
