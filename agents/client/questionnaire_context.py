"""
Форматирование "остаточных" полей анкеты онбординга (не попавших в структурные
колонки client_profiles) для подачи в системный промпт клиентского оркестратора.

Почему это нужно (P1-14): из 33 полей анкеты в структурные колонки client_profiles
попадают только 9 (birth_date/gender/weight/height/target_weight/activity_level/
allergies/chronic_conditions/goals) — остальные ~24 уходят в questionnaire_json и
раньше никогда не читались (ни LLM, ни кабинетом нутрициолога). Клиент их сообщает
не просто так — они создают полный контекст ("что за человек перед нами"), поэтому
считаются частью профиля клиента, а не второстепенными данными по запросу.

Метки (label) продублированы из frontend/src/features/questionnaire/schema.ts —
источник правды для UI. При изменении schema.ts синхронизировать вручную (полей
редко добавляют/меняют — анкета зафиксирована структурой онбординга).
"""

from typing import Any, Dict, Optional

# Поля, уже отражённые в структурных колонках client_profiles (или неприменимые
# как текст в промпте) — исключаем, чтобы не дублировать.
_EXCLUDED_FIELDS = {
    "full_name", "birth_date", "gender", "weight", "height", "target_weight",
    "neck", "waist", "hips", "sport_level", "allergies", "chronic_conditions",
    "improve_targets", "goal_text", "labs_files",
}

# Метка (ru) для оставшихся полей — синхронизировано с schema.ts.
_FIELD_LABELS: Dict[str, str] = {
    "weight_history": "Динамика веса за 3–5 лет",
    "daily_routine": "Режим дня",
    "bedtime": "Обычное время отхода ко сну",
    "wakeup": "Обычное время подъёма",
    "work_field": "Сфера работы",
    "work_activity": "Активность на работе",
    "outdoor_hours_week": "Часов на воздухе в неделю",
    "sport_details": "Спорт/физнагрузки — подробно",
    "diet_typical": "Типичный рацион (2–3 дня)",
    "water_liters": "Вода в день на момент анкеты",
    "other_drinks": "Другие напитки",
    "alcohol": "Алкоголь",
    "eating_out": "Питание дома/вне дома",
    "body_complaints": "Жалобы на состояние тела",
    "unpleasant_symptoms": "Неприятные симптомы",
    "serious_illness_surgery": "Серьёзные заболевания/операции",
    "cold_frequency": "Частота простуд",
    "stress": "Стресс/настроение",
    "under_doctor": "На учёте у врача",
    "medications": "Принимаемые препараты",
    "supplements": "Витамины/добавки",
    "doctor_recommendations": "Рекомендации лечащего врача",
    "last_labs_date": "Дата последних анализов",
    "smoking": "Курение",
    "environment_eating": "Пищевое окружение",
    "family_support": "Поддержка семьи в ЗОЖ",
    "frequent_complaints": "Частые жалобы на здоровье",
    "additional_info": "Доп. информация для плана",
}

# Расшифровка select-значений (value → ru label), см. schema.ts.
_OPTION_LABELS: Dict[str, Dict[str, str]] = {
    "work_activity": {"sedentary": "Сидячая", "mixed": "Смешанная", "active": "Активная"},
    "eating_out": {"home": "В основном дома", "mixed": "Смешанно", "out": "В основном вне дома"},
    "cold_frequency": {"rare": "Редко", "few_year": "Несколько раз в год", "often": "Часто"},
    "environment_eating": {
        "healthy": "Больше здорового питания", "mixed": "Смешанно", "unhealthy": "Больше нездорового",
    },
    "family_support": {"supportive": "Поддерживают", "neutral": "Нейтрально", "unsupportive": "Не разделяют"},
}

# Поля типа yesno_text: {"answer": bool, "details": str}.
_YESNO_TEXT_FIELDS = {"under_doctor", "smoking"}


def _format_value(field_id: str, value: Any) -> Optional[str]:
    """Человекочитаемое значение одного поля анкеты, или None если пусто."""
    if value is None:
        return None

    if field_id in _YESNO_TEXT_FIELDS and isinstance(value, dict):
        answer = value.get("answer")
        details = (value.get("details") or "").strip()
        if not answer:
            return "нет"
        return f"да — {details}" if details else "да"

    options = _OPTION_LABELS.get(field_id)
    if options and isinstance(value, str):
        return options.get(value, value)

    text = str(value).strip()
    return text or None


def format_questionnaire_extra(questionnaire_json: Optional[Dict[str, Any]]) -> str:
    """
    Собирает текстовый блок из полей анкеты, не отражённых в структурных колонках
    client_profiles. Пустые/неотвеченные поля пропускаются. Порядок — как в анкете.
    """
    if not isinstance(questionnaire_json, dict):
        return ""

    lines = []
    for field_id, label in _FIELD_LABELS.items():
        if field_id in _EXCLUDED_FIELDS:
            continue  # защита от рассинхрона списков, на случай правки одного без другого
        value = _format_value(field_id, questionnaire_json.get(field_id))
        if value:
            lines.append(f"- {label}: {value}")

    return "\n".join(lines)


def build_summary_input(profile: Optional[Dict[str, Any]]) -> str:
    """
    Полный текст анкеты (структурные поля client_profiles + остаток из questionnaire_json)
    для LLM-саммаризации (agents/client/questionnaire_summary.py). В отличие от промпта
    оркестратора, тут не нужны красивые ru-метки полей типа "пол"/"возраст" — только полнота
    исходных фактов для сжатия моделью.
    """
    profile = profile or {}
    lines: List[str] = []

    if profile.get("birth_date"):
        lines.append(f"Дата рождения: {profile['birth_date']}")
    if profile.get("gender"):
        lines.append(f"Пол: {profile['gender']}")
    if profile.get("goals"):
        lines.append(f"Цель: {profile['goals']}")
    weight = profile.get("weight")
    if weight:
        target = profile.get("target_weight")
        lines.append(f"Вес: {weight} кг" + (f" → цель {target} кг" if target else ""))
    if profile.get("height"):
        lines.append(f"Рост: {profile['height']} см")
    if profile.get("activity_level"):
        lines.append(f"Уровень активности: {profile['activity_level']}")
    if profile.get("chronic_conditions"):
        lines.append("Хронические заболевания: " + ", ".join(profile["chronic_conditions"]))
    if profile.get("allergies"):
        lines.append("Аллергии: " + ", ".join(profile["allergies"]))

    extra = format_questionnaire_extra(profile.get("questionnaire_json"))
    if extra:
        lines.append(extra)

    return "\n".join(lines)
