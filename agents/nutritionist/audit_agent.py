"""
Audit Agent (нутрициолог, NEW-1) — проактивный фоновый аудит клиента.

Не по запросу нутрициолога (в отличие от analytics_agent) — вызывается планировщиком
(api/scheduler.py::run_client_audit, по умолчанию 2 раза в неделю). Сверяет заметки
нутрициолога, план питания/ЗОЖ, динамику клиента и базу знаний, ищет расхождения и
возможные ошибки назначений. Переиспользует сбор данных клиента и pgvector-поиск из
analytics_agent (тот же паттерн, что reports.py) — синтез-промпт и формат вывода другие
(структурированные находки JSON, не markdown-анализ).

Находки пишутся в client_audit_findings ТОЛЬКО когда что-то реально найдено — модель
явно инструктирована промптом (nutritionist/audit_system.md) вернуть пустой список,
если расхождений нет; пустой список → ничего не записываем, карточка клиента остаётся
без блока находок. Ничего не эскалируется в Telegram — severity ограничен low/medium,
это материал для планового просмотра, не канал критичных алертов (те — business_rules).
"""

import logging
from typing import Any, Dict, List

from utils.llm import call_llm
from prompts import load_prompt
from database import queries
from .analytics_agent import _gather_client_data, _vector_retrieve, _safe_parse_json

logger = logging.getLogger(__name__)

MAX_FINDINGS_PER_RUN = 3
_VALID_SEVERITY = {"low", "medium"}


def run_audit_for_client(client_id: str) -> int:
    """
    Прогон аудита для одного клиента. Возвращает число записанных находок — 0 (самый
    частый и ожидаемый исход) означает, что расхождений не найдено, а не сбой.
    """
    try:
        client_ctx, _indicators = _gather_client_data(client_id, period_days=30)
    except Exception as e:
        logger.warning(f"audit_agent: сбор данных клиента {client_id} не удался: {e}")
        return 0

    # Заметки нутрициолога не входят в _gather_client_data (тот собирает данные для
    # анализа по запросу) — для аудита это ключевой источник сверки, добираем отдельно.
    try:
        client = queries.get_client_by_id(client_id) or {}
        notes = (client.get("nutritionist_notes") or "").strip()
    except Exception as e:
        logger.warning(f"audit_agent: заметки клиента {client_id} не получены: {e}")
        notes = ""

    knowledge_ctx = _vector_retrieve(_search_queries(notes, client_ctx), client_id)
    findings = _find_discrepancies(client_id, client_ctx, notes, knowledge_ctx)

    written = 0
    for f in findings[:MAX_FINDINGS_PER_RUN]:
        severity = f.get("severity") if f.get("severity") in _VALID_SEVERITY else "medium"
        try:
            queries.insert_audit_finding(
                client_id=client_id,
                title=f["title"],
                description=f["description"],
                severity=severity,
            )
            written += 1
        except Exception as e:
            logger.warning(f"audit_agent: находка не записана client={client_id}: {e}")

    return written


def _search_queries(notes: str, client_ctx: str) -> List[str]:
    """
    Поисковые запросы для pgvector-сверки с базой знаний. Без отдельного PLAN-шага, как
    у analytics_agent (это не ответ на вопрос нутрициолога, а фоновая проверка) — строим
    запросы прямо из имеющихся данных (заметки + сводка клиента).
    """
    candidates = [notes[:200], client_ctx[:200]]
    return [q.strip() for q in candidates if q.strip()][:2]


def _find_discrepancies(
    client_id: str, client_ctx: str, notes: str, knowledge_ctx: str,
) -> List[Dict[str, Any]]:
    system_prompt = _build_system_prompt()
    user_prompt = (
        f"Данные клиента:\n{client_ctx}\n\n"
        f"Заметки нутрициолога:\n{notes or '—'}\n\n"
        f"Материалы базы знаний (по теме данных клиента):\n{knowledge_ctx or '—'}\n\n"
        "Найди расхождения по инструкции системного промпта. Верни JSON."
    )
    try:
        resp = call_llm(
            task_type="client_audit",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        logger.warning(f"audit_agent: LLM-вызов не удался client={client_id}: {e}")
        return []

    parsed = _safe_parse_json(resp.get("content", "")) or {}
    findings = parsed.get("findings") or []
    return [
        f for f in findings
        if isinstance(f, dict) and f.get("title") and f.get("description")
    ]


def _build_system_prompt() -> str:
    try:
        return load_prompt("nutritionist/audit_system")
    except Exception as e:
        logger.error(f"Error loading audit prompt: {e}")
        return (
            'Ты ассистент-аналитик. Ищи расхождения между заметками нутрициолога, планом '
            'и динамикой клиента. Верни JSON {"findings": [...]}. Пустой список, если '
            'расхождений нет. Отвечай на русском.'
        )
