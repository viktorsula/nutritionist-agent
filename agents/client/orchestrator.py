"""
Client Orchestrator — LangGraph граф для обработки сообщений клиента

Граф:
START
  ↓
ingest         (голос → текст через Whisper, если message_type == 'voice')
  ↓
load_context   (профиль, план, история)
  ↓
route          (определяет ветку: photo / diary / nutrition / dialog)
  ↓ [conditional]
  ├── photo      → vision_agent   (фото еды)
  ├── diary      → diary_agent    (факт: еда/вес/самочувствие)
  ├── nutrition  → nutrition_agent (вопрос о рационе/плане)
  └── dialog     → dialog_agent   (общий разговор)
  ↓
format_response (добавить алерты/уведомление)
  ↓
save_to_db     (conversations; события пишут сами агенты)
  ↓
END
"""

import json
import logging
from typing import Dict, Any
from datetime import datetime

from langgraph.graph import StateGraph, END

from .state import ClientState, create_initial_state, extract_response
from .dialog_agent import dialog_node
from .vision_agent import vision_node
from .diary_agent import diary_node
from .nutrition_agent import nutrition_node
from utils.llm import call_llm

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
    Создаёт LangGraph граф для клиента с роутингом к агентам.

    ingest → load_context → route → [vision|diary|nutrition|dialog]
           → format_response → save_to_db → END
    """
    workflow = StateGraph(ClientState)

    # Узлы
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("route", route_node)
    workflow.add_node("vision_agent", vision_node)
    workflow.add_node("diary_agent", diary_node)
    workflow.add_node("nutrition_agent", nutrition_node)
    workflow.add_node("dialog_agent", dialog_node)
    workflow.add_node("format_response", format_response_node)
    workflow.add_node("save_to_db", save_to_db_node)

    # Линейная часть до маршрутизации
    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "load_context")
    workflow.add_edge("load_context", "route")

    # Условный роутинг к агентам (по state['route'])
    workflow.add_conditional_edges(
        "route",
        _select_route,
        {
            "vision": "vision_agent",
            "diary": "diary_agent",
            "nutrition": "nutrition_agent",
            "dialog": "dialog_agent",
        },
    )

    # Все агенты сходятся в форматирование и сохранение
    for agent in ("vision_agent", "diary_agent", "nutrition_agent", "dialog_agent"):
        workflow.add_edge(agent, "format_response")

    workflow.add_edge("format_response", "save_to_db")
    workflow.add_edge("save_to_db", END)

    return workflow.compile()


def _select_route(state: ClientState) -> str:
    """Path-функция для add_conditional_edges: возвращает ветку из state['route']."""
    return state.get('route', 'dialog')


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


def ingest_node(state: ClientState) -> ClientState:
    """
    Узел входа: если пришёл голос — распознаём его в текст (Whisper).

    Контракт голоса: message_type == 'voice', metadata['audio_bytes'] = bytes,
    metadata['audio_name'] (опц.) — имя файла с расширением. После распознавания
    сообщение становится обычным текстом и идёт в общий роутинг.
    """
    if state.get('message_type') != 'voice':
        return state

    metadata = state.get('metadata') or {}
    audio_bytes = metadata.get('audio_bytes')

    if not audio_bytes:
        # Голос заявлен, но аудио нет — оставляем как есть, route разрулит в dialog
        return state

    try:
        from utils.voice import transcribe_voice

        text = transcribe_voice(
            audio_bytes,
            file_name=metadata.get('audio_name', 'voice.ogg'),
        )
        if text:
            state['message'] = text
            state['message_type'] = 'text'  # дальше обрабатываем как текст
            metadata['transcribed'] = True
            state['metadata'] = metadata
            logger.info(f"Transcribed voice for client {state['client_id']}: {len(text)} chars")
        else:
            state['message'] = state.get('message', '')
            logger.info("Voice transcription returned empty text")

    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        # Не валим обработку — пойдём в dialog с исходным (возможно пустым) текстом

    return state


def route_node(state: ClientState) -> ClientState:
    """
    Узел маршрутизации: определяет ветку обработки и кладёт её в state['route'].

    - photo (есть изображение) → 'vision'
    - текст → классификатор (Groq): 'diary' | 'nutrition' | 'dialog'
    """
    message_type = state.get('message_type', 'text')

    # Фото → vision (без LLM)
    if message_type == 'photo':
        state['route'] = 'vision'
        return state

    # Текст → классификация интента
    state['route'] = _classify_text(state.get('message', ''))
    logger.info(f"Routed client {state['client_id']} to '{state['route']}'")
    return state


CLASSIFIER_PROMPT = """Ты — маршрутизатор сообщений клиента нутрициолога. Определи тип сообщения.

Верни СТРОГО валидный JSON без markdown: {"route": "diary | nutrition | dialog"}

- diary — клиент сообщает ФАКТ о себе: что поел/ест, свой вес, своё самочувствие.
- nutrition — ВОПРОС про рацион, план, меню, продукты, его анализы, цель.
- dialog — общий разговор, поддержка, благодарность, всё остальное.

Только JSON, ничего больше."""


def _classify_text(message: str) -> str:
    """Грубая классификация текстового сообщения через дешёвый LLM (Groq)."""
    message = (message or '').strip()
    if not message:
        return 'dialog'

    try:
        response = call_llm(
            task_type='dialog',
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": message},
            ],
        )
        parsed = _safe_parse_json(response.get('content', ''))
        route = (parsed or {}).get('route', 'dialog')
        if route not in ('diary', 'nutrition', 'dialog'):
            return 'dialog'
        return route

    except Exception as e:
        logger.error(f"Classifier error: {e}")
        return 'dialog'


def _safe_parse_json(text: str):
    """Извлекает JSON из ответа модели (со снятием markdown-обёртки)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


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
        # Сохранение сообщения пользователя.
        # Из metadata убираем бинарные вложения (фото/аудио), их нельзя писать в JSONB.
        queries.save_conversation(
            client_id=client_id,
            role="user",
            message_text=user_message,
            channel=channel,
            metadata={
                "message_type": state.get('message_type', 'text'),
                **_sanitize_metadata(state.get('metadata', {})),
            },
        )

        # Сохранение ответа ассистента
        queries.save_conversation(
            client_id=client_id,
            role="assistant",
            message_text=assistant_message,
            channel=channel,
            metadata={
                "agent_used": state.get('agent_used'),
                "llm_model": state.get('llm_model'),
                "processing_time_ms": state.get('processing_time_ms'),
                "alerts_count": len(state.get('alerts', [])),
            },
        )

        # Примечание: структурированные события (calories_logged и т.п.) пишет сам
        # агент (например, vision_agent._log_meal_event), здесь — только диалог.

        logger.info(f"Saved conversation for client {client_id}")

    except Exception as e:
        logger.error(f"Error saving to DB: {e}")

    return state


def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Убирает из metadata бинарные/несериализуемые поля перед записью в JSONB.

    Бинарные вложения (image_bytes, audio_bytes, file_bytes) заменяются на флаг
    наличия, чтобы не ломать JSON и не раздувать таблицу.
    """
    if not metadata:
        return {}

    binary_keys = ('image_bytes', 'audio_bytes', 'file_bytes')
    cleaned: Dict[str, Any] = {}

    for key, value in metadata.items():
        if key in binary_keys:
            cleaned[f"has_{key}"] = bool(value)
        elif isinstance(value, (bytes, bytearray)):
            cleaned[f"has_{key}"] = True
        else:
            cleaned[key] = value

    return cleaned
