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
from datetime import date
import sys
import os

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.queries import get_client_by_id, get_client_profile


def _payment_active(client: Dict[str, Any]) -> bool:
    """
    Оплата активна: статус trial/active И срок оплаты не истёк.

    paid_until ('YYYY-MM-DD') задаёт нутрициолог при оплате. Если он в прошлом —
    считаем неоплаченным АВТОМАТИЧЕСКИ (ежемесячная оплата: без ручного переключения
    payment_status). paid_until не задан → блокируем только по статусу (напр. trial без
    даты), чтобы не запереть клиента без даты. Сравнение ISO-дат строкой корректно.
    """
    if (client or {}).get('payment_status') not in ('trial', 'active'):
        return False
    paid_until = client.get('paid_until')
    if paid_until:
        try:
            if str(paid_until)[:10] < date.today().isoformat():
                return False
        except Exception:
            pass
    return True


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
    if not _payment_active(client):
        return {
            "allowed": False,
            "mode": "blocked",
            "reason": "payment_inactive",
            "message_for_client": "Ваша подписка неактивна или срок оплаты истёк. Для продолжения обратитесь к нутрициологу."
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
    # [5] ОПРЕДЕЛЕНИЕ РЕЖИМА РАБОТЫ (тарифа)
    # ════════════════════════════════════════════
    # Здесь уже: онбординг завершён, оплата ок, не архив/пауза.
    # Тариф определяется наличием сопровождения нутрициолога:
    #   - 'active' → full_program (Активный: полный, с поддержкой нутрициолога)
    #   - иначе    → ai_support  (Базовый: кабинет + ИИ-агент, без нутрициолога)
    if client.get('client_status') == 'active':
        return {
            "allowed": True,
            "mode": "full_program",
            "reason": "ok",
            "message_for_client": ""
        }

    return {
        "allowed": True,
        "mode": "ai_support",
        "reason": "ok",
        "message_for_client": ""
    }


def check_web_access(client_id: str) -> Dict[str, Any]:
    """
    Проверка допуска клиента В ВЕБ-КАБИНЕТ (до диалога с агентом).

    Отличие от check_access: НЕ требует завершённого онбординга (клиент должен
    войти, чтобы заполнить анкету). Блокирует по: архив, пауза, оплата (вкл. истёкший
    paid_until). Единый рубильник «приостановлено» — client_status='paused' (access_status
    убран как дублирующий).

    Returns: {"allowed": bool, "reason": str, "message_for_client": str}
    """
    try:
        client = get_client_by_id(client_id)
    except Exception as e:
        return {"allowed": False, "reason": "database_error",
                "message_for_client": f"Ошибка при проверке доступа. ({str(e)})"}

    if not client:
        return {"allowed": False, "reason": "client_not_found",
                "message_for_client": "Клиент не найден. Обратитесь к нутрициологу."}

    if client.get('client_status') == 'archived':
        return {"allowed": False, "reason": "client_archived",
                "message_for_client": "Ваш аккаунт архивирован. Обратитесь к нутрициологу."}

    if client.get('client_status') == 'paused':
        return {"allowed": False, "reason": "program_paused",
                "message_for_client": "Обслуживание приостановлено. Обратитесь к нутрициологу."}

    if not _payment_active(client):
        return {"allowed": False, "reason": "payment_inactive",
                "message_for_client": "Доступ к кабинету закрыт: услуга не оплачена или срок оплаты истёк. Обратитесь к нутрициологу."}

    return {"allowed": True, "reason": "ok", "message_for_client": ""}


def get_access_tier(client: Dict[str, Any]) -> str:
    """Тариф для отображения: 'full' (Активный, с нутрициологом) | 'basic' (Базовый, ИИ)."""
    return "full" if (client or {}).get("client_status") == "active" else "basic"
