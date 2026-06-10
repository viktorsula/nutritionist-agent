"""
Вспомогательные функции для агентов

Содержит утилиты для:
- Форматирование сообщений для клиента
- Парсинг дат/времени
- Валидация данных
- Расчёты КБЖУ
- Генерация сводок

TODO Этап 6:
- Добавить функции по мере необходимости агентов
- Интеграция с business_rules для форматирования алертов
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytz

logger = logging.getLogger(__name__)


# ========================================
# ФОРМАТИРОВАНИЕ СООБЩЕНИЙ
# ========================================

def format_client_message(
    text: str,
    alerts: Optional[List[Dict[str, Any]]] = None,
    nutritionist_notified: bool = False
) -> str:
    """
    Форматирует сообщение для клиента с учётом алертов.

    Args:
        text: Основной текст ответа от LLM
        alerts: Список алертов из medical_rules
        nutritionist_notified: Флаг уведомления нутрициолога

    Returns:
        Отформатированное сообщение для клиента

    Example:
        >>> message = format_client_message(
        ...     "Отличный выбор продуктов!",
        ...     alerts=[{"type": "food_incompatible", "severity": "medium"}],
        ...     nutritionist_notified=True
        ... )
    """
    parts = []

    # Если нутрициолог уведомлён — добавляем это в начало
    if nutritionist_notified:
        parts.append(
            "⚠️ Нутрициолог уже уведомлён о ситуации и свяжется с вами в ближайшее время.\n"
        )

    # Основной текст
    parts.append(text)

    # Добавляем информацию об алертах (если есть)
    if alerts and len(alerts) > 0:
        parts.append("\n\n📋 Обратите внимание:")
        for alert in alerts:
            alert_type = alert.get('type', 'unknown')
            severity = alert.get('severity', 'low')
            message = alert.get('message', '')

            # Эмодзи в зависимости от severity
            emoji = {
                'low': 'ℹ️',
                'medium': '⚠️',
                'high': '🚨',
                'critical': '🔴'
            }.get(severity, 'ℹ️')

            parts.append(f"{emoji} {message}")

    return "\n".join(parts)


# ========================================
# РАБОТА С ДАТАМИ/ВРЕМЕНЕМ
# ========================================

def parse_datetime(
    text: str,
    timezone: str = 'UTC',
    base_date: Optional[datetime] = None
) -> Optional[datetime]:
    """
    Парсит дату/время из текста на русском языке.

    Поддерживает:
    - "сегодня", "завтра", "вчера"
    - "через 2 часа", "через 3 дня"
    - ISO формат: "2026-06-10T14:30:00"

    Args:
        text: Текст с датой/временем
        timezone: Часовой пояс клиента
        base_date: Базовая дата (по умолчанию — текущая)

    Returns:
        datetime объект или None

    TODO v1.1: Добавить поддержку сложных форматов через NLP
    """
    if not text:
        return None

    tz = pytz.timezone(timezone)
    now = base_date or datetime.now(tz)

    text = text.lower().strip()

    # Простые варианты
    if text in ['сегодня', 'today']:
        return now

    if text in ['завтра', 'tomorrow']:
        return now + timedelta(days=1)

    if text in ['вчера', 'yesterday']:
        return now - timedelta(days=1)

    # TODO: Добавить парсинг "через N часов/дней"
    # TODO: Добавить парсинг ISO формата

    logger.warning(f"Не удалось распарсить дату: {text}")
    return None


def format_date_for_client(
    dt: datetime,
    timezone: str,
    language: str = 'ru'
) -> str:
    """
    Форматирует дату для отображения клиенту.

    Args:
        dt: datetime объект
        timezone: Часовой пояс клиента
        language: Язык ('ru', 'en', 'ar')

    Returns:
        Отформатированная строка

    Example:
        >>> dt = datetime.now()
        >>> format_date_for_client(dt, 'Asia/Dubai', 'ru')
        '10 июня 2026, 14:30'
    """
    tz = pytz.timezone(timezone)
    local_dt = dt.astimezone(tz)

    if language == 'ru':
        # TODO: Добавить локализацию месяцев на русский
        return local_dt.strftime('%d.%m.%Y %H:%M')
    elif language == 'en':
        return local_dt.strftime('%B %d, %Y %H:%M')
    else:
        return local_dt.strftime('%Y-%m-%d %H:%M')


# ========================================
# ВАЛИДАЦИЯ
# ========================================

def validate_ingredients(
    ingredients_list: List[str],
    client_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Валидирует список ингредиентов.

    Проверяет:
    - Аллергены клиента (если client_id указан)
    - Запрещённые продукты из плана питания

    Args:
        ingredients_list: Список ингредиентов
        client_id: ID клиента для проверки ограничений

    Returns:
        {
            "valid": bool,
            "warnings": List[str],
            "forbidden": List[str],
            "allergies": List[str]
        }

    TODO Этап 6: Интеграция с medical_rules.check_allergies()
    """
    result = {
        "valid": True,
        "warnings": [],
        "forbidden": [],
        "allergies": []
    }

    # TODO: Добавить проверку через medical_rules
    # if client_id:
    #     from business_rules.medical_rules import check_allergies
    #     allergy_result = check_allergies(client_id, ingredients_list)
    #     if allergy_result['has_allergens']:
    #         result['valid'] = False
    #         result['allergies'] = allergy_result['allergens']

    return result


# ========================================
# РАСЧЁТЫ КБЖУ
# ========================================

def calculate_nutrition(foods: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Рассчитывает суммарные КБЖУ.

    Args:
        foods: Список продуктов [{"name": str, "calories": int, "protein": float, ...}]

    Returns:
        {
            "calories": float,
            "protein": float,
            "fats": float,
            "carbs": float
        }

    Example:
        >>> foods = [
        ...     {"name": "Курица", "calories": 200, "protein": 40, "fats": 5, "carbs": 0},
        ...     {"name": "Рис", "calories": 150, "protein": 3, "fats": 1, "carbs": 35}
        ... ]
        >>> calculate_nutrition(foods)
        {'calories': 350, 'protein': 43, 'fats': 6, 'carbs': 35}
    """
    result = {
        "calories": 0.0,
        "protein": 0.0,
        "fats": 0.0,
        "carbs": 0.0
    }

    for food in foods:
        result['calories'] += food.get('calories', 0)
        result['protein'] += food.get('protein', 0)
        result['fats'] += food.get('fats', 0)
        result['carbs'] += food.get('carbs', 0)

    return result


def estimate_calories(food_description: str) -> int:
    """
    Примерная оценка калорий по описанию блюда.

    Args:
        food_description: Текстовое описание еды

    Returns:
        Приблизительное количество калорий

    TODO v1.1: Интеграция с LLM для более точной оценки
    """
    # TODO: Использовать call_llm() для оценки калорий
    # response = call_llm(
    #     task_type='nutrition_analysis',
    #     messages=[...]
    # )

    # Заглушка
    logger.warning(f"estimate_calories() — заглушка для: {food_description}")
    return 0


# ========================================
# ГЕНЕРАЦИЯ СВОДОК
# ========================================

def generate_summary(
    client_id: str,
    period: str = 'week'
) -> str:
    """
    Генерирует сводку по клиенту за период.

    Args:
        client_id: ID клиента
        period: Период ('day', 'week', 'month')

    Returns:
        Текстовая сводка

    TODO Этап 6: Реализация через queries + call_llm
    """
    # TODO: Получить данные из БД
    # from database import queries
    # events = queries.get_client_events(client_id, period)
    # meals = queries.get_conversations(client_id, filter_type='meals')

    # TODO: Использовать LLM для генерации сводки
    # from utils.llm import call_llm
    # response = call_llm(
    #     task_type='summary',
    #     messages=[...]
    # )

    logger.warning(f"generate_summary() — заглушка для client_id={client_id}")
    return f"Сводка за {period} для клиента {client_id}"


def format_analytics_report(data: Dict[str, Any]) -> str:
    """
    Форматирует аналитический отчёт для нутрициолога.

    Args:
        data: Аналитические данные

    Returns:
        Отформатированный отчёт

    TODO Этап 7: Реализация после создания analytics_agent
    """
    logger.warning("format_analytics_report() — заглушка")
    return "Аналитический отчёт (TODO)"


# ========================================
# РАБОТА С ЯЗЫКАМИ
# ========================================

def detect_language(text: str) -> str:
    """
    Определяет язык текста.

    Args:
        text: Текст для анализа

    Returns:
        Код языка ('ru', 'en', 'ar')

    TODO v1.1: Использовать langdetect или LLM
    """
    # Простая эвристика для MVP
    if any(char in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' for char in text.lower()):
        return 'ru'
    elif any(char in 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي' for char in text):
        return 'ar'
    else:
        return 'en'


def translate_if_needed(text: str, target_lang: str = 'ru') -> str:
    """
    Переводит текст если нужно.

    Args:
        text: Исходный текст
        target_lang: Целевой язык

    Returns:
        Переведённый текст

    TODO v1.1: Интеграция с translation API
    """
    detected = detect_language(text)

    if detected == target_lang:
        return text

    # TODO: Использовать Google Translate API или LLM для перевода
    logger.warning(f"translate_if_needed() — нужен перевод {detected} → {target_lang}")
    return text
