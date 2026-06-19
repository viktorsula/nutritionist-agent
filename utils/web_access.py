"""
Web Access — веб-поиск через серверный инструмент Claude (web_search)

Назначение:
- Поиск актуальной информации в интернете "по запросу" (см. контекст запроса в ТЗ).
- Используется агентами, когда ответа нет в базе знаний/профиле.

Архитектура (Этап 6, переведено с Tavily на встроенный инструмент Claude):
- build_web_search_tool(allowed_domains, max_uses) → dict инструмента для Claude.
- Инструмент передаётся в call_llm(..., tools=[tool]); Anthropic САМ выполняет
  поиск на своей стороне и возвращает ответ с цитатами. Отдельный поисковый
  провайдер и ключ (TAVILY_API_KEY) больше не нужны.
- Контроль источников сохранён: allowed_domains — whitelist доменов из
  system_settings.trusted_sources (редактирует нутрициолог).

Требование: web search должен быть включён в Claude Console (Settings → Privacy)
на уровне организации. Без этого инструмент вернёт ошибку в рантайме.

Цена: $10 за 1000 поисков + токены (usage.web_search_requests в ответе call_llm).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Версия серверного инструмента web search (базовый поиск, без code execution).
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"


# ========================================
# ПОСТРОЕНИЕ ИНСТРУМЕНТА WEB SEARCH ДЛЯ CLAUDE
# ========================================

def build_web_search_tool(
    allowed_domains: Optional[List[str]] = None,
    max_uses: int = 3,
    blocked_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Формирует определение серверного инструмента web_search для Claude.

    Передаётся в call_llm(..., tools=[build_web_search_tool(...)]); поиск
    выполняется на стороне Anthropic, ответ возвращается с цитатами.

    Args:
        allowed_domains: Whitelist доменов (первостепенные/доверенные источники
            из system_settings.trusted_sources). None/[] = без ограничения.
        max_uses: Максимум поисков за один запрос (баланс цена/латентность).
        blocked_domains: Чёрный список доменов. Нельзя использовать вместе
            с allowed_domains (API принимает только один из фильтров).

    Returns:
        dict определения инструмента для Anthropic Messages API.
    """
    tool: Dict[str, Any] = {
        "type": WEB_SEARCH_TOOL_TYPE,
        "name": "web_search",
        "max_uses": max_uses,
    }

    # API не допускает одновременно allowed_domains и blocked_domains.
    if allowed_domains:
        tool["allowed_domains"] = allowed_domains
    elif blocked_domains:
        tool["blocked_domains"] = blocked_domains

    return tool
