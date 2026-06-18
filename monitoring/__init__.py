"""
monitoring — трейсинг и наблюдаемость (Этап 9).

LangFuse-обёртка для трейсинга вызовов LLM. Безопасна к отсутствию SDK/ключей:
если LangFuse не установлен или ключи не заданы — все функции работают как no-op
и НИКОГДА не ломают основной поток.
"""

from .langfuse import trace_llm_call, is_enabled, flush

__all__ = ["trace_llm_call", "is_enabled", "flush"]
