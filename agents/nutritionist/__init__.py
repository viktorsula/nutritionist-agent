"""
Nutritionist agents — агенты для нутрициолога

Структура (TODO Этап 6):
- state.py — TypedDict для LangGraph State
- orchestrator.py — LangGraph граф оркестрации (ЗАГЛУШКА готова)
- analytics_agent.py — аналитика клиентов (TODO)
- management_agent.py — управление планами/задачами (TODO)

Оркестратор будет решать какой агент вызвать на основе запроса:
- Запрос аналитики → analytics_agent
- Создание/изменение плана → management_agent
- Сводки/отчёты → analytics_agent + summary
"""

from .orchestrator import process_nutritionist_message

__all__ = ['process_nutritionist_message']
