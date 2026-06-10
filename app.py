"""
Streamlit веб-интерфейс для Агента-ассистента нутрициолога

Архитектура (по ТЗ v1.3):
[Web / Streamlit] → router.py → client/ или nutritionist/

Версия: 2.0 (интеграция с agents/)
TODO v1.1: Supabase Auth (JWT авторизация)
"""

import os
import streamlit as st
from datetime import datetime

# Настройка страницы
st.set_page_config(
    page_title="Агент нутрициолога",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# ИМПОРТ AGENTS (новая архитектура)
# ==========================================

try:
    from agents import route_message
    AGENTS_AVAILABLE = True
except ImportError as e:
    AGENTS_AVAILABLE = False
    st.error(f"⚠️ Ошибка импорта agents: {e}")


# ==========================================
# ИНИЦИАЛИЗАЦИЯ SESSION STATE
# ==========================================

if "role" not in st.session_state:
    st.session_state.role = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "user_name" not in st.session_state:
    st.session_state.user_name = None

if "messages" not in st.session_state:
    st.session_state.messages = []


# ==========================================
# SIDEBAR — ВЫБОР РОЛИ
# ==========================================

with st.sidebar:
    st.title("🥗 Агент нутрициолога")
    st.caption("v2.0 — интеграция с agents/")

    st.divider()

    # Выбор роли
    st.subheader("Выберите роль")

    role_choice = st.radio(
        "Я:",
        options=["client", "nutritionist", "observer"],
        format_func=lambda x: {
            "client": "👤 Клиент",
            "nutritionist": "👨‍⚕️ Нутрициолог",
            "observer": "👁️ Наблюдатель (продакшн)"
        }[x],
        key="role_selector"
    )

    st.session_state.role = role_choice

    st.divider()

    # Авторизация / Идентификация
    if role_choice == "client":
        st.subheader("👤 Клиент")

        # TODO v1.1: Supabase Auth
        st.caption("⚠️ MVP: Тестовый режим без авторизации")

        client_name = st.text_input(
            "Ваше имя:",
            value=st.session_state.user_name or "Тестовый Клиент",
            key="client_name_input"
        )

        if client_name:
            st.session_state.user_name = client_name
            # Генерация test user_id (в продакшене — UUID из БД)
            st.session_state.user_id = f"test-client-{client_name.lower().replace(' ', '-')}"

            st.success(f"✅ Вы вошли как: **{client_name}**")
            st.caption(f"ID: `{st.session_state.user_id}`")

        st.info(
            "💡 **Для полноценного тестирования:**\n"
            "Создайте реального клиента в Supabase БД"
        )

    elif role_choice == "nutritionist":
        st.subheader("👨‍⚕️ Нутрициолог")

        st.caption("⚠️ MVP: Базовый интерфейс")

        nutritionist_name = st.text_input(
            "Ваше имя:",
            value="Нутрициолог",
            key="nutritionist_name_input"
        )

        if nutritionist_name:
            st.session_state.user_name = nutritionist_name
            st.session_state.user_id = "test-nutritionist-001"

            st.success(f"✅ Вы вошли как: **{nutritionist_name}**")

    else:  # observer
        st.subheader("👁️ Наблюдатель")

        st.info(
            "🏥 **Роль 'Наблюдатель' для продакшн-версии**\n\n"
            "Эта роль зарезервирована для версии, предназначенной для клиник:\n"
            "• Ассистенты нутрициолога\n"
            "• Родственники клиента (с согласия)\n"
            "• Права: просмотр данных, комментарии\n\n"
            "В MVP (v1.0) роль недоступна."
        )

        st.warning("⚠️ Выберите другую роль для продолжения")

    st.divider()

    # Статус системы
    st.subheader("📊 Статус системы")

    if AGENTS_AVAILABLE:
        st.success("✅ agents/ подключены")
    else:
        st.error("❌ agents/ недоступны")

    # Проверка API ключей
    groq_key = os.environ.get('GROQ_API_KEY')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')

    if groq_key:
        st.success("✅ GROQ_API_KEY")
    else:
        st.warning("⚠️ GROQ_API_KEY не найден")

    if anthropic_key:
        st.success("✅ ANTHROPIC_API_KEY")
    else:
        st.info("ℹ️ ANTHROPIC_API_KEY опционален")

    st.divider()

    # Кнопка очистки истории
    if st.button("🗑️ Очистить историю", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ==========================================
# MAIN INTERFACE
# ==========================================

# Проверка роли observer
if st.session_state.role == "observer":
    st.warning("👈 Роль 'Наблюдатель' недоступна в v1.0. Выберите другую роль в боковой панели.")
    st.stop()

# Проверка что роль выбрана и пользователь идентифицирован
if not st.session_state.user_id:
    st.warning("👈 Выберите роль и введите имя в боковой панели")
    st.stop()

# Заголовок
if st.session_state.role == "client":
    st.title("💬 Чат с ИИ-ассистентом")
    st.caption(f"Привет, {st.session_state.user_name}! Задай вопрос о питании или расскажи что ел сегодня.")
else:
    st.title("📊 Панель нутрициолога")
    st.caption("Аналитика клиентов и управление программами")

# ==========================================
# ВЕТКА КЛИЕНТА — ЧАТ
# ==========================================

if st.session_state.role == "client":

    # Отображение истории
    for msg in st.session_state.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        with st.chat_message(role):
            st.write(content)

            # Метаданные (для отладки)
            if msg.get("metadata"):
                with st.expander("🔍 Метаданные (debug)"):
                    st.json(msg["metadata"])

    # Ввод сообщения
    if prompt := st.chat_input("Ваше сообщение..."):

        # Отображение сообщения пользователя
        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat()
        })

        with st.chat_message("user"):
            st.write(prompt)

        # Вызов agents через router
        if AGENTS_AVAILABLE:
            with st.chat_message("assistant"):
                with st.spinner("🤔 Думаю..."):
                    try:
                        # Маршрутизация через agents/router.py
                        response = route_message(
                            user_id=st.session_state.user_id,
                            message=prompt,
                            channel="web"
                        )

                        if response.get("success"):
                            answer = response.get("message", "Ошибка: ответ не получен")

                            # Отображение ответа
                            st.write(answer)

                            # Сохранение в историю
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": answer,
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {
                                    "agent_used": response.get("agent_used"),
                                    "model": response.get("model"),
                                    "processing_time_ms": response.get("processing_time_ms")
                                }
                            })

                            # Показать метаданные
                            with st.expander("🔍 Детали ответа"):
                                st.write(f"**Агент:** {response.get('agent_used', 'unknown')}")
                                st.write(f"**Модель:** {response.get('model', 'unknown')}")
                                st.write(f"**Время обработки:** {response.get('processing_time_ms', 0)} мс")

                                if response.get('alerts'):
                                    st.warning(f"⚠️ Алертов: {len(response['alerts'])}")

                        else:
                            # Ошибка от router
                            error_msg = response.get("message", "Произошла ошибка")
                            st.error(f"❌ {error_msg}")

                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": error_msg,
                                "timestamp": datetime.now().isoformat(),
                                "metadata": {"error": response.get("error")}
                            })

                    except Exception as e:
                        st.error(f"❌ Ошибка: {str(e)}")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "Произошла ошибка при обработке сообщения.",
                            "timestamp": datetime.now().isoformat(),
                            "metadata": {"error": str(e)}
                        })
        else:
            st.error("❌ agents/ недоступны. Проверьте импорты.")


# ==========================================
# ВЕТКА НУТРИЦИОЛОГА — ПАНЕЛЬ УПРАВЛЕНИЯ
# ==========================================

elif st.session_state.role == "nutritionist":

    st.info("🚧 Панель нутрициолога в разработке (Этап 8)")

    # Табы для разных функций
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Реестр клиентов",
        "📊 Аналитика",
        "⚙️ Настройки",
        "💬 Тестовый диалог"
    ])

    with tab1:
        st.subheader("📋 Реестр клиентов")
        st.write("TODO: Список всех клиентов с фильтрами")
        st.write("- Статусы (active, completed, archived)")
        st.write("- Алерты (критичные события)")
        st.write("- Последняя активность")

    with tab2:
        st.subheader("📊 Аналитика")
        st.write("TODO: Аналитика по клиентам")
        st.write("- Сводки за период")
        st.write("- Графики прогресса")
        st.write("- Соблюдение планов")

    with tab3:
        st.subheader("⚙️ Настройки системы")
        st.write("TODO: Настройки")
        st.write("- Редактирование промптов")
        st.write("- Настройка моделей LLM")
        st.write("- Пороги алертов")

    with tab4:
        st.subheader("💬 Тестовый диалог с agents/")

        st.caption("Протестируйте работу системы от лица нутрициолога")

        test_message = st.text_area(
            "Тестовое сообщение:",
            value="Дай сводку по всем активным клиентам"
        )

        if st.button("📤 Отправить", use_container_width=True):
            if AGENTS_AVAILABLE:
                with st.spinner("Обработка..."):
                    try:
                        response = route_message(
                            user_id=st.session_state.user_id,
                            message=test_message,
                            channel="web"
                        )

                        if response.get("success"):
                            st.success("✅ Ответ получен:")
                            st.write(response.get("message"))

                            with st.expander("🔍 Детали"):
                                st.json(response)
                        else:
                            st.error(f"❌ {response.get('message')}")

                    except Exception as e:
                        st.error(f"❌ Ошибка: {e}")
            else:
                st.error("agents/ недоступны")


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption(
    "🥗 Агент-ассистент нутрициолога v2.0 | "
    "Интеграция с agents/ | "
    f"Роль: {st.session_state.role} | "
    f"User: {st.session_state.user_name}"
)
