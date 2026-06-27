"""
Таксономия веток входящего сообщения клиента — единый источник правды.

Двухуровневое дерево (решение 27 июня, упрощение 8→3):

ВЕРХНИЙ УРОВЕНЬ — что возвращает определитель (`intake.py`). Три семантически
разных намерения, между которыми LLM выбирает устойчиво:
- INTAKE  (A) — клиент СООБЩАЕТ данные о дне (еда, вода, самочувствие, анализы,
                вес/объёмы, документ). Ответ — подтверждение («принято»), дешёвая модель.
- PROFILE (B) — клиент СПРАШИВАЕТ о себе (свои данные/динамика/история/план/задачи)
                ИЛИ просто общается. Ассистент отвечает, ЗНАЯ клиента (профиль + история).
- ADVICE  (C) — клиент просит СОВЕТ по питанию (что приготовить из имеющихся продуктов;
                текст-список / фото холодильника / PDF). Нужна сильная модель + RAG + vision.

НИЖНИЙ УРОВЕНЬ — под-типы ветки INTAKE: КУДА сохранять. Определяются ПОСЛЕ
определителя, детерминированно (якоря: тип фото из classify_image, числовые
паттерны, reuse diary-экстрактора) — БЕЗ дорогого LLM. См. INTAKE_SUBTYPES.

needs_answer:
- ACK    — клиент прислал ДАННЫЕ/отчёт, содержательный ответ не нужен (подтверждение);
- ANSWER — есть вопрос/просьба/общение, нужен полноценный ответ.
Значение по умолчанию берётся из ветки и повышается до ANSWER, если в сегменте есть вопрос.
"""

from typing import Any, Dict, List, Optional

ACK = "ack"
ANSWER = "answer"
CLARIFY = "clarify"  # система не уверена → задать клиенту уточняющий вопрос (данные не пишем)

# ── Верхнеуровневые ветки (их возвращает определитель) ──────────────────────
INTAKE = "intake"    # A — входящая информация (отчёт о дне)
PROFILE = "profile"  # B — запрос по профилю + общий диалог
ADVICE = "advice"    # C — совет по питанию

BRANCHES: List[Dict[str, Any]] = [
    {
        "key": INTAKE,
        "label_ru": "Входящая информация",
        "default_answer": ACK,
        "handler": "intake (diary / vision / labs / document)",
        "persist": "по под-типу — см. INTAKE_SUBTYPES",
    },
    {
        "key": PROFILE,
        "label_ru": "Запрос по профилю / диалог",
        "default_answer": ANSWER,
        "handler": "dialog + данные профиля",
        "persist": "—",
    },
    {
        "key": ADVICE,
        "label_ru": "Совет по питанию",
        "default_answer": ANSWER,
        "handler": "nutrition_agent (RAG + vision)",
        "persist": "—",
    },
]

_BY_KEY: Dict[str, Dict[str, Any]] = {b["key"]: b for b in BRANCHES}
VALID_BRANCHES = set(_BY_KEY.keys())

# Ветка по умолчанию при неопределённости/сбое: безопаснее ОБЩАТЬСЯ зная клиента
# (PROFILE), чем молча «принять» возможный вопрос как данные.
FALLBACK_BRANCH = PROFILE

# ── Под-типы ветки INTAKE — КУДА сохранять (нижний уровень) ──────────────────
MEAL = "meal"
WATER = "water"
WEIGHT = "weight"
WELLBEING = "wellbeing"
LABS = "labs"
DOCUMENT = "document"

INTAKE_SUBTYPES: List[Dict[str, Any]] = [
    {"key": MEAL, "label_ru": "Приём пищи", "persist": "client_events: calories_logged"},
    {"key": WATER, "label_ru": "Вода", "persist": "client_events: water_logged"},
    {"key": WEIGHT, "label_ru": "Вес/замеры", "persist": "measurements"},
    {"key": WELLBEING, "label_ru": "Самочувствие", "persist": "client_events"},
    {"key": LABS, "label_ru": "Анализы", "persist": "lab_results"},
    {"key": DOCUMENT, "label_ru": "Документ", "persist": "client_documents"},
]

_SUBTYPE_BY_KEY: Dict[str, Dict[str, Any]] = {s["key"]: s for s in INTAKE_SUBTYPES}
VALID_INTAKE_SUBTYPES = set(_SUBTYPE_BY_KEY.keys())


def is_valid_branch(key: Optional[str]) -> bool:
    """True, если ключ — известная верхнеуровневая ветка."""
    return key in VALID_BRANCHES


def branch_meta(key: str) -> Dict[str, Any]:
    """Метаданные ветки ({} если неизвестна)."""
    return dict(_BY_KEY.get(key, {}))


def default_answer(key: str) -> str:
    """needs_answer по умолчанию для ветки (ANSWER, если ветка неизвестна)."""
    return _BY_KEY.get(key, {}).get("default_answer", ANSWER)


def label_ru(key: str) -> str:
    """Человекочитаемое название ветки (для квитанции/UI)."""
    return _BY_KEY.get(key, {}).get("label_ru", key)


def is_valid_intake_subtype(key: Optional[str]) -> bool:
    """True, если ключ — известный под-тип ветки INTAKE."""
    return key in VALID_INTAKE_SUBTYPES


def intake_subtype_meta(key: str) -> Dict[str, Any]:
    """Метаданные под-типа INTAKE ({} если неизвестен)."""
    return dict(_SUBTYPE_BY_KEY.get(key, {}))
