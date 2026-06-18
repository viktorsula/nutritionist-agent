"""
NutritionistState — TypedDict для LangGraph оркестратора нутрициолога.

Определяет структуру состояния, которое передаётся между узлами графа:
parse_request → [analytics | management | help] → format_response → save_to_db
"""

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime


class NutritionistState(TypedDict, total=False):
    """Состояние для LangGraph оркестратора нутрициолога."""

    # ==========================================
    # ВХОДНЫЕ ДАННЫЕ
    # ==========================================

    nutritionist_id: str
    """UUID нутрициолога"""

    message: str
    """Текст сообщения от нутрициолога"""

    channel: str
    """Канал: 'telegram' | 'web'"""

    message_type: str
    """Тип сообщения: 'text' | 'voice' (для нутрициолога обычно 'text')"""

    metadata: Dict[str, Any]
    """Дополнительные данные"""

    # ==========================================
    # РЕЗУЛЬТАТ РАЗБОРА ЗАПРОСА (parse_request)
    # ==========================================

    intent: str
    """Намерение: 'analytics' | 'management' | 'confirm' | 'cancel' | 'help'"""

    target_client_id: Optional[str]
    """UUID клиента, к которому относится запрос (если определён по имени)"""

    target_client_name: Optional[str]
    """Имя клиента из запроса (как написал нутрициолог)"""

    client_candidates: List[Dict[str, Any]]
    """Кандидаты при неоднозначном совпадении имени клиента"""

    period_days: int
    """Период для аналитики (дней), по умолчанию 7"""

    # ==========================================
    # ПОДТВЕРЖДЕНИЕ ЗАПИСИ (two-step)
    # ==========================================

    pending_action: Optional[Dict[str, Any]]
    """
    Разобранное, но НЕ исполненное действие записи. Структура:
    {
        "action_type": str,   # create_task | create_nutrition_plan | update_client_status | add_trusted_source
        "params": {...},      # параметры для queries.*
        "human_summary": str  # человекочитаемое резюме для подтверждения
    }
    Сохраняется в conversations.metadata_json и поднимается на следующем
    сообщении, если нутрициолог подтвердил действие.
    """

    # ==========================================
    # РЕЗУЛЬТАТЫ РАБОТЫ АГЕНТОВ
    # ==========================================

    agent_used: Optional[str]
    agent_response: Optional[str]
    final_message: Optional[str]
    llm_model: Optional[str]
    llm_usage: Optional[Dict[str, int]]

    # ==========================================
    # МЕТАДАННЫЕ
    # ==========================================

    timestamp: str
    processing_time_ms: Optional[int]
    error: Optional[str]


def nutritionist_thread_id(nutritionist_id: str) -> str:
    """
    Единый thread_id для диалога нутрициолога. Не привязан к client_id,
    что позволяет поднимать pending_action независимо от клиента.
    """
    return f"nut:{nutritionist_id}"


def create_initial_state(
    nutritionist_id: str,
    message: str,
    channel: str = "web",
    message_type: str = "text",
    metadata: Optional[Dict[str, Any]] = None,
) -> NutritionistState:
    """Создаёт начальное состояние для оркестратора нутрициолога."""
    return NutritionistState(
        nutritionist_id=nutritionist_id,
        message=message,
        channel=channel,
        message_type=message_type,
        metadata=metadata or {},
        timestamp=datetime.now().isoformat(),
        intent="help",
        target_client_id=None,
        target_client_name=None,
        client_candidates=[],
        period_days=7,
        pending_action=None,
    )


def extract_response(state: NutritionistState) -> Dict[str, Any]:
    """Извлекает финальный ответ из состояния (зеркало клиентского extract_response)."""
    return {
        "message": state.get("final_message", state.get("agent_response", "Ошибка обработки")),
        "agent_used": state.get("agent_used"),
        "model": state.get("llm_model"),
        "processing_time_ms": state.get("processing_time_ms"),
        "intent": state.get("intent"),
        "error": state.get("error"),
    }
