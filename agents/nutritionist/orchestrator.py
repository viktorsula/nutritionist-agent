"""
Nutritionist Orchestrator — обработка сообщений нутрициолога

TODO Этап 6: Реализовать полноценный граф с агентами
Сейчас: Простая заглушка, направляющая к веб-интерфейсу

Будущий граф (Этап 6):
START
  ↓
parse_request (определить тип запроса)
  ↓
┌────────────────┬──────────────────┐
│                │                  │
analytics_agent  management_agent   summary_agent
│                │                  │
└────────────────┴──────────────────┘
  ↓
format_response
  ↓
save_to_db
  ↓
END
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def process_nutritionist_message(
    nutritionist_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Обрабатывает сообщение от нутрициолога.

    TODO Этап 6: Полноценный граф с аналитикой и управлением
    Сейчас: Направление к веб-интерфейсу

    Args:
        nutritionist_id: UUID нутрициолога
        message: Текст сообщения
        channel: Канал ('telegram', 'web')
        message_type: Тип сообщения
        metadata: Дополнительные данные

    Returns:
        {
            "message": str,
            "agent_used": str
        }
    """

    logger.info(
        f"Nutritionist message: id={nutritionist_id}, "
        f"channel={channel}, type={message_type}"
    )

    # TODO Этап 6: Реализовать граф
    # Сейчас — заглушка

    if channel == 'telegram':
        response_message = (
            "Привет! Для работы с клиентами используй веб-интерфейс:\n"
            "https://nutritionist-agent-gvxp.onrender.com\n\n"
            "Там доступны:\n"
            "• Реестр клиентов\n"
            "• Аналитика и сводки\n"
            "• Управление планами\n"
            "• История диалогов\n\n"
            "Telegram интерфейс для нутрициолога в разработке."
        )
    else:
        # Веб-интерфейс — полнофункциональный
        response_message = process_web_request(nutritionist_id, message)

    return {
        "message": response_message,
        "agent_used": "nutritionist_stub"
    }


def process_web_request(nutritionist_id: str, message: str) -> str:
    """
    Обработка запроса из веб-интерфейса.

    TODO Этап 6: Парсинг интента и вызов агентов
    """

    # Простой разбор интента (для MVP)
    message_lower = message.lower()

    if any(word in message_lower for word in ['сводка', 'отчёт', 'анализ', 'прогресс']):
        return (
            "Для получения аналитики используй раздел 'Аналитика' в меню.\n"
            "Выбери клиента и период — система сгенерирует подробный отчёт."
        )

    elif any(word in message_lower for word in ['план', 'задача', 'создать', 'изменить']):
        return (
            "Для управления планами и задачами используй раздел 'Клиенты'.\n"
            "Выбери клиента → Планы → Создать/Редактировать."
        )

    elif any(word in message_lower for word in ['реестр', 'список', 'клиенты']):
        return (
            "Реестр клиентов доступен в разделе 'Реестр'.\n"
            "Там можно фильтровать по статусам, видеть алерты и активность."
        )

    else:
        return (
            "Используй навигационное меню веб-интерфейса:\n"
            "• Реестр — список всех клиентов\n"
            "• Аналитика — отчёты и сводки\n"
            "• Настройки — конфигурация системы\n\n"
            "Или задай более конкретный вопрос."
        )


# TODO Этап 6: Реализовать полноценный граф

# from langgraph.graph import StateGraph, END
# from typing import TypedDict
#
# class NutritionistState(TypedDict):
#     nutritionist_id: str
#     message: str
#     intent: str  # 'analytics', 'management', 'summary'
#     client_id: Optional[str]
#     response: str
#
# def create_nutritionist_graph():
#     workflow = StateGraph(NutritionistState)
#
#     workflow.add_node("parse_request", parse_request_node)
#     workflow.add_node("analytics_agent", analytics_agent_node)
#     workflow.add_node("management_agent", management_agent_node)
#     workflow.add_node("format_response", format_response_node)
#
#     workflow.set_entry_point("parse_request")
#
#     # Условная маршрутизация
#     workflow.add_conditional_edges(
#         "parse_request",
#         route_by_intent,
#         {
#             "analytics": "analytics_agent",
#             "management": "management_agent",
#             "unknown": "format_response"
#         }
#     )
#
#     workflow.add_edge("analytics_agent", "format_response")
#     workflow.add_edge("management_agent", "format_response")
#     workflow.add_edge("format_response", END)
#
#     return workflow.compile()
