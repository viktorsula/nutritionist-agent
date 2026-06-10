"""
Utils — вспомогательные модули для агентов

Содержит:
- llm.py: Мультипровайдерный LLM клиент (Groq, Claude, Gemini) ✅
- helpers.py: Вспомогательные функции ✅
- vision.py: Анализ фото через Gemini Flash (TODO: Этап 6)
- voice.py: Транскрипция голоса через Whisper (TODO: Этап 6)
- web_access.py: Веб-доступ к источникам знаний (TODO: Этап 6)
- knowledge.py: Работа с pgvector базой знаний (TODO: Этап 6)
"""

from .llm import call_llm, get_model_config, list_available_providers, list_task_types
from .helpers import (
    format_client_message,
    parse_datetime,
    format_date_for_client,
    validate_ingredients,
    calculate_nutrition,
    estimate_calories,
    generate_summary,
    format_analytics_report,
    detect_language,
    translate_if_needed
)

__all__ = [
    # llm.py
    'call_llm',
    'get_model_config',
    'list_available_providers',
    'list_task_types',

    # helpers.py
    'format_client_message',
    'parse_datetime',
    'format_date_for_client',
    'validate_ingredients',
    'calculate_nutrition',
    'estimate_calories',
    'generate_summary',
    'format_analytics_report',
    'detect_language',
    'translate_if_needed'
]
