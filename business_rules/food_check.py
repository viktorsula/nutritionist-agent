"""
Смысловая проверка продуктов против назначений клиента (P1-13, шаг 2).

Зачем отдельный модуль, а не расширение `_check_food_forbidden`
─────────────────────────────────────────────────────────────
Подстрочный матчинг отвечает на вопрос «встречается ли слово ограничения в названии
продукта». Нужный же вопрос другой: «подходит ли этот продукт ЭТОМУ клиенту с учётом
его аллергий, непереносимостей, ограничений плана и оговорок нутрициолога». Между ними
пропасть в обе стороны:

- ПРОПУСК: «булгур» не содержит слова «глютен», «кешью» не содержит слова «орехи» —
  подстрока молчит там, где есть реальный риск;
- ЛОЖНОЕ СРАБАТЫВАНИЕ: ограничение «молочные продукты, кроме козьего и овечьего» —
  подстрока запретит козий сыр, хотя нутрициолог его прямо разрешил.

Три исхода вместо «да/нет»
──────────────────────────
`violates` · `ok` · `unclear`. Третий — не отговорка, а честное состояние: если ответа
нет в назначениях нутрициолога и нет в его базе знаний, система НЕ придумывает его из
общего знания модели. «Неясно» НИКОГДА не трактуется как «можно».

Приоритет источников (задан промптом и порядком сборки контекста):
1. явные назначения и оговорки нутрициолога (ограничения плана, аллергии, непереносимости);
2. база знаний нутрициолога (pgvector) — отражает его подход;
3. общее знание модели — только чтобы сказать «неясно», но не чтобы разрешить.

Асимметрия по направлению
─────────────────────────
`direction='incoming'` — клиент уже съел; отменить нельзя, задача — просигналить
нутрициологу. `direction='outgoing'` — ассистент только собирается предложить; здесь
`unclear` приравнивается к «не предлагаем», потому что пропустить запрещённое хуже,
чем перестраховаться (решение владельца).

Отказоустойчивость: сбой модели/поиска НЕ означает «всё чисто». Возвращается `unclear`
с пометкой источника `error` — вызывающий сам решает, что с этим делать, но «зелёного
света» по умолчанию не получает.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VERDICT_VIOLATES = "violates"
VERDICT_OK = "ok"
VERDICT_UNCLEAR = "unclear"

# Сколько фрагментов базы знаний подмешивать в проверку. Немного: задача — дать модели
# позицию нутрициолога по спорному продукту, а не пересказать ему всю библиотеку.
_KB_CHUNKS = 4

# Кэш вердиктов в пределах процесса: рационы повторяются, а набор ограничений у клиента
# меняется редко. Это ОПТИМИЗАЦИЯ, а не корректность — обнуление при рестарте безвредно
# (в отличие от дедупа алертов, где ровно такой кэш был багом, см. P1-7).
_verdict_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_LIMIT = 2000


def _constraints(client_id: str) -> Dict[str, List[str]]:
    """Назначения клиента, против которых проверяем: аллергии, непереносимости, ограничения."""
    from database.queries import get_client_profile, get_active_nutrition_plan

    profile = get_client_profile(client_id) or {}
    plan = get_active_nutrition_plan(client_id) or {}
    plan_json = plan.get("plan_json") if isinstance(plan.get("plan_json"), dict) else {}
    restrictions = plan_json.get("restrictions") or plan.get("restrictions") or []

    return {
        "allergies": [str(x) for x in (profile.get("allergies") or [])],
        "intolerances": [str(x) for x in (profile.get("intolerances") or [])],
        "restrictions": [str(x) for x in restrictions],
    }


def _has_any(constraints: Dict[str, List[str]]) -> bool:
    return any(constraints.get(k) for k in ("allergies", "intolerances", "restrictions"))


def _cache_key(client_id: str, constraints: Dict[str, List[str]], item: str) -> str:
    # В ключ входят сами ограничения: изменил нутрициолог план — старые вердикты не
    # должны переиспользоваться.
    payload = json.dumps([constraints, item.lower().strip()], ensure_ascii=False, sort_keys=True)
    return f"{client_id}:{hash(payload)}"


def _knowledge_context(items: List[str], constraints: Dict[str, List[str]]) -> str:
    """Фрагменты базы знаний нутрициолога по спорным продуктам (пусто при сбое/отсутствии)."""
    try:
        from utils.knowledge import search_knowledge_base

        query = "; ".join(
            [", ".join(items)]
            + [", ".join(constraints[k]) for k in ("allergies", "intolerances", "restrictions")
               if constraints.get(k)]
        )
        chunks = search_knowledge_base(query, match_count=_KB_CHUNKS)
        texts = [(c.get("chunk_text") or "").strip() for c in chunks]
        return "\n\n".join(t for t in texts if t)
    except Exception as e:
        logger.warning(f"food_check: база знаний недоступна: {e}")
        return ""


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Извлекает JSON из ответа модели (со снятием markdown-обёртки)."""
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
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _unclear(item: str, reason: str, source: str = "error") -> Dict[str, Any]:
    return {"item": item, "verdict": VERDICT_UNCLEAR, "reason": reason, "source": source}


def check_food(
    client_id: str,
    items: List[str],
    direction: str = "incoming",
) -> Dict[str, Any]:
    """
    Проверить продукты против назначений клиента.

    Args:
        client_id: UUID клиента.
        items: названия продуктов/блюд.
        direction: 'incoming' (клиент сообщил, что съел) | 'outgoing' (ассистент собирается
            предложить). Влияет на трактовку `unclear` вызывающим, не на сам вердикт.

    Returns:
        {
          "checked": bool,           # выполнялась ли проверка вообще
          "verdicts": [{item, verdict, reason, source}],
          "violations": [...],       # подмножество verdict == 'violates'
          "unclear": [...],          # подмножество verdict == 'unclear'
          "blocked": bool,           # для outgoing: есть violates ИЛИ unclear
        }
    """
    clean_items = [str(i).strip() for i in (items or []) if str(i).strip()]
    empty = {"checked": False, "verdicts": [], "violations": [], "unclear": [], "blocked": False}
    if not clean_items:
        return dict(empty)

    try:
        constraints = _constraints(client_id)
    except Exception as e:
        logger.warning(f"food_check: назначения клиента не получены: {e}")
        # Не знаем ограничений — значит не можем утверждать, что продукт безопасен.
        verdicts = [_unclear(i, "не удалось получить назначения клиента") for i in clean_items]
        return _assemble(verdicts, direction, checked=True)

    if not _has_any(constraints):
        # Ограничений нет вообще — проверять нечего, это не «неясно».
        return dict(empty)

    verdicts: List[Dict[str, Any]] = []
    to_ask: List[str] = []
    for item in clean_items:
        cached = _verdict_cache.get(_cache_key(client_id, constraints, item))
        if cached:
            verdicts.append(dict(cached))
        else:
            to_ask.append(item)

    if to_ask:
        verdicts.extend(_ask_model(client_id, to_ask, constraints))

    return _assemble(verdicts, direction, checked=True)


def _assemble(verdicts: List[Dict[str, Any]], direction: str, checked: bool) -> Dict[str, Any]:
    violations = [v for v in verdicts if v.get("verdict") == VERDICT_VIOLATES]
    unclear = [v for v in verdicts if v.get("verdict") == VERDICT_UNCLEAR]
    # Для исходящих предложений «неясно» блокирует наравне с «нарушает»: пропустить
    # запрещённое в совете хуже, чем лишний раз перестраховаться (решение владельца).
    blocked = bool(violations) or (direction == "outgoing" and bool(unclear))
    return {
        "checked": checked,
        "verdicts": verdicts,
        "violations": violations,
        "unclear": unclear,
        "blocked": blocked,
    }


def _ask_model(
    client_id: str, items: List[str], constraints: Dict[str, List[str]]
) -> List[Dict[str, Any]]:
    """Один вызов модели на все спорные продукты сразу (а не по вызову на продукт)."""
    from prompts import load_prompt
    from utils.llm import call_llm

    kb = _knowledge_context(items, constraints)
    user = json.dumps(
        {
            "products": items,
            "allergies": constraints["allergies"],
            "intolerances": constraints["intolerances"],
            "plan_restrictions": constraints["restrictions"],
            "knowledge_base_excerpts": kb or None,
        },
        ensure_ascii=False,
        indent=2,
    )

    try:
        system = load_prompt("client/food_check")
        resp = call_llm(
            task_type="food_check",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        data = _safe_parse_json(resp.get("content") or "")
    except Exception as e:
        logger.warning(f"food_check: проверка моделью не удалась: {e}")
        data = None

    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        # Модель недоступна или ответила мусором — это НЕ «всё чисто».
        return [_unclear(i, "проверка недоступна") for i in items]

    by_item = {}
    for row in data["results"]:
        if isinstance(row, dict) and row.get("item"):
            by_item[str(row["item"]).lower().strip()] = row

    out: List[Dict[str, Any]] = []
    for item in items:
        row = by_item.get(item.lower().strip())
        verdict = (row or {}).get("verdict")
        if verdict not in (VERDICT_VIOLATES, VERDICT_OK, VERDICT_UNCLEAR):
            # Продукт пропущен в ответе или вердикт неизвестного вида — не додумываем.
            out.append(_unclear(item, "модель не дала вердикта по этому продукту"))
            continue
        result = {
            "item": item,
            "verdict": verdict,
            "reason": str((row or {}).get("reason") or "").strip(),
            "source": str((row or {}).get("source") or "model").strip(),
        }
        out.append(result)
        if len(_verdict_cache) < _CACHE_LIMIT:
            _verdict_cache[_cache_key(client_id, constraints, item)] = dict(result)

    return out


def reset_cache() -> None:
    """Сброс кэша вердиктов (для тестов)."""
    _verdict_cache.clear()
