"""
Веб-представления панели нутрициолога (Streamlit) — Этап 8, Шаг 1.

Чистые функции рендера, чтобы их можно было импортировать/тестировать отдельно
от app.py (без запуска Streamlit-скрипта целиком).

- render_registry()  — таб «Реестр клиентов» (данные из client_registry_view)
- render_analytics() — таб «Аналитика» (сводки + AI-анализ через analytics_node)

Запись в БД отсюда НЕ выполняется (read-only + AI-анализ). Управление планами/
задачами — через чат с подтверждением (см. management_agent).
"""

import logging
from typing import Any, Dict, List, Optional

import streamlit as st

from database import queries

logger = logging.getLogger(__name__)

STATUS_OPTIONS = ["Все", "lead", "onboarding", "active", "paused", "completed", "archived"]


# ==========================================
# ТАБ: РЕЕСТР КЛИЕНТОВ
# ==========================================

def render_registry() -> None:
    """Таб «Реестр клиентов»: таблица из client_registry_view + детали клиента."""
    st.subheader("📋 Реестр клиентов")

    status_filter = st.selectbox("Фильтр по статусу:", STATUS_OPTIONS, key="registry_status")
    status = None if status_filter == "Все" else status_filter

    try:
        rows = queries.get_client_registry(status=status)
    except Exception as e:
        st.error(f"Не удалось загрузить реестр: {e}")
        logger.error(f"Registry load error: {e}", exc_info=True)
        return

    if not rows:
        st.info("Клиентов не найдено.")
        return

    st.caption(f"Всего: {len(rows)}")
    st.dataframe(_registry_table(rows), use_container_width=True, hide_index=True)

    # Детали выбранного клиента
    names = {f"{r.get('name', '—')} ({r.get('client_status', '—')})": r.get("id") for r in rows}
    choice = st.selectbox("Открыть карточку клиента:", ["—"] + list(names.keys()), key="registry_pick")
    if choice != "—":
        _render_client_card(names[choice])


def _registry_table(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Формирует компактную таблицу реестра для отображения."""
    table = []
    for r in rows:
        table.append({
            "Имя": r.get("name", "—"),
            "Статус": r.get("client_status", "—"),
            "Оплата": r.get("payment_status", "—"),
            "Доступ": r.get("access_status", "—"),
            "Цель": r.get("goals", "—"),
            "Вес": r.get("weight", "—"),
            "План": r.get("plan_title") or "—",
            "Посл. активность": r.get("last_contact") or "—",
            "Откр. задач": r.get("open_tasks") or 0,
        })
    return table


def _render_client_card(client_id: Optional[str]) -> None:
    """Карточка клиента: профиль, активный план, задачи, последние события."""
    if not client_id:
        return

    st.divider()
    try:
        profile = queries.get_client_profile(client_id) or {}
        plan = queries.get_active_nutrition_plan(client_id) or {}
        tasks = queries.get_pending_tasks(client_id) or []
        events = queries.get_client_events(client_id, limit=10) or []
    except Exception as e:
        st.error(f"Не удалось загрузить карточку клиента: {e}")
        logger.error(f"Client card error: {e}", exc_info=True)
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**👤 Профиль**")
        st.write(f"Цель: {profile.get('goal', '—')}")
        st.write(f"Ограничения: {_join(profile.get('restrictions'))}")
        st.write(f"Аллергии: {_join(_allergy_names(profile.get('allergies')))}")
    with col2:
        st.markdown("**🍽 Активный план**")
        if plan:
            st.write(f"Название: {plan.get('title', '—')}")
            st.write(f"Калории: {plan.get('plan_json', {}).get('target_calories', '—')}")
        else:
            st.write("План не назначен.")

    st.markdown(f"**✅ Открытые задачи ({len(tasks)})**")
    for t in tasks:
        st.write(f"- {t.get('title', '—')} (до {t.get('due_date', '—')})")

    st.markdown(f"**📌 Последние события ({len(events)})**")
    for e in events[:10]:
        sev = e.get("severity") or "—"
        st.write(f"- {e.get('event_date', '')}: {e.get('event_type', '')} [{sev}]")


# ==========================================
# ТАБ: АНАЛИТИКА
# ==========================================

def render_analytics() -> None:
    """Таб «Аналитика»: метрики из get_client_summary + AI-анализ (analytics_node)."""
    st.subheader("📊 Аналитика")

    try:
        clients = queries.get_all_clients()
    except Exception as e:
        st.error(f"Не удалось загрузить клиентов: {e}")
        return

    # --- По всей базе ---
    with st.expander("📈 По всей базе", expanded=not clients):
        _render_base_stats(clients)

    if not clients:
        st.info("Нет клиентов для индивидуальной аналитики.")
        return

    # --- По клиенту ---
    st.markdown("**Аналитика по клиенту**")
    names = {c.get("name", "—"): c.get("id") for c in clients}
    picked = st.selectbox("Клиент:", list(names.keys()), key="analytics_client")
    period = st.slider("Период (дней):", min_value=7, max_value=90, value=14, step=7, key="analytics_period")
    client_id = names[picked]

    try:
        summary = queries.get_client_summary(client_id, days=period) or {}
    except Exception as e:
        st.error(f"Не удалось загрузить сводку: {e}")
        return

    _render_summary_metrics(summary)

    if st.button("🤖 Сгенерировать AI-анализ", use_container_width=True, key="analytics_ai"):
        with st.spinner("Анализирую (Claude)..."):
            text = _run_ai_analysis(client_id, picked, period)
        st.markdown("**Анализ:**")
        st.write(text)


def _render_base_stats(clients: List[Dict[str, Any]]) -> None:
    funnel: Dict[str, int] = {}
    for c in clients:
        s = c.get("client_status", "unknown")
        funnel[s] = funnel.get(s, 0) + 1

    st.write(f"Всего клиентов: **{len(clients)}**")
    if funnel:
        st.write("Воронка: " + ", ".join(f"{k}: {v}" for k, v in sorted(funnel.items())))

    try:
        alerts = queries.get_critical_alerts(hours=24)
    except Exception:
        alerts = []
    st.write(f"Критичные алерты за 24ч: **{len(alerts)}**")


def _render_summary_metrics(summary: Dict[str, Any]) -> None:
    if not summary:
        st.info("Данных за период нет.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Сообщений", summary.get("message_count", 0))
    c2.metric("Событий", summary.get("total_events", 0))
    c3.metric("Critical/High", f"{summary.get('critical_alerts', 0)}/{summary.get('high_alerts', 0)}")
    c4.metric("Задачи (вып./откр.)", f"{summary.get('completed_tasks', 0)}/{summary.get('pending_tasks', 0)}")


def _run_ai_analysis(client_id: str, client_name: str, period: int) -> str:
    """Запускает analytics_node (read + Claude) и возвращает текст анализа."""
    from agents.nutritionist.state import create_initial_state
    from agents.nutritionist.analytics_agent import analytics_node

    state = create_initial_state(
        nutritionist_id="web",
        message=f"Аналитика по клиенту {client_name} за {period} дней",
        channel="web",
    )
    state["intent"] = "analytics"
    state["target_client_id"] = client_id
    state["target_client_name"] = client_name
    state["period_days"] = period

    analytics_node(state)
    return state.get("agent_response") or "Не удалось получить анализ."


# ==========================================
# УТИЛИТЫ
# ==========================================

def _join(values: Optional[List[Any]]) -> str:
    if not values:
        return "—"
    return ", ".join(str(v) for v in values)


def _allergy_names(allergies: Optional[List[Any]]) -> List[Any]:
    if not allergies:
        return []
    return [a.get("name", a) if isinstance(a, dict) else a for a in allergies]
