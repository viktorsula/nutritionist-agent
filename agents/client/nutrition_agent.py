"""
Nutrition Agent — вопросы клиента о рационе/меню/плане

Отвечает ТОЛЬКО по личным данным клиента: цель, рацион, план сопровождения,
его анализы, ограничения; помогает с меню в рамках назначенного плана.
Советует, но не назначает (планы создаёт только нутрициолог).

Поток:
1. Собрать контекст: активный план питания, профиль, план ЗОЖ.
2. Подтянуть знания из БД: база нутрициолога (pgvector), документы клиента (pgvector).
3. Веб-источники: серверный инструмент Claude web_search с whitelist доменов
   (domains из system_settings.trusted_sources). Поиск выполняет Anthropic.
4. Сформировать ответ через Claude (task_type='nutrition_analysis').

Промпт: prompts/client/nutrition_system.md
LLM: Claude Sonnet (task_type='nutrition_analysis').
"""

import logging
from typing import Any, Dict, List, Optional

from utils.llm import call_llm, LLMUnavailableError
from utils.knowledge import (
    search_knowledge_base,
    search_client_documents,
    build_context_from_chunks,
)
from utils.web_access import build_web_search_tool, get_trusted_domains
from prompts import load_prompt
from .state import ClientState

logger = logging.getLogger(__name__)


# ==========================================
# УЗЕЛ LANGGRAPH
# ==========================================

def nutrition_node(state: ClientState) -> ClientState:
    """
    Узел вопросов о рационе. Устанавливает agent_response, agent_used, llm_model.
    """
    state['agent_used'] = 'nutrition_agent'

    try:
        # Фото холодильника/полок (ветка advice) → распознаём продукты для совета.
        fridge = _gather_fridge(state)
        knowledge_context = _gather_knowledge(state)
        system_prompt = _build_system_prompt(state, knowledge_context, fridge)
        messages = _build_messages(state, system_prompt, fridge)

        # Веб-источники: серверный инструмент Claude web_search с whitelist
        # доверенных доменов (нутрициолог ведёт список в system_settings).
        # Если доверенных доменов нет — инструмент не подключаем.
        call_kwargs: Dict[str, Any] = {}
        domains = get_trusted_domains()
        if domains:
            call_kwargs['tools'] = [
                build_web_search_tool(allowed_domains=domains, max_uses=3)
            ]

        # call_llm сам выполняет взаимозамену моделей (Claude → Groq → Gemini).
        # Если основная модель недоступна (лимиты/сбой/нет кредитов) — ответит
        # резервная; tools (web_search) применяется только если сработал Claude.
        response = call_llm(
            task_type='nutrition_analysis', messages=messages, **call_kwargs
        )

        state['agent_response'] = response['content']
        state['llm_model'] = response.get('model')
        state['llm_usage'] = response.get('usage', {})
        if response.get('fallback_used'):
            state['agent_used'] = 'nutrition_agent_fallback'
        return state

    except LLMUnavailableError as e:
        # Ни основная, ни резервные модели не ответили — просим повторить позже.
        logger.warning(f"Nutrition agent: все модели недоступны: {e}")
        state['agent_response'] = (
            "Сейчас сервис перегружен и модели не отвечают. "
            "Пожалуйста, подождите немного и отправьте вопрос ещё раз."
        )
        state['agent_used'] = 'nutrition_agent_unavailable'
        state['error'] = str(e)
        return state

    except Exception as e:
        logger.error(f"Nutrition agent error: {e}", exc_info=True)
        state['agent_response'] = (
            "Извините, не получилось подготовить ответ по рациону. "
            "Попробуйте переформулировать вопрос или обратитесь к нутрициологу."
        )
        state['agent_used'] = 'nutrition_agent_error'
        state['error'] = str(e)
        return state


# ==========================================
# СБОР ЗНАНИЙ (pgvector из БД)
# ==========================================

def _gather_knowledge(state: ClientState) -> str:
    """
    Собирает контекст из БД: база знаний нутрициолога и документы клиента (pgvector).
    Всё защищено — при ошибке/без ключей источник просто пропускается.

    Веб-источники сюда НЕ входят: их ищет серверный инструмент Claude web_search
    (подключается в nutrition_node по whitelist доменов из system_settings).
    """
    query = (state.get('message') or '').strip()
    client_id = state['client_id']
    parts: List[str] = []

    if not query:
        return ""

    # 1. База знаний нутрициолога
    kb_chunks = search_knowledge_base(query, match_count=4)
    kb_ctx = build_context_from_chunks(kb_chunks, max_chars=2000)
    if kb_ctx:
        parts.append("Из базы знаний нутрициолога:\n" + kb_ctx)

    # 2. Документы/анализы самого клиента
    doc_chunks = search_client_documents(query, client_id, match_count=4)
    doc_ctx = build_context_from_chunks(doc_chunks, max_chars=2000)
    if doc_ctx:
        parts.append("Из документов клиента:\n" + doc_ctx)

    return "\n\n".join(parts)


def _gather_fridge(state: ClientState) -> Optional[Dict[str, Any]]:
    """
    Если ход — фото продуктов (холодильник/полки), распознаёт их (Gemini) для совета.

    Возвращает {"products": [...], "meal_type": str} или None (не фото / не распозналось).
    """
    if state.get('message_type') != 'photo':
        return None

    metadata = state.get('metadata') or {}
    image_bytes = metadata.get('image_bytes')
    if not image_bytes:
        return None

    try:
        from utils.vision import analyze_fridge

        result = analyze_fridge(image_bytes, mime_type=metadata.get('mime_type', 'image/jpeg'))
    except Exception as e:
        logger.warning(f"analyze_fridge failed: {e}")
        return None

    products = [str(p).strip() for p in (result.get('products') or []) if p]
    if not products:
        return None

    state['food_items'] = products
    from .food_analysis import resolve_meal_type
    return {"products": products, "meal_type": resolve_meal_type(state.get('message', ''))}


def _format_fridge_block(fridge: Dict[str, Any]) -> str:
    """Блок-инструкция для LLM: советовать ТОЛЬКО из имеющихся продуктов, в рамках плана."""
    products = ", ".join(fridge.get('products') or [])
    meal_labels = {
        "breakfast": "завтрак", "lunch": "обед", "dinner": "ужин",
        "snack": "перекус", "all_day": "рацион на весь день",
    }
    meal = meal_labels.get(fridge.get('meal_type'), "приём пищи")
    return (
        "## Доступные продукты клиента (распознаны с фото)\n"
        f"{products}\n"
        f"Приём пищи: {meal}\n"
        "Предложи 2–3 варианта блюд ТОЛЬКО из этих продуктов (плюс базовые специи/масло/вода), "
        "в рамках плана питания, ограничений и аллергий. Не предлагай того, чего нет в списке. "
        "Если из имеющегося в рамках плана собрать сложно — честно скажи и подскажи, что докупить."
    )


# ==========================================
# ПОСТРОЕНИЕ ПРОМПТА И СООБЩЕНИЙ
# ==========================================

def _build_system_prompt(
    state: ClientState,
    knowledge_context: str,
    fridge: Optional[Dict[str, Any]] = None,
) -> str:
    profile = state.get('client_profile') or {}
    plan = state.get('active_plan') or {}

    try:
        template = load_prompt('client/nutrition_system')
        prompt = template.format(
            client_name=profile.get('name', 'Клиент'),
            client_goal=profile.get('goal', 'Не указана'),
            restrictions=_format_list(plan.get('restrictions')),
            allergies=_format_allergies(profile),
            plan_context=_format_plan(plan),
            knowledge_context=knowledge_context or "Дополнительных материалов нет.",
            language='русский',  # TODO: определять из profile/channel
        )
        # Собственные данные клиента (вес/анализы с динамикой) — можно сообщать ему.
        from .dialog_agent import build_health_lines
        health = build_health_lines(state)
        if health:
            prompt += (
                "\n\n## Данные клиента (его собственные; можно сообщать ему)\n"
                + "\n".join(health)
            )

        # План ЗОЖ («как жить»: сон/активность/восстановление/стресс) — назначен
        # нутрициологом; учитываем при советах по рациону, но не выходим за рамки.
        wellness = _format_wellness(state.get('wellness_plan'))
        if wellness:
            prompt += "\n\n## План ЗОЖ клиента (назначен нутрициологом)\n" + wellness

        # Долговременная память — сводка прошлых разговоров (rolling-summary)
        summary = (state.get('conversation_summary') or '').strip()
        if summary:
            prompt += "\n\n## Память о клиенте (сводка прошлых разговоров)\n" + summary

        # Совет из имеющихся продуктов (фото холодильника/полок) — UC-3.
        if fridge:
            prompt += "\n\n" + _format_fridge_block(fridge)
        return prompt
    except Exception as e:
        logger.error(f"Error building nutrition system prompt: {e}")
        return (
            "Ты ИИ-ассистент нутрициолога. Отвечай на вопросы клиента о его рационе "
            "и плане, учитывай ограничения и аллергии, не выходи за рамки плана, "
            "советуй (не назначай). Отвечай на русском."
        )


def _build_messages(
    state: ClientState,
    system_prompt: str,
    fridge: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    messages = [{"role": "system", "content": system_prompt}]

    # История диалога (последние 10 сообщений)
    history = state.get('conversation_history') or []
    for msg in history[-10:]:
        messages.append({"role": msg['role'], "content": msg['content']})

    # Фото продуктов без подписи — синтезируем явную просьбу о совете.
    user_text = (state.get('message') or '').strip()
    if not user_text and fridge:
        user_text = "Я прислал фото продуктов. Подскажи, что можно из них приготовить."

    messages.append({"role": "user", "content": user_text})
    return messages


# ==========================================
# ФОРМАТИРОВАНИЕ
# ==========================================

def _format_plan(plan: Dict[str, Any]) -> str:
    if not plan:
        return "Активный план питания не назначен."

    lines = []
    title = plan.get('title')
    if title:
        lines.append(f"Название: {title}")

    calories = plan.get('target_calories')
    if calories:
        lines.append(f"Целевые калории: {calories} ккал/день")

    restrictions = plan.get('restrictions')
    if restrictions:
        lines.append("Ограничения: " + _format_list(restrictions))

    supplements = plan.get('supplements_json')
    if supplements:
        lines.append(f"БАДы/добавки: {supplements}")

    return "\n".join(lines) if lines else "План назначен, детали не заполнены."


def _format_wellness(plan: Optional[Dict[str, Any]]) -> str:
    """Человекочитаемый план ЗОЖ (только заполненные поля). Пусто → ''."""
    if not plan:
        return ""
    fields = [
        ("Сон", plan.get('sleep_target')),
        ("Активность", plan.get('activity_target')),
        ("Восстановление", plan.get('recovery')),
        ("Стресс", plan.get('stress_management')),
        ("Заметки", plan.get('notes')),
    ]
    lines = [f"- {label}: {value}" for label, value in fields if value]
    return "\n".join(lines)


def _format_list(values: Optional[List[Any]]) -> str:
    if not values:
        return "Нет"
    return ", ".join(str(v) for v in values)


def _format_allergies(profile: Dict[str, Any]) -> str:
    allergies = (profile or {}).get('allergies') or []
    if not allergies:
        return "Нет"
    names = [a.get('name', a) if isinstance(a, dict) else a for a in allergies]
    return ", ".join(str(n) for n in names)
