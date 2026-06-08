# Журнал прогресса проекта

## Статус: В разработке
Последнее обновление: 8 июня 2026

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

### Код Python — БАЗА ГОТОВА
- [x] **database/client.py** — подключение к Supabase готово
- [x] **database/models.py** — все 14 моделей готовы, синхронизированы с БД v1.3
- [x] **database/queries.py** — 42 функции реализованы (8 для business_rules, 14 для agents, 8 для n8n, 12 базовых)

## В процессе

### Код (Этапы по ТЗ v1.3)
- [x] **Этап 2:** database/ — ЗАВЕРШЁН (client.py, models.py, queries.py готовы)
- [ ] **Этап 3:** business_rules/ (access, medical, payment, notification) ← **СЛЕДУЮЩИЙ**
- [ ] **Этап 4:** utils/ (llm.py, vision.py, voice.py, helpers.py)
- [ ] **Этап 5:** agents/ (router.py + client/ + nutritionist/)
- [ ] **Этап 6:** telegram/bot.py
- [ ] **Этап 7:** app.py (обновить под новую архитектуру)
- [ ] **Этап 8:** monitoring/langfuse.py

## Ключевые решения принятые в ходе разработки
- **wellness_plans** — отдельная таблица "как жить" vs "что есть" (зафиксировано в ТЗ v1.3)
- **supplements_json** — отдельное поле в nutrition_plans (не внутри plan_json)
- **Индивидуальные пороги алертов** — в client_profiles (переопределяют system_settings)
- **created_by = 'nutritionist' only** — агент не назначает задачи и планы, только советует
- **5 типов алертов:** weight_increase, food_incompatible, food_forbidden, no_response, bad_wellbeing
- **Триггеры:** SECURITY INVOKER + SET search_path (прошли Security Advisor)
- **VIEW:** SECURITY INVOKER (безопасность, RLS работает корректно)
- **timestamp → message_timestamp/action_timestamp** — избежание конфликта с зарезервированным словом PostgreSQL
- **queries.py:** 42 функции охватывают все сценарии из ТЗ v1.3 (раздел 12)

## Следующий шаг
**Этап 3:** Создание business_rules/ — детерминированный слой (access_rules, medical_rules, payment_rules, notification_rules)