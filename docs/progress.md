# Журнал прогресса проекта

## Статус: В разработке
Последнее обновление: 10 июня 2026

## Выполнено

### Инфраструктура
- [x] Репозиторий GitHub: viktorsula/nutritionist-agent
- [x] Среда разработки: GitHub Codespaces → Claude Code
- [x] Деплой на Render: nutritionist-agent-gvxp.onrender.com
- [x] Базовый app.py на Streamlit задеплоен
- [x] .env.example — шаблон всех ключей
- [x] .gitignore — защита секретов
- [x] Supabase проект создан: nutritionist-agent (FREE tier)

### База данных Supabase — ✅ ПОЛНОСТЬЮ ГОТОВА (v1.3)
- [x] **Блок 1:** users, clients, client_profiles, wellness_plans
- [x] **Блок 2:** conversations, client_events
- [x] **Блок 3:** nutrition_plans (версионирование + триггеры), tasks
- [x] **Блок 4:** notification_schedule, audit_logs, system_settings
- [x] **Блок 5:** document_metadata, knowledge_base, client_documents (pgvector)
- [x] **VIEW:** client_registry_view (SECURITY INVOKER)
- [x] **Триггеры:** trg_plan_version, trg_deactivate_old_plans
- [x] **Индексы:** включая ivfflat для pgvector
- [x] **Security Advisor:** 0 errors, 0 warnings ✅
- [x] **docs/schema.sql** — актуализирован до v1.3
- [x] **Миграция v1.2 → v1.3** — успешно выполнена (8 июня 2026)

### Код Python
- [x] **database/client.py** — подключение к Supabase готово
- [x] **database/models.py** — все 14 моделей готовы, синхронизированы с БД v1.3
- [x] **database/queries.py** — 43 функции реализованы (добавлена get_setting() для llm_config)
- [x] **business_rules/** — детерминированный слой готов ✅
  - [x] access_rules.py — проверка доступа, 2 режима (full_program, ai_support)
  - [x] medical_rules.py — 5 типов алертов + маршрутизация к нутрициологу
  - [x] notification_rules.py — timezone-aware проверки расписания
- [x] **utils/** — базовые модули готовы ✅
  - [x] llm.py — мультипровайдерный LLM клиент (Groq, Claude, Gemini), 6 task_type, Вариант 3 (гибридный)
  - [x] helpers.py — вспомогательные функции (структура готова, большинство — TODO для Этапа 6)
- [x] **prompts/** — система управления промптами готова ✅
  - [x] __init__.py — загрузка из БД (приоритет) → файлы (fallback)
  - [x] client/dialog_system.md — промпт для диалога с клиентом
  - [x] nutritionist/analytics_system.md — промпт для аналитики
- [x] **agents/** — базовая инфраструктура готова ✅
  - [x] router.py — входной маршрутизатор (роль → ветка агентов)
  - [x] client/state.py — ClientState TypedDict для LangGraph
  - [x] client/orchestrator.py — LangGraph граф (5 узлов: load_context → check_alerts → dialog_agent → format_response → save_to_db)
  - [x] client/dialog_agent.py — работающий агент диалога (использует Groq llama-3.3-70b)
  - [x] nutritionist/orchestrator.py — заглушка (направление к веб-интерфейсу)

## В процессе

### Код (Этапы по ТЗ v1.3)
- [x] **Этап 2:** database/ — ЗАВЕРШЁН ✅
- [x] **Этап 3:** business_rules/ — ЗАВЕРШЁН ✅
- [x] **Этап 4:** utils/ — ЗАВЕРШЁН (базовые модули) ✅
- [x] **Этап 5:** agents/ + prompts/ — ЗАВЕРШЁН (базовая инфраструктура) ✅
- [ ] **Этап 6:** Расширение agents/ (vision, nutrition, diary, analytics) + utils/ (vision.py, voice.py, web_access.py, knowledge.py)
- [ ] **Этап 7:** telegram/bot.py — интеграция с router.py ← **СЛЕДУЮЩИЙ** (для работающего MVP)
- [ ] **Этап 8:** app.py (обновить веб-интерфейс под новую архитектуру)
- [ ] **Этап 9:** monitoring/langfuse.py

## Ключевые решения принятые в ходе разработки
- **wellness_plans** — отдельная таблица "как жить" vs "что есть" (зафиксировано в ТЗ v1.3)
- **supplements_json** — отдельное поле в nutrition_plans (не внутри plan_json)
- **Индивидуальные пороги алертов** — в client_profiles (переопределяют system_settings)
- **created_by = 'nutritionist' only** — агент не назначает задачи и планы, только советует
- **5 типов алертов:** weight_increase, food_incompatible, food_forbidden, no_response, bad_wellbeing
- **Триггеры:** SECURITY INVOKER + SET search_path (прошли Security Advisor)
- **VIEW:** SECURITY INVOKER (безопасность, RLS работает корректно)
- **timestamp → message_timestamp/action_timestamp** — избежание конфликта с зарезервированным словом PostgreSQL
- **queries.py:** 43 функции охватывают все сценарии из ТЗ v1.3 (раздел 12)
- **llm.py Вариант 3 (гибридный):** task_type (из БД) ИЛИ provider+model (эксперименты) — максимальная гибкость
- **llm_config в system_settings:** нутрициолог сможет менять модели через веб-интерфейс (v1.1)
- **Система промптов (3 уровня):** файлы .md (MVP) → БД (v1.1) → веб-редактор (v1.1+) — приоритет БД над файлами
- **LangGraph для оркестрации:** стандарт мультиагентных систем, граф: load_context → check_alerts → agent → format → save
- **ClientState TypedDict:** полное состояние агента (входные данные, контекст, алерты, результаты, метаданные)

## Следующий шаг
**Этап 7:** Telegram Bot (telegram/bot.py) — интеграция с agents/router.py для работающего MVP диалога с клиентами  
**ИЛИ**  
**Этап 6:** Расширение агентов (vision_agent для фото еды, nutrition_agent для анализа рациона) + utils/ (vision.py, voice.py, web_access.py, knowledge.py)