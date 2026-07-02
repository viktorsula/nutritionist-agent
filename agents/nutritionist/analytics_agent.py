"""
Analytics Agent (Нутрициолог) — аналитик/контролёр/репортёр.

Read-only RAG-конвейер по клиенту (v1: клиент + vector; web — позже):
1. PLAN     — тема + смежные вопросы + поисковые запросы (Groq, дёшево)
2. CONTEXT  — последние реплики треда нутрициолога
3. CLIENT   — данные клиента из БД (профиль, сводка, события, анализы, план)
4. VECTOR   — client_documents + knowledge_base по поисковым запросам (pgvector)
5. WEB      — (отложено: серверный инструмент Claude web_search)
6. SYNTHESIS— сильная LLM (task_type='analytics') → анализ + графики
7. → результат в state["analysis"] для панели «Аналитика»

По всей базе (клиент не определён) — лёгкий путь: воронка + критичные алерты.

Ничего не записывает. Финальное решение всегда за нутрициологом.
Промпт: prompts/nutritionist/analytics_system.md
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from utils.llm import call_llm
from utils.knowledge import (
    search_knowledge_base,
    search_client_documents,
    build_context_from_chunks,
)
from prompts import load_prompt
from database import queries
from .state import NutritionistState, nutritionist_thread_id

logger = logging.getLogger(__name__)

MAX_SEARCH_QUERIES = 3  # ограничение на vector-запросы (стоимость/латентность)


def analytics_node(state: NutritionistState) -> NutritionistState:
    """Узел аналитики. По клиенту — RAG-конвейер; по базе — лёгкий обзор."""
    state["agent_used"] = "analytics_agent"

    try:
        if state.get("target_client_id"):
            return _client_analytics(state)
        return _base_analytics(state)
    except Exception as e:
        logger.error(f"Analytics agent error: {e}", exc_info=True)
        state["agent_response"] = (
            "Не удалось подготовить аналитику. Уточните запрос "
            "(имя клиента, тему и период) или повторите позже."
        )
        state["agent_used"] = "analytics_agent_error"
        state["error"] = str(e)
        return state


# ==========================================
# КЛИЕНТСКИЙ КОНВЕЙЕР (RAG)
# ==========================================

def _client_analytics(state: NutritionistState) -> NutritionistState:
    client_id = state["target_client_id"]
    period_days = state.get("period_days") or 30
    request = (state.get("message") or "").strip()

    # 1. PLAN — тема, смежные вопросы, поисковые запросы
    plan = _plan_request(request)

    # 2. CONTEXT беседы
    convo = _conversation_context(state.get("nutritionist_id"))

    # 3. CLIENT — данные из БД + список доступных показателей (для графиков)
    client_ctx, indicators = _gather_client_data(client_id, period_days)

    # 4. VECTOR — документы клиента + база знаний по поисковым запросам
    knowledge_ctx = _vector_retrieve(plan.get("search_queries", []), client_id)

    # 6. SYNTHESIS — сильная LLM
    markdown, charts = _synthesize(
        request=request,
        plan=plan,
        convo=convo,
        client_ctx=client_ctx,
        knowledge_ctx=knowledge_ctx,
        indicators=indicators,
        state=state,
    )

    state["analysis"] = {
        "client_id": client_id,
        "client_name": state.get("target_client_name"),
        "title": plan.get("topic") or "Аналитика по клиенту",
        "markdown": markdown,
        "charts": charts,
        "period_days": period_days,
    }
    state["agent_response"] = "Анализ готов — открыл его в панели «Аналитика»."
    return state


# ---- Шаг 1: PLAN ----

def _plan_request(request: str) -> Dict[str, Any]:
    """Определяет тему, смежные вопросы и поисковые запросы (Groq)."""
    if not request:
        return {"topic": "Аналитика по клиенту", "questions": [], "search_queries": []}
    try:
        resp = call_llm(
            task_type="dialog",
            messages=[
                {"role": "system", "content": load_prompt("system/analytics_plan")},
                {"role": "user", "content": request},
            ],
        )
        parsed = _safe_parse_json(resp.get("content", "")) or {}
    except Exception as e:
        logger.error(f"Analytics plan error: {e}")
        parsed = {}

    return {
        "topic": parsed.get("topic") or "Аналитика по клиенту",
        "questions": parsed.get("questions") or [],
        # подстраховка: если план пуст, ищем по самому запросу
        "search_queries": (parsed.get("search_queries") or [request])[:MAX_SEARCH_QUERIES],
    }


# ---- Шаг 2: CONTEXT беседы ----

def _conversation_context(nutritionist_id: Optional[str], last_n: int = 6) -> str:
    """Последние реплики треда нутрициолога (для связности беседы)."""
    if not nutritionist_id:
        return ""
    try:
        thread = queries.get_conversation_thread(nutritionist_thread_id(nutritionist_id))
    except Exception as e:
        logger.error(f"Analytics conversation context error: {e}")
        return ""
    if not thread:
        return ""
    lines = []
    for msg in thread[-last_n:]:
        role = msg.get("role", "")
        text = (msg.get("message_text") or "").strip()
        if text:
            lines.append(f"{role}: {text[:300]}")
    return "\n".join(lines)


# ---- Шаг 3: CLIENT данные ----

def _gather_client_data(client_id: str, period_days: int) -> Tuple[str, List[str]]:
    """Данные клиента из БД. Возвращает (текст контекста, список показателей анализов)."""
    summary = queries.get_client_summary(client_id, days=period_days)
    if not summary:
        return "Клиент не найден или данных нет.", []

    client = summary.get("client", {})
    profile = _safe_call(queries.get_client_profile, client_id) or {}
    events = _safe_call(queries.get_client_events, client_id, limit=20) or []
    labs = _safe_call(queries.get_recent_lab_results, client_id, limit=30) or []
    plan = _safe_call(queries.get_active_nutrition_plan, client_id)

    lines = [
        f"Клиент: {client.get('name', 'без имени')} (статус: {client.get('client_status', '—')})",
        f"Период анализа: {period_days} дн.",
        f"Цель: {profile.get('goals', '—')}",
        f"Пол/возраст: {profile.get('gender', '—')} / {_age(profile.get('birth_date'))}",
        f"Вес: {profile.get('weight', '—')} → цель {profile.get('target_weight', '—')}",
        f"Аллергии: {_join(profile.get('allergies'))}; хронические: {_join(profile.get('chronic_conditions'))}",
        f"Сообщений за период: {summary.get('message_count', 0)}; "
        f"события: {summary.get('total_events', 0)} "
        f"(critical {summary.get('critical_alerts', 0)}, high {summary.get('high_alerts', 0)})",
        f"Задачи: выполнено {summary.get('completed_tasks', 0)}, в работе {summary.get('pending_tasks', 0)}",
    ]

    if plan:
        lines.append(f"Активный план: {plan.get('title', '—')}")

    # Нарративная память клиента (скользящая сводка бесед). Здесь оседают СУБЪЕКТИВНЫЕ
    # сигналы, сказанные в диалоге, но не ставшие структурным событием: жалобы, самочувствие,
    # контекст (напр. «вчера болела голова»). Без этого нутрициолог не видит того, что видит
    # клиентский ассистент (у которого сводка + история есть). Устраняем асимметрию памяти.
    convo_summary = (client.get("conversation_summary") or "").strip()
    if convo_summary:
        lines.append(f"\nПамять диалога с клиентом (сводка бесед; субъективные жалобы/самочувствие):\n{convo_summary}")

    # Числовые анализы (для трактовки и выбора графиков)
    indicators: List[str] = []
    if labs:
        lines.append("\nАнализы (свежие сверху):")
        for r in labs:
            ind = r.get("indicator", "")
            if ind and ind not in indicators:
                indicators.append(ind)
            lines.append(
                f"- {r.get('measured_at', '')}: {ind} = {r.get('value', '')} {r.get('unit', '') or ''}"
            )

    if events:
        lines.append("\nПоследние события:")
        for e in events[:15]:
            lines.append(
                f"- {e.get('event_date', '')}: {e.get('event_type', '')} "
                f"[{e.get('severity') or 'n/a'}] {_short(e.get('payload_json'))}"
            )

    return "\n".join(lines), indicators


# ---- Шаг 4: VECTOR ----

def _vector_retrieve(search_queries: List[str], client_id: str) -> str:
    """Чанки из документов клиента и базы знаний по поисковым запросам (pgvector)."""
    chunks: List[Dict[str, Any]] = []
    for q in search_queries:
        q = (q or "").strip()
        if not q:
            continue
        try:
            chunks.extend(search_client_documents(q, client_id, match_count=3))
        except Exception as e:
            logger.warning(f"search_client_documents failed: {e}")
        try:
            chunks.extend(search_knowledge_base(q, match_count=3))
        except Exception as e:
            logger.warning(f"search_knowledge_base failed: {e}")
    return build_context_from_chunks(chunks, max_chars=4000)


# ---- Шаг 6: SYNTHESIS ----

def _synthesize(
    request: str,
    plan: Dict[str, Any],
    convo: str,
    client_ctx: str,
    knowledge_ctx: str,
    indicators: List[str],
    state: NutritionistState,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Сильная LLM: анализ (markdown) + блок графиков (JSON). Возвращает (markdown, charts)."""
    system_prompt = _build_system_prompt()

    questions = "; ".join(plan.get("questions", [])) or "—"
    chart_hint = (
        "В КОНЦЕ ответа добавь блок ```json с графиками для панели аналитики:\n"
        '```json\n{"charts": [{"kind": "lab", "indicator": "<из списка показателей>"}, '
        '{"kind": "weight"}]}\n```\n'
        f"Доступные показатели анализов: {', '.join(indicators) if indicators else 'нет'}. "
        "Выбирай ТОЛЬКО показатели из списка; если данных для графика нет — пустой список."
    )

    user_prompt = (
        f"Запрос нутрициолога: {request}\n\n"
        f"Тема: {plan.get('topic')}\nСмежные вопросы: {questions}\n\n"
        f"Контекст беседы:\n{convo or '—'}\n\n"
        f"Данные клиента из базы:\n{client_ctx}\n\n"
        f"Материалы (документы клиента + база знаний):\n{knowledge_ctx or '—'}\n\n"
        "Сделай профессиональный анализ по структуре системного промпта "
        "(описание, тенденции, взаимосвязи, рекомендации; выводы — гипотезы для нутрициолога).\n\n"
        + chart_hint
    )

    resp = call_llm(
        task_type="analytics",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    state["llm_model"] = resp.get("model")
    state["llm_usage"] = resp.get("usage", {})

    content = resp.get("content", "") or ""
    return _split_charts(content, indicators)


def _split_charts(content: str, indicators: List[str]) -> Tuple[str, List[Dict[str, Any]]]:
    """Отделяет markdown-анализ от блока ```json с графиками; валидирует индикаторы."""
    charts: List[Dict[str, Any]] = []
    markdown = content

    m = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        markdown = (content[: m.start()] + content[m.end():]).strip()
        parsed = _safe_parse_json(m.group(1)) or {}
        for ch in parsed.get("charts", []) or []:
            kind = ch.get("kind")
            if kind == "weight":
                charts.append({"kind": "weight"})
            elif kind == "lab" and ch.get("indicator") in indicators:
                charts.append({"kind": "lab", "indicator": ch["indicator"]})

    return markdown or content, charts


# ==========================================
# БАЗОВАЯ АНАЛИТИКА (по всей базе)
# ==========================================

def _base_analytics(state: NutritionistState) -> NutritionistState:
    """Лёгкий обзор базы: воронка по статусам + критичные алерты (без vector)."""
    clients = queries.get_all_clients()
    funnel: Dict[str, int] = {}
    for c in clients:
        status = c.get("client_status", "unknown")
        funnel[status] = funnel.get(status, 0) + 1

    lines = [
        f"Всего клиентов: {len(clients)}",
        "Воронка по статусам: " + ", ".join(f"{k}: {v}" for k, v in sorted(funnel.items())),
    ]
    alerts = _safe_call(queries.get_critical_alerts, hours=24) or []
    if alerts:
        lines.append(f"\nКритичные алерты за 24ч ({len(alerts)}):")
        for a in alerts[:15]:
            name = (a.get("clients") or {}).get("name", a.get("client_id", "?"))
            lines.append(f"- {name}: {a.get('event_type', '')} {_short(a.get('payload_json'))}")
    else:
        lines.append("\nКритичных алертов за 24ч нет.")

    base_ctx = "\n".join(lines)
    resp = call_llm(
        task_type="analytics",
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": (
                f"Запрос нутрициолога: {(state.get('message') or '').strip()}\n\n"
                f"Данные по базе:\n{base_ctx}\n\n"
                "Сделай краткий аналитический обзор базы."
            )},
        ],
    )
    state["llm_model"] = resp.get("model")
    state["llm_usage"] = resp.get("usage", {})
    state["analysis"] = {
        "client_id": None,
        "client_name": None,
        "title": "Аналитика по базе",
        "markdown": resp.get("content", "") or base_ctx,
        "charts": [],
        "period_days": None,
    }
    state["agent_response"] = "Обзор по базе готов — открыл его в панели «Аналитика»."
    return state


# ==========================================
# ПРОМПТ + УТИЛИТЫ
# ==========================================

def _build_system_prompt() -> str:
    try:
        return load_prompt("nutritionist/analytics_system")
    except Exception as e:
        logger.error(f"Error loading analytics prompt: {e}")
        return (
            "Ты эксперт-аналитик нутрициолога. Анализируй данные клиентов "
            "структурированно, с цифрами и конкретными рекомендациями. "
            "Финальное решение за нутрициологом. Отвечай на русском."
        )


def _safe_call(fn, *args, **kwargs):
    """Вызов функции БД с проглатыванием ошибки (конвейер не должен падать целиком)."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning(f"{getattr(fn, '__name__', 'db_call')} failed: {e}")
        return None


def _short(value: Any, limit: int = 120) -> str:
    if not value:
        return ""
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _join(value: Any) -> str:
    if isinstance(value, list) and value:
        return ", ".join(str(x) for x in value)
    return "—"


def _age(birth: Optional[str]) -> str:
    if not birth:
        return "—"
    try:
        from datetime import datetime
        d = datetime.fromisoformat(str(birth)[:10])
        years = (datetime.now() - d).days // 365
        return f"{years} лет"
    except Exception:
        return "—"


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
