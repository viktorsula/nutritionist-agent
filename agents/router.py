"""
Router — входной маршрутизатор сообщений

Процесс:
1. Определить роль пользователя (nutritionist/client)
2. Проверка доступа через business_rules
3. Маршрутизация к соответствующему оркестратору
4. Возврат ответа

Использование:
    from agents.router import route_message

    response = route_message(
        user_id="telegram_123456",
        message="Что мне съесть на завтрак?",
        channel="telegram"
    )
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def route_message(
    user_id: str,
    message: str,
    channel: str = 'telegram',
    message_type: str = 'text',
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Маршрутизирует входящее сообщение к нужному оркестратору.

    Args:
        user_id: ID пользователя (telegram_id или user_id из БД)
        message: Текст сообщения
        channel: Канал ('telegram', 'web')
        message_type: Тип сообщения ('text', 'photo', 'voice', 'document')
        metadata: Дополнительные данные (фото, аудио и т.д.)

    Returns:
        {
            "success": bool,
            "message": str,  # Ответ для пользователя
            "role": str,  # Роль пользователя
            "agent_used": str,  # Какой агент обработал
            "model": str,  # Какая модель использовалась
            "error": str  # Если success=False
        }

    Example:
        >>> response = route_message(
        ...     user_id="123456",
        ...     message="Привет! Что съесть на завтрак?",
        ...     channel="telegram"
        ... )
        >>> print(response['message'])
    """

    try:
        # 1. Определить пользователя и его роль
        user_info = get_user_info(user_id, channel)

        if not user_info:
            return {
                "success": False,
                "error": "user_not_found",
                "message": "Пользователь не найден. Обратитесь к нутрициологу для регистрации."
            }

        role = user_info['role']
        actual_user_id = user_info['id']

        logger.info(
            f"Routing message: user_id={actual_user_id}, role={role}, "
            f"channel={channel}, type={message_type}"
        )

        # 2. Маршрутизация по роли
        if role == 'client':
            return route_to_client(
                client_id=actual_user_id,
                message=message,
                channel=channel,
                message_type=message_type,
                metadata=metadata or {}
            )

        elif role == 'nutritionist':
            return route_to_nutritionist(
                nutritionist_id=actual_user_id,
                message=message,
                channel=channel,
                message_type=message_type,
                metadata=metadata or {}
            )

        else:
            return {
                "success": False,
                "error": "unknown_role",
                "message": f"Неизвестная роль: {role}"
            }

    except Exception as e:
        logger.error(f"Router error: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "message": "Произошла ошибка. Попробуйте позже или обратитесь к нутрициологу."
        }


def get_user_info(user_id: str, channel: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о пользователе из БД.

    Args:
        user_id: ID пользователя (telegram_id или UUID)
        channel: Канал ('telegram', 'web')

    Returns:
        {
            "id": str,  # UUID пользователя
            "role": str,  # 'client' | 'nutritionist'
            "name": str,
            "telegram_id": str (optional),
            "email": str (optional)
        }
        или None если не найден
    """
    from database import queries

    # Попытка 1: Поиск по telegram_id
    if channel == 'telegram':
        user = queries.get_user_by_telegram_id(user_id)
        if user:
            return user

    # Попытка 2: Поиск по UUID
    try:
        user = queries.get_user(user_id)
        if user:
            return user
    except Exception:
        pass

    return None


def route_to_client(
    client_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Маршрутизация для клиента.

    Процесс:
    1. Проверка доступа через business_rules
    2. Вызов client/orchestrator
    3. Возврат ответа
    """
    from business_rules.access_rules import check_access

    # 1. Проверка доступа
    access_check = check_access(client_id)

    if not access_check['allowed']:
        return {
            "success": False,
            "error": "access_denied",
            "role": "client",
            "message": access_check['message_for_client']
        }

    # 2. Вызов оркестратора клиента
    from agents.client.orchestrator import process_client_message

    result = process_client_message(
        client_id=client_id,
        message=message,
        channel=channel,
        message_type=message_type,
        metadata=metadata,
        access_info=access_check
    )

    return {
        "success": True,
        "role": "client",
        **result
    }


def route_to_nutritionist(
    nutritionist_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Маршрутизация для нутрициолога.

    TODO Этап 6: Реализовать полноценный оркестратор
    Сейчас: простая заглушка
    """
    from agents.nutritionist.orchestrator import process_nutritionist_message

    result = process_nutritionist_message(
        nutritionist_id=nutritionist_id,
        message=message,
        channel=channel,
        message_type=message_type,
        metadata=metadata
    )

    return {
        "success": True,
        "role": "nutritionist",
        **result
    }


# Вспомогательные функции для тестирования

def simulate_client_message(client_id: str, message: str) -> Dict[str, Any]:
    """Симуляция сообщения от клиента для тестирования"""
    return route_message(
        user_id=client_id,
        message=message,
        channel='web'
    )


def simulate_nutritionist_message(nutritionist_id: str, message: str) -> Dict[str, Any]:
    """Симуляция сообщения от нутрициолога для тестирования"""
    return route_message(
        user_id=nutritionist_id,
        message=message,
        channel='web'
    )
