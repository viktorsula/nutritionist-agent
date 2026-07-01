"""
Present-слой: тёплый ответ клиенту ИЗ IntakeRecord (Слайс 3).

Один общий механизм для diary и vision: факты берутся из канонической записи (а не из
ad-hoc словарей каждого агента), проза генерится dialog-LLM. Проза в логику/БД НЕ
возвращается — источник правды остаётся структурой. Каждый путь передаёт свой промпт
(client/diary_system | client/vision_system) — тон раздельный и редактируемый нутрициологом.

Предупреждения безопасности (аллерген/отклонения) добавляет позже format_response_node
оркестратора из state['alerts']; здесь — дружелюбное подтверждение записанного.
"""

import logging
from typing import Any, Dict, List, Optional

from utils.llm import call_llm
from prompts import load_prompt
from .intake_schema import normalize

logger = logging.getLogger(__name__)


def present(state: Dict[str, Any], record: Dict[str, Any], *, prompt_name: str) -> str:
    """Тёплый ответ из IntakeRecord по заданному (редактируемому) системному промпту."""
    record = normalize(record)
    try:
        system = _system_prompt(state, prompt_name)
        # Долговременная память — сводка прошлых разговоров (как в dialog/nutrition).
        summary = (state.get("conversation_summary") or "").strip()
        if summary:
            system += "\n\n## Память о клиенте (сводка прошлых разговоров)\n" + summary
        facts = _facts_from_record(state, record)
        # Краткосрочная память — последние реплики диалога перед фактами текущего хода,
        # чтобы ответ был в контексте (без повторного приветствия/противоречий).
        messages = [{"role": "system", "content": system}]
        for msg in (state.get("conversation_history") or [])[-6:]:
            if msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": facts})
        resp = call_llm(task_type="dialog", messages=messages)
        state["llm_model"] = resp.get("model")
        state["llm_usage"] = resp.get("usage", {})
        return resp["content"]
    except Exception as e:
        logger.error(f"present failed: {e}", exc_info=True)
        return _fallback(record)


def _system_prompt(state: Dict[str, Any], prompt_name: str) -> str:
    profile = state.get("client_profile") or {}
    plan = state.get("active_plan") or {}
    try:
        template = load_prompt(prompt_name)
        return template.format(
            client_name=profile.get("name", "Клиент"),
            restrictions=format_list(plan.get("restrictions")),
            allergies=format_allergies(profile),
            language="русский",  # TODO: определять из profile/channel
        )
    except Exception as e:
        logger.error(f"present system prompt error: {e}")
        return (
            "Ты ИИ-ассистент нутрициолога. Тепло подтверди, что записал сообщение клиента, "
            "кратко перечисли записанное и пригласи дополнить. Не выдумывай. Отвечай на русском."
        )


def _facts_from_record(state: Dict[str, Any], record: Dict[str, Any]) -> str:
    """Человекочитаемые факты ИЗ записи (kind-aware) + алерты из state — для dialog-LLM."""
    kind = record.get("kind")
    lines = [f"ТИП: {kind}", f"Сообщение клиента: {state.get('message', '') or '—'}"]

    if kind == "meal":
        meal = record.get("meal") or {}
        if meal.get("dish_name"):
            lines.append(f"Блюдо: {meal['dish_name']}")
        names = [it["name"] for it in (meal.get("items") or []) if it.get("name")]
        lines.append("Записанный состав: " + (", ".join(names) if names else "—"))
        total = meal.get("total") or {}
        if total.get("kcal"):
            lines.append(
                f"Примерно КБЖУ (справочно): {total.get('kcal')} ккал, "
                f"Б {total.get('protein_g') or 0} / Ж {total.get('fat_g') or 0} / У {total.get('carb_g') or 0}"
            )
    elif kind == "water":
        lines.append(f"Записано воды: {record.get('water_ml')} мл")
    elif kind == "weight":
        lines.append(f"Записанный вес: {record.get('weight_kg')} кг")
    elif kind == "wellbeing":
        wb = record.get("wellbeing") or {}
        lines.append(f"Самочувствие: {wb.get('status', '')}; причина: {wb.get('reason') or '—'}")
    elif kind == "lab":
        labs = state.get("saved_labs") or record.get("labs") or []
        recorded = ", ".join(
            f"{l['indicator']} {l['value']}{(' ' + l['unit']) if l.get('unit') else ''}" for l in labs
        )
        lines.append(f"Записанные анализы: {recorded or '—'}")
        lines.append("Не интерпретируй медицински — просто подтверди, что внёс в карту.")

    alerts = state.get("alerts") or []
    if alerts:
        lines.append("Отклонения/алерты (упомяни мягко, аллерген — серьёзно):")
        for a in alerts:
            lines.append(f"- [{a.get('severity', 'low')}] {a.get('type')}: {a.get('message', '')}")

    lines.append("\nСформулируй короткий тёплый ответ клиенту.")
    return "\n".join(lines)


def clarify_from_uncertainties(state: Dict[str, Any], record: Dict[str, Any]) -> str:
    """
    ОДИН уточняющий вопрос на ВСЕ неясные моменты записи (не серия вопросов).

    Собирает `record['uncertainties']` в одно сообщение с нумерованным списком. Если
    список пуст (тема/факт совсем не разобраны) — возвращает '' (вызывающий применит
    общий clarify_request оркестратора).
    """
    unc = [str(u).strip() for u in (record or {}).get("uncertainties") or [] if str(u).strip()]
    if not unc:
        return ""
    name = (state.get("client_profile") or {}).get("name") or ""
    prefix = f"{name}, уточни" if name else "Уточни"
    items = "; ".join(f"{i + 1}) {u}" for i, u in enumerate(unc))
    return f"{prefix}, пожалуйста: {items}?"


def _fallback(record: Dict[str, Any]) -> str:
    """Детерминированное подтверждение, если LLM недоступен."""
    acks = {
        "meal": "Спасибо, записал твой приём пищи ✅ Если что-то не так — поправь.",
        "water": "Записал воду ✅ Так удобнее следить за нормой за день.",
        "weight": "Записал твой вес ✅ Продолжай отмечать — так виднее динамика.",
        "wellbeing": "Спасибо, что поделился самочувствием 🙏 Я всё зафиксировал.",
        "lab": "Записал результаты анализов в твою карту ✅ Нутрициолог их увидит.",
    }
    return acks.get(record.get("kind"), "Принято ✅")


def format_list(values: Optional[List[Any]]) -> str:
    if not values:
        return "Нет"
    return ", ".join(str(v) for v in values)


def format_allergies(profile: Dict[str, Any]) -> str:
    allergies = (profile or {}).get("allergies") or []
    if not allergies:
        return "Нет"
    names = [a.get("name", a) if isinstance(a, dict) else a for a in allergies]
    return ", ".join(str(n) for n in names)
