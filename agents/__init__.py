"""
Agents — мультиагентная система на базе LangGraph

Архитектура:
- router.py — входной маршрутизатор (роль → ветка)
- client/ — агенты для клиента (dialog, nutrition, diary, vision)
- nutritionist/ — агенты для нутрициолога (analytics, management)

Каждая ветка имеет:
- state.py — TypedDict для LangGraph State
- orchestrator.py — LangGraph граф оркестрации
- *_agent.py — специализированные агенты

Интеграция:
- utils/llm.py — вызовы LLM
- business_rules/ — детерминированные проверки
- database/queries.py — работа с БД
- prompts/ — system prompts для агентов
"""

from .router import route_message

__all__ = ['route_message']
