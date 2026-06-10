"""
Client Orchestrator — LangGraph граф для обработки сообщений клиента

Граф:
START
  ↓
load_context (загрузить профиль, план, историю)
  ↓
check_alerts (проверить алерты через medical_rules)
  ↓
dialog_agent (обработать сообщение)
  ↓
format_response (форматировать ответ с алертами)
  ↓
save_to_db (сохранить в conversations + events)
  ↓
END

TODO Этап 6: Добавить роутинг к разным агентам (vision, nutrition, diary)
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from langgraph.graph import StateGraph, END

from .state import ClientState, create_initial_state, extract_response
from .dialog_agent import dialog_node

logger = logging.getLogger(__name__)


# ==========================================
# ГЛАВНАЯ ФУНКЦИЯ (вызывается из router.py)
# ==========================================

def process_client_message(
    client_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any],
    access_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Обрабатывает сообщение от клиента через LangGraph.

    Args:
        client_id: UUID клиента
        message: Текст сообщения
        channel: Канал ('telegram', 'web')
        message_type: Тип ('text', 'photo', 'voice')
        metadata: Дополнительные данные
        access_info: Результат check_access()

    Returns:
        {
            "message": str,
            "agent_used": str,
            "model": str,
            "processing_time_ms": int
        }
    """
    start_time = datetime.now()

    try:
        # Создание графа
        graph = create_client_graph()

        # Создание начального состояния
        initial_state = create_initial_state(
            client_id=client_id,
            message=message,
            channel=channel,
            message_type=message_type,
            metadata=metadata,
            access_info=access_info
        )

        # Выполнение графа
        final_state = graph.invoke(initial_state)

        # Вычисление времени обработки
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        final_state['processing_time_ms'] = int(processing_time)

        # Извлечение ответа
        return extract_response(final_state)

    except Exception as e:
        logger.error(f"Orchestrator error for client {client_id}: {e}", exc_info=True)
        return {
            "message": "Произошла ошибка при обработке сообщения. Попробуйте ещё раз.",
            "error": str(e),
            "agent_used": "error_handler"
        }


# ==========================================
# СОЗДАНИЕ LANGGRAPH ГРАФА
# ==========================================

def create_client_graph():
    """
    Создаёт LangGraph граф для клиента.

    Граф (MVP — простой):
    load_context → check_alerts → dialog_agent → format_response → save_to_db → END

    TODO Этап 6: Добавить роутинг к разным агентам
    """
    workflow = StateGraph(ClientState)

    # Добавление узлов
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("check_alerts", check_alerts_node)
    workflow.add_node("dialog_agent", dialog_node)  # Импорт из dialog_agent.py
    workflow.add_node("format_response", format_response_node)
    workflow.add_node("save_to_db", save_to_db_node)

    # Рёбра (последовательные переходы для MVP)
    workflow.set_entry_point("load_context")
    workflow.add_edge("load_context", "check_alerts")
    workflow.add_edge("check_alerts", "dialog_agent")
    workflow.add_edge("dialog_agent", "format_response")
    workflow.add_edge("format_response", "save_to_db")
    workflow.add_edge("save_to_db", END)

    return workflow.compile()


# ==========================================
# УЗЛЫ ГРАФА
# ==========================================

def load_context_node(state: ClientState) -> ClientState:
    """
    Узел 1: Загрузка контекста клиента из БД.

    Загружает:
    - Профиль клиента (client_profiles)
    - Активный план питания (nutrition_plans)
    - План ЗОЖ (wellness_plans)
    - История диалога (conversations, последние 10 сообщений)
    """
    from database import queries

    client_id = state['client_id']

    try:
        # Профиль клиента
        profile = queries.get_client_profile(client_id)
        state['client_profile'] = profile

        # Активный план питания
        plan = queries.get_active_nutrition_plan(client_id)
        state['active_plan'] = plan

        # План ЗОЖ
        # TODO: Добавить get_active_wellness_plan() в queries.py
        # wellness = queries.get_active_wellness_plan(client_id)
        # state['wellness_plan'] = wellness

        # История диалога (последние 10 сообщений)
        conversations = queries.get_conversations(
            client_id=client_id,
            limit=10
        )

        # Конвертация в формат для LLM
        history = []
        for conv in conversations:
            history.append({
                "role": conv['role'],
                "content": conv['message']
            })

        state['conversation_history'] = history

        logger.info(f"Loaded context for client {client_id}")

    except Exception as e:
        logger.error(f"Error loading context: {e}")
        state['error'] = f"Ошибка загрузки контекста: {str(e)}"

    return state


def check_alerts_node(state: ClientState) -> ClientState:
    """
    Узел 2: Проверка медицинских алертов.

    Вызывает business_rules.medical_rules для проверки:
    - Аллергенов
    - Запрещённых продуктов
    - Резкого набора веса
    - Долгого отсутствия ответов
    """
    from business_rules.medical_rules import check_medical_alerts, determine_routing

    client_id = state['client_id']
    mode = state.get('access_info', {}).get('mode', 'full_program')

    try:
        # Проверка алертов
        # TODO: Извлечь продукты из сообщения (для MVP — пустой список)
        food_items = []  # TODO Этап 6: Извлечение через NER или LLM

        alerts = check_medical_alerts(
            client_id=client_id,
            food_items=food_items,
            mode=mode
        )

        state['alerts'] = alerts

        # Определение маршрутизации
        routing = determine_routing(alerts, mode)
        state['routing'] = routing

        logger.info(f"Checked alerts for client {client_id}: {len(alerts)} found")

    except Exception as e:
        logger.error(f"Error checking alerts: {e}")
        state['alerts'] = []
        state['routing'] = {
            'route_to': 'llm',
            'notify_nutritionist': False
        }

    return state


def format_response_node(state: ClientState) -> ClientState:
    """
    Узел 4: Форматирование финального ответа.

    Добавляет к ответу агента:
    - Информацию об алертах (если есть)
    - Уведомление что нутрициолог в курсе (если notify_nutritionist=True)
    """
    from utils.helpers import format_client_message

    agent_response = state.get('agent_response', '')
    alerts = state.get('alerts', [])
    routing = state.get('routing', {})

    try:
        final_message = format_client_message(
            text=agent_response,
            alerts=alerts,
            nutritionist_notified=routing.get('notify_nutritionist', False)
        )

        state['final_message'] = final_message

        logger.info(f"Formatted response for client {state['client_id']}")

    except Exception as e:
        logger.error(f"Error formatting response: {e}")
        state['final_message'] = agent_response  # Fallback на сырой ответ

    return state


def save_to_db_node(state: ClientState) -> ClientState:
    """
    Узел 5: Сохранение в БД.

    Сохраняет:
    - Сообщение пользователя в conversations
    - Ответ ассистента в conversations
    - События (если есть) в client_events
    """
    from database import queries

    client_id = state['client_id']
    channel = state['channel']
    user_message = state['message']
    assistant_message = state.get('final_message', '')

    try:
        # Сохранение сообщения пользователя
        queries.insert_conversation({
            "client_id": client_id,
            "role": "user",
            "message": user_message,
            "channel": channel,
            "message_type": state.get('message_type', 'text'),
            "metadata": state.get('metadata', {})
        })

        # Сохранение ответа ассистента
        queries.insert_conversation({
            "client_id": client_id,
            "role": "assistant",
            "message": assistant_message,
            "channel": channel,
            "message_type": "text",
            "metadata": {
                "agent_used": state.get('agent_used'),
                "llm_model": state.get('llm_model'),
                "processing_time_ms": state.get('processing_time_ms'),
                "alerts_count": len(state.get('alerts', []))
            }
        })

        # TODO: Сохранение событий в client_events (если есть)
        # if state.get('alerts'):
        #     for alert in state['alerts']:
        #         queries.insert_client_event({...})

        logger.info(f"Saved conversation for client {client_id}")

    except Exception as e:
        logger.error(f"Error saving to DB: {e}")

    return state
