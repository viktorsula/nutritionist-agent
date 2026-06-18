"""
Nutritionist agents — агенты для нутрициолога (Этап 6 Часть B).

Структура:
- state.py            — NutritionistState (TypedDict) + helpers
- orchestrator.py     — LangGraph граф: parse_request → [analytics|management|help]
                        → format_response → save_to_db
- analytics_agent.py  — аналитика клиентов/базы (Claude, read-only)
- management_agent.py — управление планами/задачами/статусами через подтверждение

Оркестратор определяет intent и вызывает агента:
- analytics  → analytics_agent (сводки, динамика, паттерны, статистика по базе)
- management → management_agent (создать/изменить план/задачу/статус; запись через
               двухшаговое подтверждение)
- help       → подсказка по возможностям
"""

from .orchestrator import process_nutritionist_message

__all__ = ['process_nutritionist_message']
