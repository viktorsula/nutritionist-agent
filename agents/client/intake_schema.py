"""
IntakeRecord v1 — внутренний протокол передачи извлечённых данных приёма (intake).

Зачем: распознавание (vision/diary/labs) и подача (тёплый ответ клиенту) — две разные
задачи. Их разделяем: экстрактор выдаёт СТРОГУЮ структуру (этот тип), domain-слой её
валидирует/пишет/гоняет алерты, present-слой генерирует прозу ИЗ структуры. Источник
правды для БД/алертов/агрегации — только структура, единая для всех модальностей.

ОБЛАСТЬ: только ветка «приём информации» (что клиент сообщает как факт — еда, вода, вес,
самочувствие, анализы). Ветка «совет» (что приготовить) — отдельный поток, НЕ этот протокол.
Один IntakeRecord = один захваченный факт (один сегмент хода); ход с несколькими темами →
несколько записей.

Уверенность — enum (LLM плохо калибрует числа): low ≈ «понял <~60%/не уверен» → НЕ пишем,
уточняем. medium/high → пишем (неточный объём/форма → КБЖУ грубо/None, клиента не дёргаем).
Все неясные моменты экстрактор кладёт в `uncertainties[]` → present-слой собирает ОДИН
уточняющий вопрос на всё (а не серию).

Этот модуль (Слайс 1): тип + normalize() + validate() + адаптеры из текущих выходов
экстракторов (from_diary_extract / from_food_plate). Поведение графа НЕ меняет — подключение
в diary/vision будет в Слайсе 2.
"""

import re
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

KINDS = ("meal", "water", "weight", "wellbeing", "lab", "measurement", "sleep", "none")
SOURCES = ("text", "photo", "voice")
CONFIDENCE = ("high", "medium", "low")
MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "all_day")
AMOUNT_UNITS = ("g", "ml", "pcs", "serving")
WELLBEING_STATUS = ("good", "ok", "bad")

# КБЖУ — единый набор ключей (граммы; sugar_g/fiber_g — часть углеводов и клетчатка).
KBJU_KEYS = ("kcal", "protein_g", "fat_g", "carb_g", "sugar_g", "fiber_g")

# Негативные маркеры самочувствия (та же эвристика, что в diary; вынесена для переиспользования).
_NEGATIVE_WELLBEING = ("плох", "хуже", "нехорош", "тошн", "боль", "болит", "устал", "слаб")

# Единицы количества: свободный текст → канон.
_UNIT_MAP = {
    "г": "g", "гр": "g", "грамм": "g", "граммов": "g", "g": "g",
    "мл": "ml", "ml": "ml", "млл": "ml",
    "шт": "pcs", "штук": "pcs", "штуки": "pcs", "pcs": "pcs",
    "порц": "serving", "порция": "serving", "порции": "serving", "serving": "serving",
}


# ==========================================
# ВСПОМОГАТЕЛЬНОЕ
# ==========================================

def _to_float(value: Any) -> Optional[float]:
    """float из числа/строки ('5,2'→5.2); None если не число."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def empty_kbju() -> Dict[str, Optional[float]]:
    """КБЖУ со всеми ключами = None (неизвестно)."""
    return {k: None for k in KBJU_KEYS}


def parse_amount(text: Any) -> Optional[Dict[str, Any]]:
    """
    Парсит количество из свободного текста ('150 г', '2 шт', '300мл') → {value, unit}.
    Если число не распознано — None (объём неизвестен, не выдумываем).
    """
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zа-я]+)?", s)
    if not m:
        return None
    value = _to_float(m.group(1))
    if value is None:
        return None
    raw_unit = (m.group(2) or "").strip()
    unit = None
    for prefix, canon in _UNIT_MAP.items():
        if raw_unit.startswith(prefix):
            unit = canon
            break
    return {"value": value, "unit": unit}


def kbju_from_legacy(d: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Старый формат vision (calories/protein/fats/carbs) → канон KBJU_KEYS.

    Защищено от «грязного» входа: LLM иногда отдаёт kbju строкой/числом/списком
    вместо словаря — тогда считаем КБЖУ неизвестным (всё None), а не падаем.
    """
    if not isinstance(d, dict):
        d = {}
    out = empty_kbju()
    out["kcal"] = _to_float(d.get("kcal", d.get("calories")))
    out["protein_g"] = _to_float(d.get("protein_g", d.get("protein")))
    out["fat_g"] = _to_float(d.get("fat_g", d.get("fats")))
    out["carb_g"] = _to_float(d.get("carb_g", d.get("carbs")))
    out["sugar_g"] = _to_float(d.get("sugar_g"))
    out["fiber_g"] = _to_float(d.get("fiber_g"))
    return out


def infer_wellbeing_status(answer: str = "", reason: str = "") -> str:
    """good|ok|bad по тексту (негативные маркеры → bad), иначе 'ok'."""
    text = f"{answer} {reason}".lower()
    if any(m in text for m in _NEGATIVE_WELLBEING):
        return "bad"
    return "ok"


def sum_kbju(items: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Суммирует КБЖУ по элементам (None игнорируем; если все None — ключ остаётся None)."""
    total = empty_kbju()
    for key in KBJU_KEYS:
        vals = [_to_float((it.get("kbju") or {}).get(key)) for it in items]
        vals = [v for v in vals if v is not None]
        total[key] = round(sum(vals), 2) if vals else None
    return total


# ==========================================
# КОНСТРУКТОР
# ==========================================

def empty_record(kind: str, source: str, confidence: str = "medium") -> Dict[str, Any]:
    """Пустая запись заданного типа (релевантный блок заполняет вызывающий/адаптер)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind if kind in KINDS else "none",
        "source": source if source in SOURCES else "text",
        "confidence": confidence if confidence in CONFIDENCE else "medium",
        "uncertainties": [],
        "meal": None,
        "water_ml": None,
        "weight_kg": None,
        "wellbeing": None,
        "labs": None,
        "measurement": None,
        "sleep": None,
    }


def norm_hhmm(value: Any) -> Optional[str]:
    """Приводит время к 'HH:MM' (принимает '23:30', '23.30', '2330'). Иначе None."""
    if value is None:
        return None
    s = str(value).strip().replace(".", ":").replace("-", ":")
    if ":" not in s and s.isdigit() and len(s) in (3, 4):
        s = s.zfill(4)
        s = f"{s[:2]}:{s[2:]}"
    parts = s.split(":")
    try:
        h, m = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


# ==========================================
# НОРМАЛИЗАЦИЯ
# ==========================================

def normalize(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Приводит запись к канону: типы чисел, наличие ключей КБЖУ, досчёт meal.total из items.
    Возвращает НОВЫЙ dict (вход не мутируется). Безопасна к частичным/«грязным» данным.
    """
    r = dict(record or {})
    r["schema_version"] = SCHEMA_VERSION
    r["kind"] = r.get("kind") if r.get("kind") in KINDS else "none"
    r["source"] = r.get("source") if r.get("source") in SOURCES else "text"
    r["confidence"] = r.get("confidence") if r.get("confidence") in CONFIDENCE else "medium"
    unc = r.get("uncertainties") or []
    r["uncertainties"] = [str(u) for u in unc if str(u).strip()]

    # meal
    meal = r.get("meal")
    if r["kind"] == "meal" and isinstance(meal, dict):
        meal = dict(meal)
        meal["meal_type"] = meal.get("meal_type") if meal.get("meal_type") in MEAL_TYPES else "all_day"
        items = []
        for it in (meal.get("items") or []):
            if not isinstance(it, dict) or not str(it.get("name") or "").strip():
                continue
            amount = it.get("amount")
            if amount is not None and not (isinstance(amount, dict) and "value" in amount):
                amount = parse_amount(amount)  # допускаем свободный текст
            items.append({
                "name": str(it["name"]).strip(),
                "form": (str(it["form"]).strip() if it.get("form") else None),
                "amount": amount,
                "kbju": kbju_from_legacy(it.get("kbju")),
            })
        meal["items"] = items
        total = meal.get("total")
        if isinstance(total, dict) and any(_to_float(v) is not None for v in total.values()):
            meal["total"] = kbju_from_legacy(total)
        else:
            meal["total"] = sum_kbju(items)
        r["meal"] = meal
    else:
        r["meal"] = meal if r["kind"] == "meal" else None

    # water / weight
    r["water_ml"] = _to_float(r.get("water_ml"))
    r["weight_kg"] = _to_float(r.get("weight_kg"))

    # wellbeing
    wb = r.get("wellbeing")
    if isinstance(wb, dict):
        status = wb.get("status")
        r["wellbeing"] = {
            "status": status if status in WELLBEING_STATUS else infer_wellbeing_status(
                wb.get("answer", ""), wb.get("reason", "")
            ),
            "reason": str(wb.get("reason") or "").strip(),
        }

    # labs
    labs_in = r.get("labs")
    if isinstance(labs_in, list):
        labs = []
        for item in labs_in:
            if not isinstance(item, dict):
                continue
            indicator = str(item.get("indicator") or "").strip().lower()
            value = _to_float(item.get("value"))
            if not indicator or value is None:
                continue
            labs.append({
                "indicator": indicator,
                "value": value,
                "unit": (str(item.get("unit")).strip() or None) if item.get("unit") else None,
                "measured_at": item.get("measured_at") or None,
            })
        r["labs"] = labs

    # measurement (произвольный контролируемый показатель: metric_key + число)
    meas = r.get("measurement")
    if r["kind"] == "measurement" and isinstance(meas, dict):
        key = str(meas.get("metric_key") or "").strip().lower()
        r["measurement"] = {
            "metric_key": key or None,
            "value": _to_float(meas.get("value")),
            "unit": (str(meas.get("unit")).strip() or None) if meas.get("unit") else None,
        }
    else:
        r["measurement"] = meas if r["kind"] == "measurement" else None

    # sleep (лёг/встал; продолжительность досчитывается при записи)
    sl = r.get("sleep")
    if r["kind"] == "sleep" and isinstance(sl, dict):
        r["sleep"] = {"bedtime": norm_hhmm(sl.get("bedtime")), "wake": norm_hhmm(sl.get("wake"))}
    else:
        r["sleep"] = sl if r["kind"] == "sleep" else None

    return r


# ==========================================
# ВАЛИДАЦИЯ
# ==========================================

def validate(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Проверяет запись и решает, нужен ли уточняющий вопрос.

    Returns {ok, needs_clarify, issues, uncertainties}:
    - ok            — структура валидна (kind/типы корректны);
    - needs_clarify — НЕ писать в БД, спросить клиента (low / нет ключевого факта);
    - issues        — структурные замечания (для отладки/логов);
    - uncertainties — список неясных моментов из записи (для ОДНОГО clarify-сообщения).
    """
    r = record or {}
    issues: List[str] = []

    kind = r.get("kind")
    if kind not in KINDS:
        return {"ok": False, "needs_clarify": True, "issues": ["unknown kind"],
                "uncertainties": list(r.get("uncertainties") or [])}

    needs_clarify = False

    if kind == "none":
        needs_clarify = True
    elif r.get("confidence") == "low":
        needs_clarify = True  # понял < ~60% → уточняем, не пишем
    elif kind == "meal":
        if not ((r.get("meal") or {}).get("items")):
            needs_clarify = True
            issues.append("meal without items")
    elif kind == "water":
        if not (_to_float(r.get("water_ml")) and _to_float(r.get("water_ml")) > 0):
            needs_clarify = True
            issues.append("water without amount")
    elif kind == "weight":
        if _to_float(r.get("weight_kg")) is None:
            needs_clarify = True
            issues.append("weight without value")
    elif kind == "wellbeing":
        wb = r.get("wellbeing") or {}
        if not (wb.get("status") or wb.get("reason")):
            needs_clarify = True
            issues.append("wellbeing empty")
    elif kind == "lab":
        if not (r.get("labs")):
            needs_clarify = True
            issues.append("lab without values")
    elif kind == "measurement":
        m = r.get("measurement") or {}
        if not (m.get("metric_key") and _to_float(m.get("value")) is not None):
            needs_clarify = True
            issues.append("measurement without key/value")
    elif kind == "sleep":
        s = r.get("sleep") or {}
        if not (s.get("bedtime") and s.get("wake")):
            needs_clarify = True
            issues.append("sleep without bedtime/wake")

    return {
        "ok": not issues or needs_clarify,
        "needs_clarify": needs_clarify,
        "issues": issues,
        "uncertainties": list(r.get("uncertainties") or []),
    }


# ==========================================
# АДАПТЕРЫ (текущие выходы экстракторов → IntakeRecord)
# ==========================================

def from_diary_extract(
    extracted: Dict[str, Any],
    *,
    source: str = "text",
    meal_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Маппит выход diary `_extract` ({kind, ingredients, weight_kg, water_ml, wellbeing, labs,
    meal_type}) в IntakeRecord. Текст обычно явный → confidence high, кроме нераспознанного.
    """
    ex = extracted or {}
    raw_kind = ex.get("kind")
    kind = raw_kind if raw_kind in KINDS else ("none" if raw_kind in (None, "other") else raw_kind)
    kind = kind if kind in KINDS else "none"

    confidence = "low" if kind == "none" else "high"
    rec = empty_record(kind, source, confidence)

    if kind == "meal":
        items = [{"name": str(i).strip(), "form": None, "amount": None, "kbju": empty_kbju()}
                 for i in (ex.get("ingredients") or []) if str(i).strip()]
        rec["meal"] = {
            "meal_type": (meal_type or ex.get("meal_type")),
            "dish_name": None,
            "items": items,
            "total": empty_kbju(),
        }
    elif kind == "water":
        rec["water_ml"] = ex.get("water_ml")
    elif kind == "weight":
        rec["weight_kg"] = ex.get("weight_kg")
    elif kind == "wellbeing":
        wb = ex.get("wellbeing") or {}
        rec["wellbeing"] = {"status": None, "answer": wb.get("answer", ""), "reason": wb.get("reason", "")}
    elif kind == "lab":
        rec["labs"] = ex.get("labs") or []

    return normalize(rec)


def from_food_plate(
    food_analysis: Dict[str, Any],
    *,
    meal_type: Optional[str] = None,
    source: str = "photo",
) -> Dict[str, Any]:
    """
    Маппит выход `utils.vision.analyze_food_plate` (dish_name/ingredients/nutrition/confidence)
    в IntakeRecord(kind=meal). Старые ключи КБЖУ (calories/protein/fats/carbs) → канон.
    """
    fa = food_analysis or {}
    confidence = (fa.get("confidence") or "medium").lower()
    rec = empty_record("meal", source, confidence)

    # Карта КБЖУ по имени ингредиента из nutrition.items (если есть).
    nutrition = fa.get("nutrition") or {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for ni in (nutrition.get("items") or []):
        if isinstance(ni, dict) and ni.get("name"):
            by_name[str(ni["name"]).strip().lower()] = ni

    items = []
    for ing in (fa.get("ingredients") or []):
        if isinstance(ing, dict):
            name = str(ing.get("name") or "").strip()
            if not name:
                continue
            items.append({
                "name": name,
                "form": (str(ing["form"]).strip() if ing.get("form") else None),
                "amount": parse_amount(ing.get("approx_amount")),
                "kbju": kbju_from_legacy(by_name.get(name.lower())),
            })
        elif isinstance(ing, str) and ing.strip():
            items.append({"name": ing.strip(), "form": None, "amount": None, "kbju": empty_kbju()})

    total = nutrition.get("total")
    rec["meal"] = {
        "meal_type": meal_type,
        "dish_name": (str(fa["dish_name"]).strip() if fa.get("dish_name") else None),
        "items": items,
        "total": kbju_from_legacy(total) if total else empty_kbju(),
    }
    rec["uncertainties"] = list(fa.get("uncertainties") or [])
    return normalize(rec)


def coerce_to_record(
    parsed: Dict[str, Any],
    *,
    source: str,
    meal_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Приводит выход экстрактора к IntakeRecord, принимая ОБА формата (де-риск Слайса 4):

    - НОВЫЙ (промпт выдаёт схему: есть `meal`/`schema_version`, а для текста — `confidence`)
      → normalize() напрямую (+ форс meal_type, маппинг 'other'→'none');
    - СТАРЫЙ (legacy) → прежние адаптеры: photo → from_food_plate, text → from_diary_extract.

    Так смена промпта не роняет поток: если LLM вернёт ответ «по-старому», он всё равно
    корректно разложится.
    """
    parsed = parsed or {}
    is_new = (
        "meal" in parsed
        or "schema_version" in parsed
        or (source == "text" and "confidence" in parsed)
    )

    if is_new:
        rec = dict(parsed)
        rec.setdefault("source", source)
        if rec.get("kind") == "other":
            rec["kind"] = "none"
        if meal_type and isinstance(rec.get("meal"), dict):
            rec["meal"] = {**rec["meal"], "meal_type": meal_type}
        return normalize(rec)

    if source == "photo":
        return from_food_plate(parsed, meal_type=meal_type, source=source)
    return from_diary_extract(parsed, source=source, meal_type=meal_type)
