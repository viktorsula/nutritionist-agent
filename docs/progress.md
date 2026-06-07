# Журнал прогресса проекта

## Статус: В разработке
Последнее обновление: июнь 2026

## Выполнено

### Инфраструктура
- [x] Репозиторий GitHub: viktorsula/nutritionist-agent
- [x] Среда разработки: GitHub Codespaces → переход на Claude Code
- [x] Деплой на Render: nutritionist-agent-gvxp.onrender.com
- [x] Базовый app.py на Streamlit задеплоен
- [x] .env.example — шаблон всех ключей
- [x] .gitignore — защита секретов
- [x] Supabase проект создан: nutritionist-agent (FREE tier)

### База данных Supabase (Блоки 1-4)
- [x] Блок 1: users, clients, client_profiles, wellness_plans
- [x] Блок 2: conversations, client_events
- [x] Блок 3: nutrition_plans (версионирование + триггеры), tasks
- [x] Блок 4: notification_schedule, audit_logs, system_settings
- [x] View: client_registry_view
- [x] Security Advisor: 0 errors, 2 warnings (системные, не наши)
- [x] docs/schema.sql актуализирован (v1.2)

## В процессе

### База данных
- [ ] Блок 5: document_metadata
- [ ] Блок 5: pgvector — включить расширение в Supabase
- [ ] Блок 5: коллекции knowledge_base, client_documents

### Код (Этапы по ТЗ)
- [ ] Этап 2: database/client.py, models.py, queries.py
- [ ] Этап 3: business_rules/
- [ ] Этап 4: utils/llm.py, vision.py, helpers.py
- [ ] Этап 5: agents/router.py + client/ + nutritionist/
- [ ] Этап 6: telegram/bot.py
- [ ] Этап 7: app.py (обновить под новую архитектуру)
- [ ] Этап 8: monitoring/langfuse.py

## Ключевые решения принятые в ходе разработки
- wellness_plans добавлен как отдельная таблица (не было в исходном ТЗ)
- supplements_json — отдельное поле в nutrition_plans (не внутри plan_json)
- Индивидуальные пороги алертов в client_profiles (переопределяют system_settings)
- created_by = 'nutritionist' only — агент не назначает задачи и планы
- 5 типов алертов: weight_increase, food_incompatible, food_forbidden,
  no_response, bad_wellbeing (с обязательной причиной)
- Триггеры: SECURITY INVOKER + SET search_path (прошли Security Advisor)

## Следующий шаг
Блок 5 БД в Supabase:
1. Включить расширение pgvector
2. Создать таблицу document_metadata
3. Создать коллекции knowledge_base и client_documents
Затем: database/client.py — первый файл кода