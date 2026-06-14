"""
ClientState — TypedDict для LangGraph оркестратора клиента

Определяет структуру состояния, которое передаётся между узлами графа.
"""

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime


class ClientState(TypedDict, total=False):
    """
    Состояние для LangGraph оркестратора клиента.

    Используется для передачи данных между узлами:
    load_context → check_alerts → route_to_agent → agent → format_response → save_to_db
    """

    # ==========================================
    # ВХОДНЫЕ ДАННЫЕ (устанавливаются в начале)
    # ==========================================

    client_id: str
    """UUID клиента"""

    message: str
    """Текст сообщения от клиента"""

    channel: str
    """Канал: 'telegram' | 'web'"""

    message_type: str
    """Тип сообщения: 'text' | 'photo' | 'voice' | 'document'"""

    metadata: Dict[str, Any]
    """Дополнительные данные (фото, аудио, файлы)"""

    # ==========================================
    # КОНТЕКСТ КЛИЕНТА (загружается из БД)
    # ==========================================

    client_profile: Optional[Dict[str, Any]]
    """
    Профиль клиента из client_profiles:
    {
        "name": str,
        "goal": str,
        "allergies": [{...}],
        "initial_weight": float,
        "target_weight": float,
        ...
    }
    """

    active_plan: Optional[Dict[str, Any]]
    """
    Активный план питания из nutrition_plans:
    {
        "target_calories": int,
        "restrictions": List[str],
        "plan_json": {...},
        ...
    }
    """

    wellness_plan: Optional[Dict[str, Any]]
    """
    План ЗОЖ из wellness_plans:
    {
        "target_sleep_hours": float,
        "target_activity_minutes": int,
        ...
    }
    """

    access_info: Dict[str, Any]
    """
    Результат check_access() из business_rules:
    {
        "allowed": bool,
        "mode": 'full_program' | 'ai_support',
        "reason": str,
        "message_for_client": str
    }
    """

    conversation_history: List[Dict[str, str]]
    """
    История последних сообщений из conversations:
    [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."},
        ...
    ]
    """

    # ==========================================
    # РЕЗУЛЬТАТЫ ПРОВЕРОК
    # ==========================================

    food_items: List[str]
    """
    Распознанные/упомянутые продукты (из vision_agent или из текста).
    Используется business_rules для проверок food_forbidden / food_incompatible.
    """

    alerts: List[Dict[str, Any]]
    """
    Алерты из medical_rules.check_medical_alerts():
    [
        {
            "type": str,
            "severity": str,
            "message": str,
            "details": {...}
        },
        ...
    ]
    """

    routing: Optional[Dict[str, Any]]
    """
    Результат medical_rules.determine_routing():
    {
        "route_to": 'llm' | 'both',
        "notify_nutritionist": bool,
        "llm_context": {...}
    }
    """

    # ==========================================
    # РЕЗУЛЬТАТЫ РАБОТЫ АГЕНТОВ
    # ==========================================

    agent_used: Optional[str]
    """Имя агента, который обработал сообщение"""

    agent_response: Optional[str]
    """Сырой ответ от агента (до форматирования)"""

    final_message: Optional[str]
    """Финальное сообщение для клиента (после форматирования)"""

    llm_model: Optional[str]
    """Модель LLM, которая использовалась"""

    llm_usage: Optional[Dict[str, int]]
    """
    Использование токенов:
    {
        "input_tokens": int,
        "output_tokens": int,
        "total_tokens": int
    }
    """

    # ==========================================
    # МЕТАДАННЫЕ
    # ==========================================

    timestamp: str
    """ISO timestamp начала обработки"""

    processing_time_ms: Optional[int]
    """Время обработки в миллисекундах"""

    error: Optional[str]
    """Текст ошибки, если произошла"""


# Вспомогательные функции для работы со State

def create_initial_state(
    client_id: str,
    message: str,
    channel: str = 'telegram',
    message_type: str = 'text',
    metadata: Optional[Dict[str, Any]] = None,
    access_info: Optional[Dict[str, Any]] = None
) -> ClientState:
    """
    Создаёт начальное состояние для оркестратора.

    Args:
        client_id: UUID клиента
        message: Текст сообщения
        channel: Канал коммуникации
        message_type: Тип сообщения
        metadata: Дополнительные данные
        access_info: Результат check_access()

    Returns:
        ClientState с заполненными входными данными
    """
    return ClientState(
        client_id=client_id,
        message=message,
        channel=channel,
        message_type=message_type,
        metadata=metadata or {},
        access_info=access_info or {},
        timestamp=datetime.now().isoformat(),
        alerts=[],
        conversation_history=[]
    )


def extract_response(state: ClientState) -> Dict[str, Any]:
    """
    Извлекает финальный ответ из состояния.

    Args:
        state: Финальное состояние после обработки

    Returns:
        {
            "message": str,
            "agent_used": str,
            "model": str,
            "processing_time_ms": int
        }
    """
    return {
        "message": state.get('final_message', state.get('agent_response', 'Ошибка обработки')),
        "agent_used": state.get('agent_used'),
        "model": state.get('llm_model'),
        "processing_time_ms": state.get('processing_time_ms'),
        "alerts": state.get('alerts', []),
        "error": state.get('error')
    }
