"""
Client agents — агенты для работы с клиентами

Структура:
- state.py — TypedDict для LangGraph State
- orchestrator.py — LangGraph граф оркестрации
- dialog_agent.py — диалог с клиентом (ГОТОВ)
- nutrition_agent.py — анализ рациона (TODO Этап 6)
- diary_agent.py — дневник питания (TODO Этап 6)
- vision_agent.py — анализ фото еды (TODO Этап 6)

Оркестратор решает какой агент вызвать на основе типа сообщения:
- Обычный текст → dialog_agent
- Фото еды → vision_agent
- Голосовое → voice + dialog_agent
- Вопрос о рационе → nutrition_agent
"""

from .orchestrator import process_client_message

__all__ = ['process_client_message']
