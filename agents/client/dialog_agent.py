"""
Dialog Agent — агент ежедневного диалога с клиентом

Используется для:
- Обычные вопросы о питании
- Поддержка и мотивация
- Ответы на общие вопросы
- Фиксация информации от клиента

Промпт: prompts/client/dialog_system.md
LLM: Groq llama-3.3-70b (task_type='dialog')
"""

import logging
from typing import List, Dict, Any

from utils.llm import call_llm
from prompts import load_prompt
from .state import ClientState

logger = logging.getLogger(__name__)


def dialog_node(state: ClientState) -> ClientState:
    """
    Узел LangGraph для диалога с клиентом.

    Процесс:
    1. Загрузка промпта из prompts/client/dialog_system.md
    2. Форматирование с контекстом клиента
    3. Формирование истории диалога
    4. Вызов LLM (task_type='dialog')
    5. Сохранение ответа в state
    """
    try:
        # 1. Построение system prompt
        system_prompt = build_system_prompt(state)

        # 2. Построение истории диалога
        messages = build_messages(state, system_prompt)

        # 3. Вызов LLM
        logger.info(f"Calling LLM for client {state['client_id']}")

        response = call_llm(
            task_type='dialog',  # Groq llama-3.3-70b
            messages=messages
        )

        # 4. Сохранение результата
        state['agent_response'] = response['content']
        state['agent_used'] = 'dialog_agent'
        state['llm_model'] = response['model']
        state['llm_usage'] = response.get('usage', {})

        logger.info(
            f"Dialog agent response for client {state['client_id']}: "
            f"{len(response['content'])} chars, "
            f"{response['usage'].get('total_tokens', 0)} tokens"
        )

        return state

    except Exception as e:
        logger.error(f"Dialog agent error: {e}", exc_info=True)
        state['agent_response'] = (
            "Извините, произошла ошибка при обработке вашего сообщения. "
            "Попробуйте ещё раз или обратитесь к нутрициологу."
        )
        state['agent_used'] = 'dialog_agent_error'
        state['error'] = str(e)

        return state


def build_system_prompt(state: ClientState) -> str:
    """
    Формирует system prompt для dialog agent.

    Загружает шаблон из prompts/client/dialog_system.md
    и заполняет его контекстом клиента.
    """
    try:
        # Загрузка шаблона
        template = load_prompt('client/dialog_system')

        # Извлечение данных
        profile = state.get('client_profile', {})
        plan = state.get('active_plan', {})
        access = state.get('access_info', {})
        alerts = state.get('alerts', [])

        # Форматирование
        prompt = template.format(
            client_name=profile.get('name') or 'Клиент',
            client_goal=profile.get('goals') or 'Не указана',
            restrictions=format_restrictions(plan),
            allergies=format_allergies(profile),
            mode=access.get('mode', 'full_program'),
            mode_description=get_mode_description(access.get('mode')),
            alerts_context=format_alerts_context(alerts),
            language='русский'  # TODO: Определять из profile или channel
        )

        # Доп. контекст по ТЗ (вес, задачи, заметки нутрициолога, план)
        extra = build_context_block(state)
        return prompt + ("\n\n" + extra if extra else "")

    except Exception as e:
        logger.error(f"Error building system prompt: {e}")
        # Fallback на минимальный промпт
        return (
            "Ты ИИ-ассистент нутрициолога. "
            "Помогай клиенту с вопросами о питании, будь доброжелательным и профессиональным."
        )


def build_messages(state: ClientState, system_prompt: str) -> List[Dict[str, str]]:
    """
    Формирует список сообщений для LLM.

    Структура:
    1. System prompt
    2. История диалога (последние 10 сообщений)
    3. Текущее сообщение пользователя
    """
    messages = []

    # 1. System prompt
    messages.append({
        "role": "system",
        "content": system_prompt
    })

    # 2. История диалога
    conversation_history = state.get('conversation_history', [])

    # Ограничение: последние 10 сообщений (5 пар user-assistant)
    recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history

    for msg in recent_history:
        messages.append({
            "role": msg['role'],
            "content": msg['content']
        })

    # 3. Текущее сообщение
    messages.append({
        "role": "user",
        "content": state['message']
    })

    return messages


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def build_context_block(state: ClientState) -> str:
    """
    Доп. контекст клиента для агента (по ТЗ): текущий/желаемый вес,
    активный план, активные задачи, заметки нутрициолога.
    Используется как внутренний контекст — не цитировать дословно.
    """
    profile = state.get('client_profile') or {}
    client = state.get('client') or {}
    plan = state.get('active_plan') or {}
    tasks = state.get('tasks') or []

    lines: List[str] = []
    if profile.get('weight'):
        lines.append(f"- Текущий вес: {profile.get('weight')} кг")
    if profile.get('target_weight'):
        lines.append(f"- Желаемый вес: {profile.get('target_weight')} кг")
    if plan and plan.get('title'):
        lines.append(f"- Активный план питания: {plan.get('title')}")
    if tasks:
        titles = ", ".join(t.get('title', '') for t in tasks[:5] if t.get('title'))
        if titles:
            lines.append(f"- Активные задачи: {titles}")
    notes = client.get('nutritionist_notes')
    if notes:
        lines.append(f"- Заметки нутрициолога (внутреннее): {notes}")

    if not lines:
        return ""
    return "## Дополнительный контекст клиента (для тебя; не цитируй дословно)\n" + "\n".join(lines)


def format_restrictions(plan: Dict[str, Any]) -> str:
    """Форматирует ограничения в питании"""
    if not plan:
        return "Не указаны"

    restrictions = plan.get('restrictions', [])

    if not restrictions:
        return "Нет"

    return ', '.join(restrictions)


def format_allergies(profile: Dict[str, Any]) -> str:
    """Форматирует список аллергий"""
    if not profile:
        return "Не указаны"

    allergies = profile.get('allergies', [])

    if not allergies:
        return "Нет"

    # allergies = [{"name": "орехи", "severity": "critical"}, ...]
    allergy_names = [a.get('name', a) if isinstance(a, dict) else a for a in allergies]

    return ', '.join(allergy_names)


def get_mode_description(mode: str) -> str:
    """Возвращает описание режима работы"""
    descriptions = {
        'full_program': (
            "Клиент находится в активной программе с нутрициологом. "
            "При критичных ситуациях нутрициолог будет уведомлён."
        ),
        'ai_support': (
            "Клиент завершил основную программу и сейчас на поддержке ИИ-ассистента. "
            "Нутрициолог не будет уведомляться, вся поддержка через тебя."
        ),
        'blocked': (
            "Доступ ограничен."
        )
    }

    return descriptions.get(mode, "Режим не определён")


def format_alerts_context(alerts: List[Dict[str, Any]]) -> str:
    """
    Форматирует алерты для включения в system prompt.

    Если есть алерты — агент должен об этом знать,
    чтобы корректно включить информацию в ответ.
    """
    if not alerts:
        return "Нет активных алертов."

    lines = [f"У клиента есть {len(alerts)} активных алертов:"]

    for idx, alert in enumerate(alerts, 1):
        alert_type = alert.get('type', 'unknown')
        severity = alert.get('severity', 'low')
        message = alert.get('message', '')

        lines.append(f"{idx}. [{severity.upper()}] {alert_type}: {message}")

    lines.append("\nУчти эту информацию при формировании ответа.")

    return '\n'.join(lines)


# ==========================================
# ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ БУДУЩЕГО
# ==========================================

def extract_food_items_from_message(message: str) -> List[str]:
    """
    Извлекает упоминания продуктов из сообщения.

    TODO Этап 6: Реализовать через NER или LLM
    Сейчас — заглушка
    """
    # Простая эвристика для примера
    food_keywords = ['курица', 'рис', 'овсянка', 'салат', 'яблоко', 'творог']

    found_items = []
    message_lower = message.lower()

    for food in food_keywords:
        if food in message_lower:
            found_items.append(food)

    return found_items


def detect_intent(message: str) -> str:
    """
    Определяет намерение пользователя.

    TODO Этап 6: Реализовать через классификацию или LLM
    Возможные интенты:
    - 'question_about_food' — вопрос о конкретном продукте
    - 'plan_question' — вопрос о плане питания
    - 'report_meal' — сообщение о приёме пищи
    - 'report_weight' — сообщение о весе
    - 'report_wellbeing' — сообщение о самочувствии
    - 'general_chat' — общий разговор
    """
    # Заглушка
    return 'general_chat'
