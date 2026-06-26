"""
Таксономия веток входящего сообщения клиента — единый источник правды (Фаза 1).

Определитель (`intake.py`) классифицирует каждый сегмент хода в одну из этих веток.
Здесь — только КОД-правда: валидные ключи + метаданные для маршрутизации и UI.
Инструкция для LLM (как классифицировать) живёт отдельно, в редактируемом файле
prompts/system/intake_determiner.md.

needs_answer:
- ACK    — клиент прислал ДАННЫЕ/отчёт, содержательный ответ не нужен (только подтверждение);
- ANSWER — есть вопрос/просьба, нужен полноценный ответ.
Значение по умолчанию берётся из ветки и повышается до ANSWER, если в сегменте есть вопрос.
"""

from typing import Any, Dict, List, Optional

ACK = "ack"
ANSWER = "answer"

# Технические ключи веток (стабильные; используются в коде и в промпте-определителе).
MEAL = "meal"
LABS = "labs"
WEIGHT = "weight"
WELLBEING = "wellbeing"
NUTRITION_Q = "nutrition_q"
OWN_DATA = "own_data"
DIALOG = "dialog"
DOCUMENT = "document"

# Единый список веток с метаданными. Порядок сохраняется для UI/отладки.
BRANCHES: List[Dict[str, Any]] = [
    {
        "key": MEAL,
        "label_ru": "Приём пищи",
        "default_answer": ACK,
        "handler": "diary/vision (food)",
        "persist": "client_events: calories_logged (+ окно приёма)",
    },
    {
        "key": LABS,
        "label_ru": "Анализы",
        "default_answer": ACK,
        "handler": "lab ingest",
        "persist": "lab_results",
    },
    {
        "key": WEIGHT,
        "label_ru": "Вес/замеры",
        "default_answer": ACK,
        "handler": "diary (weight)",
        "persist": "measurements",
    },
    {
        "key": WELLBEING,
        "label_ru": "Самочувствие",
        "default_answer": ACK,
        "handler": "diary (wellbeing)",
        "persist": "client_events",
    },
    {
        "key": NUTRITION_Q,
        "label_ru": "Вопрос-рекомендация",
        "default_answer": ANSWER,
        "handler": "nutrition_agent (RAG)",
        "persist": "—",
    },
    {
        "key": OWN_DATA,
        "label_ru": "Вопрос о своих данных",
        "default_answer": ANSWER,
        "handler": "dialog + health-данные",
        "persist": "—",
    },
    {
        "key": DIALOG,
        "label_ru": "Общий диалог",
        "default_answer": ANSWER,
        "handler": "dialog_agent",
        "persist": "—",
    },
    {
        "key": DOCUMENT,
        "label_ru": "Документ в карту",
        "default_answer": ACK,
        "handler": "document_agent",
        "persist": "client_documents",
    },
]

_BY_KEY: Dict[str, Dict[str, Any]] = {b["key"]: b for b in BRANCHES}
VALID_BRANCHES = set(_BY_KEY.keys())

# Ветка по умолчанию при неопределённости/сбое — безопаснее ответить, чем молча «принять».
FALLBACK_BRANCH = DIALOG


def is_valid_branch(key: Optional[str]) -> bool:
    """True, если ключ — известная ветка."""
    return key in VALID_BRANCHES


def branch_meta(key: str) -> Dict[str, Any]:
    """Метаданные ветки ({} если неизвестна)."""
    return dict(_BY_KEY.get(key, {}))


def default_answer(key: str) -> str:
    """needs_answer по умолчанию для ветки (ANSWER, если ветка неизвестна)."""
    return _BY_KEY.get(key, {}).get("default_answer", ANSWER)
