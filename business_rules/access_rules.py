"""
Access Rules — Проверка доступа клиента к системе

Проверяет:
1. Анкета заполнена (onboarding_completed_at)
2. Оплата активна (payment_status)
3. Не архивирован (client_status)

Определяет режим работы:
- 'full_program' — активная работа с нутрициологом
- 'ai_support' — поддержка AI-агентом без нутрициолога
"""

from typing import Dict, Any
import sys
import os

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.queries import get_client_by_id, get_client_profile


def check_access(client_id: str) -> Dict[str, Any]:
    """
    Проверка доступа клиента к системе

    Args:
        client_id: UUID клиента

    Returns:
        {
            "allowed": bool,                    # Можно ли продолжать работу
            "mode": str,                        # 'full_program' | 'ai_support' | 'blocked'
            "reason": str,                      # Код причины блокировки
            "message_for_client": str           # Сообщение клиенту
        }

    Режимы работы:
        - full_program: client_status='active' — активная работа с нутрициологом
        - ai_support: client_status='completed' + payment='active' — поддержка AI без нутрициолога
        - blocked: доступ запрещён
    """

    # Получить данные клиента
    try:
        client = get_client_by_id(client_id)
        profile = get_client_profile(client_id)
    except Exception as e:
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "database_error",
            "message_for_client": f"Ошибка при проверке доступа. Обратитесь в поддержку. ({str(e)})"
        }

    if not client:
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "client_not_found",
            "message_for_client": "Клиент не найден в системе. Обратитесь к нутрициологу."
        }

    # ════════════════════════════════════════════
    # [1] ПРОВЕРКА: Клиент архивирован?
    # ════════════════════════════════════════════
    if client.get('client_status') == 'archived':
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "client_archived",
            "message_for_client": "Ваш аккаунт архивирован. Для возобновления работы обратитесь к нутрициологу."
        }

    # ════════════════════════════════════════════
    # [2] ПРОВЕРКА: Анкета заполнена?
    # ════════════════════════════════════════════
    if not profile or profile.get('onboarding_completed_at') is None:
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "onboarding_incomplete",
            "message_for_client": "Пожалуйста, завершите заполнение анкеты перед началом работы с агентом."
        }

    # ════════════════════════════════════════════
    # [3] ПРОВЕРКА: Оплата активна?
    # ════════════════════════════════════════════
    payment_status = client.get('payment_status')

    if payment_status not in ['trial', 'active']:
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "payment_inactive",
            "message_for_client": "Ваша подписка неактивна. Для продолжения работы обратитесь к нутрициологу."
        }

    # ════════════════════════════════════════════
    # [4] ПРОВЕРКА: Программа на паузе?
    # ════════════════════════════════════════════
    if client.get('client_status') == 'paused':
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "program_paused",
            "message_for_client": "Ваша программа временно приостановлена. Для возобновления обратитесь к нутрициологу."
        }

    # ════════════════════════════════════════════
    # [5] ОПРЕДЕЛЕНИЕ РЕЖИМА РАБОТЫ
    # ════════════════════════════════════════════
    client_status = client.get('client_status')

    # РЕЖИМ 1: Полная программа с нутрициологом
    if client_status == 'active':
        return {
            "allowed": True,
            "mode": "full_program",
            "reason": "ok",
            "message_for_client": ""
        }

    # РЕЖИМ 2: AI-поддержка без нутрициолога
    if client_status == 'completed' and payment_status == 'active':
        return {
            "allowed": True,
            "mode": "ai_support",
            "reason": "ok",
            "message_for_client": ""
        }

    # ════════════════════════════════════════════
    # FALLBACK: Неизвестный статус (не должны попадать сюда)
    # ════════════════════════════════════════════
    return {
        "allowed": False,
        "mode": "blocked",
        "reason": "unknown_status",
        "message_for_client": f"Неизвестный статус аккаунта ({client_status}). Обратитесь к нутрициологу."
    }
