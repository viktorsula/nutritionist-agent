"""
Utils — вспомогательные модули для агентов

Содержит:
- llm.py: Мультипровайдерный LLM клиент (Groq, Claude, Gemini) ✅
- helpers.py: Вспомогательные функции ✅
- vision.py: Анализ фото через Gemini Flash ✅
- voice.py: Транскрипция голоса через Whisper ✅
- web_access.py: Веб-поиск через Tavily ✅
- knowledge.py: Семантический поиск по pgvector (ada-002) ✅
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
from .knowledge import (
    get_embedding,
    search_knowledge_base,
    search_client_documents,
    build_context_from_chunks,
)
from .vision import analyze_image, analyze_food_plate, extract_ingredient_names
from .voice import transcribe_voice
from .web_access import web_search, build_context_from_results

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
    'translate_if_needed',

    # knowledge.py
    'get_embedding',
    'search_knowledge_base',
    'search_client_documents',
    'build_context_from_chunks',

    # vision.py
    'analyze_image',
    'analyze_food_plate',
    'extract_ingredient_names',

    # voice.py
    'transcribe_voice',

    # web_access.py
    'web_search',
    'build_context_from_results',
]
