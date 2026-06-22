"""
Генерация отчётов по клиенту (каркас).

Агент заполняет шаблон-форму данными клиента (LLM по шаблону). Результат —
{title, content, report_type} — фронт сохраняет в client_reports (под RLS),
нутрициолог правит и выгружает в PDF/TXT.

Типы отчётов (report_type) → шаблон-промпт в prompts/nutritionist/reports/.
Добавление новой формы = новая запись в REPORT_TYPES + .md-шаблон.
"""

import logging
from typing import Any, Dict

from utils.llm import call_llm
from prompts import load_prompt
from .analytics_agent import _gather_client_data  # переиспользуем сбор данных клиента

logger = logging.getLogger(__name__)

# Реестр типов отчётов. Пока один демо-тип; формы добавим по мере поступления.
REPORT_TYPES: Dict[str, Dict[str, str]] = {
    "recommendations": {
        "title": "Рекомендации для подопечного",
        "prompt": "nutritionist/reports/recommendations_for_clients",
    },
}

_SYSTEM_PROMPT = (
    "Ты ассистент нутрициолога. Заполни шаблон отчёта данными конкретного клиента. "
    "Сохраняй структуру и заголовки шаблона, подставляй реальные данные вместо "
    "плейсхолдеров в фигурных скобках. Не выдумывай факты, которых нет в данных — "
    "если данных нет, пиши «нет данных». Тон профессиональный. Отвечай на русском, "
    "верни только готовый текст отчёта (markdown), без пояснений."
)


def list_report_types() -> Dict[str, str]:
    """{report_type: title} — для выбора на фронте."""
    return {k: v["title"] for k, v in REPORT_TYPES.items()}


def generate_report(client_id: str, report_type: str) -> Dict[str, Any]:
    """
    Формирует отчёт по клиенту: шаблон + данные клиента → LLM.

    Returns: {"report_type", "title", "content"}.
    Raises: ValueError при неизвестном report_type.
    """
    meta = REPORT_TYPES.get(report_type)
    if not meta:
        raise ValueError(f"Неизвестный тип отчёта: {report_type}")

    client_ctx, _ = _gather_client_data(client_id, period_days=90)
    template = _load_template(meta["prompt"])

    user_prompt = (
        f"Шаблон отчёта (заполни его):\n{template}\n\n"
        f"Данные клиента:\n{client_ctx}\n\n"
        "Верни заполненный отчёт по структуре шаблона."
    )

    resp = call_llm(
        task_type="analytics",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    return {
        "report_type": report_type,
        "title": meta["title"],
        "content": resp.get("content", "") or "",
    }


def _load_template(prompt_name: str) -> str:
    try:
        return load_prompt(prompt_name)
    except Exception as e:
        logger.error(f"Report template '{prompt_name}' not found: {e}")
        return (
            "# Отчёт\n\nСформируй структурированный отчёт по клиенту: итоги, "
            "достижения, рекомендации по питанию и образу жизни, дальнейшие шаги."
        )
