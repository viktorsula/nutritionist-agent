"""
Веб-представления панели нутрициолога (Streamlit) — Этап 8, Шаг 1.

Чистые функции рендера, чтобы их можно было импортировать/тестировать отдельно
от app.py (без запуска Streamlit-скрипта целиком).

- render_registry()  — таб «Реестр клиентов» (данные из client_registry_view)
- render_analytics() — таб «Аналитика» (сводки + AI-анализ через analytics_node)

Запись в БД отсюда НЕ выполняется (read-only + AI-анализ). Управление планами/
задачами — через чат с подтверждением (см. management_agent).
"""

import json
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
# ТАБ: НАСТРОЙКИ
# ==========================================

def render_settings(actor_id: Optional[str] = None) -> None:
    """
    Таб «Настройки»: пороги алертов, доверенные источники, редактор промптов,
    LLM-модели. Это системные настройки нутрициолога (ТЗ: правка без кода) —
    запись прямая, без подтверждения.
    """
    st.subheader("⚙️ Настройки системы")

    with st.expander("🚨 Пороги алертов (alert_thresholds)", expanded=True):
        _render_json_setting("alert_thresholds", actor_id, hint='{"glucose_critical": 15, "glucose_high": 10}')

    with st.expander("🌐 Доверенные источники (trusted_sources)"):
        _render_trusted_sources(actor_id)

    with st.expander("📝 Редактор промптов"):
        _render_prompt_editor()

    with st.expander("🤖 LLM-модели (llm_config)"):
        _render_json_setting("llm_config", actor_id, hint='{"dialog": {...}, "analysis": {...}}')


def _render_json_setting(key: str, actor_id: Optional[str], hint: str = "") -> None:
    """Универсальный JSON-редактор настройки system_settings по ключу."""
    try:
        value = queries.get_setting(key)
    except Exception as e:
        st.error(f"Не удалось загрузить «{key}»: {e}")
        return

    current = json.dumps(value, ensure_ascii=False, indent=2) if value is not None else ""
    text = st.text_area(
        f"Значение «{key}» (JSON):",
        value=current,
        height=200,
        placeholder=hint,
        key=f"setting_{key}",
    )

    if st.button("💾 Сохранить", key=f"save_{key}"):
        parsed, err = _parse_json(text)
        if err:
            st.error(f"Некорректный JSON: {err}")
            return
        try:
            queries.update_system_setting(key, parsed, updated_by=actor_id)
            queries.write_audit_log(
                actor_type="nutritionist",
                actor_id=actor_id,
                action="update_threshold",
                entity_type="settings",
                entity_id=key,
                new_value={"value": parsed},
            )
            st.success(f"«{key}» сохранено.")
        except Exception as e:
            st.error(f"Ошибка сохранения: {e}")


def _render_trusted_sources(actor_id: Optional[str]) -> None:
    """Список доверенных источников + добавление/удаление."""
    try:
        sources = queries.get_setting("trusted_sources")
    except Exception as e:
        st.error(f"Не удалось загрузить источники: {e}")
        return
    if not isinstance(sources, list):
        sources = []

    if sources:
        for i, src in enumerate(sources):
            name = src.get("name") if isinstance(src, dict) else None
            url = src.get("url") if isinstance(src, dict) else src
            cols = st.columns([4, 1])
            cols[0].write(f"• {name or '—'} — {url}")
            if cols[1].button("🗑", key=f"del_src_{i}"):
                remaining = [s for j, s in enumerate(sources) if j != i]
                _save_trusted_sources(remaining, actor_id, f"удалён источник {url}")
                st.rerun()
    else:
        st.caption("Источников пока нет.")

    st.markdown("**Добавить источник:**")
    c1, c2 = st.columns(2)
    new_name = c1.text_input("Название", key="new_src_name")
    new_url = c2.text_input("URL", key="new_src_url")
    if st.button("➕ Добавить", key="add_src"):
        if not new_url:
            st.error("Укажите URL.")
            return
        sources.append({"name": new_name or None, "url": new_url})
        _save_trusted_sources(sources, actor_id, f"добавлен источник {new_url}")
        st.rerun()


def _save_trusted_sources(sources: List[Any], actor_id: Optional[str], note: str) -> None:
    try:
        queries.update_system_setting("trusted_sources", sources, updated_by=actor_id)
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=actor_id,
            action="update_threshold",
            entity_type="settings",
            entity_id="trusted_sources",
            new_value={"note": note, "count": len(sources)},
        )
    except Exception as e:
        st.error(f"Ошибка сохранения источников: {e}")


def _render_prompt_editor() -> None:
    """Редактор промптов: список → загрузка текста → сохранение в БД."""
    from prompts import list_available_prompts, load_prompt, save_prompt

    try:
        available = list_available_prompts()
    except Exception as e:
        st.error(f"Не удалось получить список промптов: {e}")
        return
    if not available:
        st.caption("Промптов не найдено.")
        return

    name = st.selectbox("Промпт:", sorted(available.keys()), key="prompt_pick")
    info = available.get(name, {})
    st.caption(f"Источник: {info.get('source', '—')}")

    try:
        text = load_prompt(name)
    except Exception as e:
        st.error(f"Не удалось загрузить промпт: {e}")
        return

    edited = st.text_area("Текст промпта:", value=text, height=300, key=f"prompt_text_{name}")
    description = st.text_input("Описание изменения:", key=f"prompt_desc_{name}")

    if st.button("💾 Сохранить промпт", key=f"save_prompt_{name}"):
        try:
            save_prompt(name, edited, description=description or None)
            st.success(f"Промпт «{name}» сохранён в БД (приоритет над файлом).")
        except Exception as e:
            st.error(f"Ошибка сохранения промпта: {e}")


def _parse_json(text: str):
    """Парсит JSON из текста. Возвращает (value, error). Пустой текст → (None, None)."""
    text = (text or "").strip()
    if not text:
        return None, None
    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        return None, str(e)


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
