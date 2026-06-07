# Журнал прогресса проекта

## Статус: В разработке
Последнее обновление: июнь 2026 (День 2)

## Выполнено

### Инфраструктура
- [x] Репозиторий создан на GitHub
- [x] Среда разработки: GitHub Codespaces
- [x] CLAUDE.md создан — контекст для ИИ
- [x] docs/progress.md — журнал прогресса
- [x] .env.example — шаблон всех ключей
- [x] .gitignore — защита секретов
- [x] .env — реальные ключи Supabase заполнены
- [x] Supabase проект создан: nutritionist-agent

### База данных Supabase

#### Блок 1: Пользователи и профили ✅
- [x] users (роли: nutritionist/observer/client)
- [x] clients (воронка + оплата + subscription_start/end_date)
- [x] client_profiles (медицинский профиль)
- [x] wellness_plans (Health Coaching план)
- [x] RLS включён на всех таблицах

#### Блок 2: Память агента ✅
- [x] conversations (история диалогов, thread_id)
- [x] client_events (лента событий: вес, сон, еда, алерты)
- [x] Индексы для быстрого поиска
- [x] RLS включён

## В процессе

### База данных Supabase
- [ ] Блок 3: nutrition_plans + tasks
- [ ] Блок 4: notification_schedule + audit_logs + system_settings
- [ ] Блок 5: client_documents_metadata + knowledge_base_metadata
- [ ] Блок 6: pgvector (client_documents_embeddings + knowledge_base_embeddings)
- [ ] Блок 7: client_registry_view

### Этапы разработки
- [ ] Этап 1: requirements.txt обновить под новый стек
- [ ] Этап 3: business_rules/
- [ ] Этап 4: utils/
- [ ] Этап 5: agents/
- [ ] Этап 6: telegram/
- [ ] Этап 7: app.py (обновить)
- [ ] Этап 8: monitoring/

## Ключевые решения принятые в День 2

### Архитектура
- Нутрициолог = единственный источник назначений
- Агент = советник и аналитик (предлагает нутрициологу)
- Клиент общается как ему удобно (фото/текст/голос)

### База знаний
- Два физически разных хранилища (клиент ≠ библиотека)
- Два типа веб-доступа (curated/open web)
- Агент активно ходит на сайты добавленные нутрициологом

### Данные о питании
- Фото → Gemini Vision → уточнение если нужно
- Текст → агент уточняет состав и способ приготовления
- Все данные: calories, protein, fat, carbs, interval_from_last_h

### Wellness план
- Отдельная таблица (не часть nutrition_plans)
- Блоки: sleep, physical_activity, recovery, stress_management
- Клиент видит полностью, только нутрициолог создаёт

## Следующий шаг (День 3)
Блок 3 БД: обсудить и выполнить nutrition_plans + tasks
Вопрос для обсуждения: структура плана питания
(свободный текст / структурированный JSON / гибридный)

## Открытые вопросы
- Telegram: нужен новый бот или используем существующий?
- nutrition_plans: формат хранения плана (обсудить в День 3)