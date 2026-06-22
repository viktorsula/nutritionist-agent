"""
Nutritionist Orchestrator — LangGraph граф для обработки сообщений нутрициолога.

Граф (общий для Telegram и web):
START
  ↓
parse_request   (intent + клиент по имени; детект подтверждения pending_action)
  ↓ [conditional по intent]
  ├── analytics   → analytics_agent  (Claude, read-only)
  ├── management  → management_agent  (запись через подтверждение)
  ├── confirm     → management_agent  (исполнение pending_action)
  ├── cancel      → management_agent  (отмена)
  └── help        → help_node         (подсказка по возможностям)
  ↓
format_response
  ↓
save_to_db      (conversations: thread нутрициолога, pending_action в metadata)
  ↓
END

Запись в БД — только через двухшаговое подтверждение (см. management_agent).
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from langgraph.graph import StateGraph, END

from utils.llm import call_llm
from database import queries
from .state import (
    NutritionistState,
    create_initial_state,
    extract_response,
    nutritionist_thread_id,
)
from .analytics_agent import analytics_node
from .management_agent import management_node

logger = logging.getLogger(__name__)


# ==========================================
# ГЛАВНАЯ ФУНКЦИЯ (вызывается из router.py)
# ==========================================

def process_nutritionist_message(
    nutritionist_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Обрабатывает сообщение от нутрициолога через LangGraph (Telegram и web).

    Returns:
        {"message": str, "agent_used": str, "model": str, "intent": str, ...}
    """
    start_time = datetime.now()

    try:
        graph = create_nutritionist_graph()
        initial_state = create_initial_state(
            nutritionist_id=nutritionist_id,
            message=message,
            channel=channel,
            message_type=message_type,
            metadata=metadata,
        )

        final_state = graph.invoke(initial_state)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        final_state["processing_time_ms"] = int(processing_time)

        return extract_response(final_state)

    except Exception as e:
        logger.error(f"Nutritionist orchestrator error for {nutritionist_id}: {e}", exc_info=True)
        return {
            "message": "Произошла ошибка при обработке запроса. Попробуйте ещё раз.",
            "error": str(e),
            "agent_used": "error_handler",
        }


# ==========================================
# СОЗДАНИЕ LANGGRAPH ГРАФА
# ==========================================

def create_nutritionist_graph():
    """parse_request → [analytics|management|help] → format_response → save_to_db → END"""
    workflow = StateGraph(NutritionistState)

    workflow.add_node("parse_request", parse_request_node)
    workflow.add_node("analytics_agent", analytics_node)
    workflow.add_node("management_agent", management_node)
    workflow.add_node("help_node", help_node)
    workflow.add_node("format_response", format_response_node)
    workflow.add_node("save_to_db", save_to_db_node)

    workflow.set_entry_point("parse_request")

    workflow.add_conditional_edges(
        "parse_request",
        _route_by_intent,
        {
            "analytics": "analytics_agent",
            "management": "management_agent",
            "help": "help_node",
        },
    )

    for node in ("analytics_agent", "management_agent", "help_node"):
        workflow.add_edge(node, "format_response")

    workflow.add_edge("format_response", "save_to_db")
    workflow.add_edge("save_to_db", END)

    return workflow.compile()


def _route_by_intent(state: NutritionistState) -> str:
    """Path-функция: confirm/cancel/management → management; analytics → analytics; иначе help."""
    intent = state.get("intent", "help")
    if intent in ("management", "confirm", "cancel"):
        return "management"
    if intent == "analytics":
        return "analytics"
    return "help"


# ==========================================
# УЗЕЛ: РАЗБОР ЗАПРОСА
# ==========================================

_AFFIRM = re.compile(r"^\s*(да|ага|ок|окей|подтверждаю|верно|согласен|давай|yes|ok|y)\b", re.I)
_NEGATE = re.compile(r"^\s*(нет|не надо|отмена|отмени|стоп|cancel|no|n)\b", re.I)


def parse_request_node(state: NutritionistState) -> NutritionistState:
    """
    Определяет intent. Если есть ожидающее подтверждения действие (pending_action
    в последней реплике агента) и сообщение — да/нет, ставит intent=confirm/cancel
    и поднимает pending_action в state. Иначе классифицирует запрос через Groq.
    """
    message = (state.get("message") or "").strip()

    # 1. Подтверждение/отмена ожидающего действия
    pending = _load_pending_action(state.get("nutritionist_id"))
    if pending:
        if _AFFIRM.match(message):
            state["intent"] = "confirm"
            state["pending_action"] = pending
            return state
        if _NEGATE.match(message):
            state["intent"] = "cancel"
            state["pending_action"] = pending
            return state
        # Иначе — новая команда, pending игнорируется (будет перезаписан)

    # 2. Классификация запроса
    parsed = _classify_request(message)
    state["intent"] = parsed.get("intent", "help")
    state["period_days"] = int(parsed.get("period_days") or 7)

    client_name = parsed.get("client_name")
    if client_name:
        state["target_client_name"] = client_name
        client_id, candidates = _resolve_client(client_name)
        state["target_client_id"] = client_id
        state["client_candidates"] = candidates

    return state


CLASSIFIER_PROMPT = """Ты — маршрутизатор запросов нутрициолога. Определи намерение.

Верни СТРОГО валидный JSON без markdown:
{"intent": "analytics | management | help", "client_name": "<имя или null>", "period_days": <число или null>}

- analytics — запрос аналитики/сводки/отчёта/динамики/статистики по клиенту или базе.
- management — команда создать/изменить: план, задачу, статус клиента, доверенный источник.
- help — общий вопрос, неясный запрос, приветствие.

client_name — имя клиента, если упомянуто (иначе null). period_days — период в днях, если указан.
Только JSON."""


def _classify_request(message: str) -> Dict[str, Any]:
    """Классификация запроса нутрициолога через дешёвый LLM (Groq)."""
    if not message:
        return {"intent": "help"}
    try:
        response = call_llm(
            task_type="dialog",
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": message},
            ],
        )
        parsed = _safe_parse_json(response.get("content", "")) or {}
        if parsed.get("intent") not in ("analytics", "management", "help"):
            parsed["intent"] = "help"
        return parsed
    except Exception as e:
        logger.error(f"Nutritionist classifier error: {e}")
        return {"intent": "help"}


def _resolve_client(name: str):
    """
    Разрешает имя клиента в client_id по подстроке (без учёта регистра).
    Возвращает (client_id|None, candidates). Один матч → id; несколько → candidates.
    """
    name = (name or "").strip().lower()
    if not name:
        return None, []
    try:
        clients = queries.get_all_clients()
    except Exception as e:
        logger.error(f"Error loading clients for resolve: {e}")
        return None, []

    matches = [c for c in clients if name in (c.get("name") or "").lower()]
    if len(matches) == 1:
        return matches[0].get("id"), []
    return None, matches


def _load_pending_action(nutritionist_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Поднимает pending_action из последней реплики агента в треде нутрициолога."""
    if not nutritionist_id:
        return None
    try:
        thread = queries.get_conversation_thread(nutritionist_thread_id(nutritionist_id))
    except Exception as e:
        logger.error(f"Error loading nutritionist thread: {e}")
        return None

    for msg in reversed(thread or []):
        if msg.get("role") != "agent":
            continue
        meta = msg.get("metadata_json") or {}
        if meta.get("pending_action"):
            return meta["pending_action"]
        break  # интересует только последняя реплика агента
    return None


# ==========================================
# УЗЕЛ: HELP
# ==========================================

def help_node(state: NutritionistState) -> NutritionistState:
    state["agent_used"] = "help"
    state["agent_response"] = (
        "Я ассистент-аналитик. Могу:\n"
        "• Аналитика: «сводка по Марине за неделю», «статистика по базе»\n"
        "• Управление: «поставь задачу X клиенту Y», «смени статус Z на paused»\n"
        "  (любая запись — только после вашего подтверждения)\n"
        "Уточните клиента по имени, если запрос о конкретном человеке."
    )
    return state


# ==========================================
# УЗЕЛ: ФОРМАТИРОВАНИЕ
# ==========================================

def format_response_node(state: NutritionistState) -> NutritionistState:
    state["final_message"] = state.get("agent_response") or "Готово."
    state["view"] = _build_view_directive(state)
    return state


def _build_view_directive(state: NutritionistState) -> Optional[Dict[str, Any]]:
    """
    Директива для центральной панели веб-кабинета (Блок 2), выводится из уже
    разобранного запроса. Telegram её игнорирует.

    - конкретный клиент определён → карточка клиента (с графиками)
    - аналитика по базе (без клиента) → дашборд аналитики
    - неоднозначное имя / help / запись → не переключаем вид (None)
    """
    intent = state.get("intent")
    # Аналитика всегда уходит в панель «Аналитика» (анализ рендерится там).
    if intent == "analytics":
        return {"type": "analytics"}
    # Прочие запросы по конкретному клиенту (управление) → карточка клиента.
    if state.get("target_client_id"):
        return {
            "type": "client_card",
            "client_id": state.get("target_client_id"),
            "client_name": state.get("target_client_name"),
            "period_days": state.get("period_days", 7),
        }
    return None


# ==========================================
# УЗЕЛ: СОХРАНЕНИЕ В БД
# ==========================================

def save_to_db_node(state: NutritionistState) -> NutritionistState:
    """
    Сохраняет реплику агента в тред нутрициолога. pending_action кладётся в
    metadata_json, чтобы следующее сообщение могло его подтвердить/отменить.
    """
    nutritionist_id = state.get("nutritionist_id")
    try:
        metadata: Dict[str, Any] = {
            "agent_used": state.get("agent_used"),
            "intent": state.get("intent"),
        }
        pending = state.get("pending_action")
        if pending:
            metadata["pending_action"] = pending

        queries.save_conversation(
            client_id=state.get("target_client_id"),  # nullable: None для запросов по базе
            role="agent",
            message_text=state.get("final_message") or "",
            channel=state.get("channel", "web"),
            conversation_type="nutritionist_note",
            thread_id=nutritionist_thread_id(nutritionist_id) if nutritionist_id else None,
            metadata=metadata,
        )
    except Exception as e:
        logger.error(f"Error saving nutritionist conversation: {e}")
        # Не валим обработку — ответ уже сформирован

    return state


# ==========================================
# УТИЛИТЫ
# ==========================================

def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
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
