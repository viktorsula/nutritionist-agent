"""
Ролевой движок агента — общее ядро tool-calling для ЛЮБОЙ роли (клиент/нутрициолог).

`run_agent` не знает ни про клиента, ни про нутрициолога, ни про конкретное состояние.
Он получает готовые: системный промпт, историю, сообщение пользователя, набор инструментов
и их обработчики, и task_type. Всё ролеспецифичное (какие инструменты, какой промпт, какие
права) собирает АДАПТЕР РОЛИ снаружи и передаёт сюда.

Централизация соблюдена:
- модель берётся ТОЛЬКО через `task_type` → `call_llm` → `system_settings.llm_config`
  (кабинет нутрициолога), с код-дефолтом; здесь модель НЕ хардкодится;
- системный промпт готовит адаптер через `load_prompt` (БД-приоритет → файл), не движок.

Клиентские инструменты и цикл `tool_use → tool_result` реализованы в `utils.llm` (Фаза 0)
и работают на Claude; сюда они приходят через `call_llm(tools=..., tool_handlers=...)`.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.llm import call_llm


@dataclass
class AgentResult:
    """Итог одного прохода агента (роле-независимый)."""
    content: str
    model: Optional[str]
    usage: Dict[str, Any]
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


def run_agent(
    *,
    system_prompt: str,
    history: Optional[List[Dict[str, str]]],
    user_message: Optional[str],
    tools: List[Dict[str, Any]],
    tool_handlers: Dict[str, Callable],
    task_type: str,
    history_limit: int = 10,
) -> AgentResult:
    """
    Один проход агента с инструментами.

    Args:
        system_prompt: готовый системный промпт (адаптер уже подставил роль/данные).
        history: последние реплики диалога [{"role": "user|assistant", "content": str}, ...].
        user_message: текущее сообщение пользователя.
        tools: JSON-схемы инструментов (Anthropic-формат) — ТОЛЬКО этой роли.
        tool_handlers: {имя_инструмента: callable(input_dict) -> str|JSON}. Замкнуты на
                       разрешённый scope роли (клиентские — на client_id).
        task_type: ключ в llm_config (модель управляется из кабинета нутрициолога).
        history_limit: сколько последних реплик истории подмешать.

    Returns:
        AgentResult (текст ответа, модель, usage, трейс вызванных инструментов).
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in (history or [])[-history_limit:]:
        if msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message or "—"})

    resp = call_llm(
        task_type=task_type,
        messages=messages,
        tools=tools,
        tool_handlers=tool_handlers,
    )
    return AgentResult(
        content=(resp.get("content") or "").strip(),
        model=resp.get("model"),
        usage=resp.get("usage") or {},
        tool_calls=resp.get("tool_calls") or [],
    )
