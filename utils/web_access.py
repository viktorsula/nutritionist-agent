"""
Web Access — веб-поиск через Tavily (Этап 6)

Назначение:
- Поиск актуальной информации в интернете "по запросу" (см. контекст запроса в ТЗ).
- Используется агентами, когда ответа нет в базе знаний/профиле.

Архитектура:
1. web_search(query) → список результатов [{title, url, content}]
2. build_context_from_results(results) → текст для передачи в LLM

Ключи: TAVILY_API_KEY из os.environ.get (НИКОГДА load_dotenv).

TODO v1.1:
- Кэширование частых запросов
- Фильтр доменов (только медицинские/научные источники)
"""

import os
import logging
from typing import Any, Dict, List, Optional

# Импорт SDK (устанавливается через requirements.txt)
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

logger = logging.getLogger(__name__)


# ========================================
# ВЕБ-ПОИСК
# ========================================

def web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Ищет информацию в интернете через Tavily.

    Args:
        query: Поисковый запрос
        max_results: Сколько результатов вернуть
        search_depth: 'basic' (быстро) | 'advanced' (глубже)
        include_domains: Ограничить поиск только этими доменами (первостепенные
            источники из system_settings.trusted_sources). None/[] = без ограничения.

    Returns:
        Список результатов:
        [{"title": str, "url": str, "content": str, "score": float}, ...]
        Пустой список при ошибке или отсутствии ключа (поиск не критичен).
    """
    if TavilyClient is None:
        logger.warning("Tavily SDK не установлен — web_search недоступен")
        return []

    if not query or not query.strip():
        return []

    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        logger.warning("TAVILY_API_KEY не найден — web_search недоступен")
        return []

    try:
        client = TavilyClient(api_key=api_key)
        search_kwargs: Dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        if include_domains:
            search_kwargs["include_domains"] = include_domains

        response = client.search(**search_kwargs)

        results = []
        for item in response.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0.0),
            })

        logger.info(f"web_search('{query[:40]}...'): найдено {len(results)} результатов")
        return results

    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return []


# ========================================
# ХЕЛПЕР: СБОРКА КОНТЕКСТА ДЛЯ LLM
# ========================================

def build_context_from_results(
    results: List[Dict[str, Any]],
    max_chars: int = 4000,
) -> str:
    """
    Собирает текстовый контекст из результатов поиска для передачи в LLM.

    Args:
        results: Результат web_search()
        max_chars: Ограничение длины контекста

    Returns:
        Склеенный текст результатов (с источниками) или пустая строка.
    """
    if not results:
        return ""

    parts: List[str] = []
    total = 0

    for item in results:
        content = item.get("content", "")
        url = item.get("url", "")
        if not content:
            continue
        block = f"{content}\n(Источник: {url})"
        if total + len(block) > max_chars:
            parts.append(block[: max_chars - total])
            break
        parts.append(block)
        total += len(block)

    return "\n\n---\n\n".join(parts)
