# Журнал прогресса проекта

## Статус: В разработке → ПРОД на Render (поднимается)
Последнее обновление: 22 июня 2026 (вечер)
Сессия: Фаза 3 слита в main (PR #1–3) + продакшен-деплой на Render
Ветка: Фаза 3 в `main`; рабочая `stage6-utils` синхронизирована

### Деплой 22 июня 2026 (продакшен)
- **Бэкенд** (FastAPI/Docker→uvicorn) на Render: https://nutritionist-agent-gvxp.onrender.com — `/health` ок.
- **Фронт** (React Static Site) на Render: https://nutritionist-agent-1-ljzi.onrender.com.
- Чинили деплой: requirements ResolutionImpossible (ptb 20.7 httpx ↔ supabase → ptb>=21; убран
  streamlit/protobuf-конфликт); Dockerfile→uvicorn; SPA deep-link → `404.html`=index.html на сборке.
- CORS_ORIGINS бэкенда = URL фронта (ок); Supabase Auth Site URL/Redirect = URL фронта (ок).
- OpenAI + Anthropic **оплачены** → ИИ полноценный. Миграции 001–008 применены (проверено интроспекцией).
- **⏳ ОТКРЫТО (старт следующей сессии):** белый экран фронта — не вшиты `VITE_SUPABASE_URL`/
  `VITE_SUPABASE_ANON_KEY`. Задать на Static Site + Manual Deploy (Clear cache) → рендер входа → smoke-тест.

### Сессия 22 июня 2026 — кабинет нутрициолога: 3 панели, аналитика-RAG, отчёты, настройки
- **Раскладка в 3 панели** (`NutritionistShell`): слева инструменты, центр — рабочая
  область, справа — постоянный чат; ресайз границы центр↔чат и скрытие чата (localStorage).
- **Создание клиента со статусами** (миграция `007_client_paid_until.sql`): оплата
  (active/inactive), режим базовый/полный → client_status (тариф из статуса), `paid_until`.
  Гейт входа уже работал (`check_web_access`). API `/clients` + `invite_client_account` расширены.
- **Фильтры реестра** по столбцам (имя/статус/оплата/цель) + столбец «Оплачено до»;
  локализация значений статусов/оплаты (`registry.status_value`/`payment_value`/`access_value`).
- **Индикатор истечения тарифа** (`expiry.ts`): в реестре (цвет + «ещё N дн./истёк»),
  в «Алертах» секция «Истекает тариф» (paid_until ≤ сегодня+2). Telegram-уведомление за 2 дня — n8n (позже).
- **Блок 2: агент наполняет центр** — директива вида в ответе агента
  (`orchestrator._build_view_directive`, `state.view`): клиент→карточка, аналитика→панель.
  `ClientCard` переведён на самозагрузку по `clientId`. Мини-дашборд `AnalyticsPanel` (воронка+счётчики).
- **Аналитика — RAG-конвейер** (`analytics_agent`, v1: клиент+vector, web позже): план(Groq) →
  контекст беседы → данные клиента(SQL/JSON) → vector (client_documents+knowledge_base) →
  синтез(analytics LLM) → `state.analysis` {title, markdown, charts}. Панель «Аналитика» рисует
  markdown (`react-markdown`) + графики из реальных данных БД.
- **Карточка клиента**: лента «События» прокручиваемая (до 50), алерты подсвечены, галка «Только алерты».
- **Отчёты** (миграция `008_client_reports.sql`): `agents/nutritionist/reports.py` (LLM по шаблону),
  эндпоинты `/nutritionist/report(-types)`; `ReportsCard` — генерация→правка→сохранение→выгрузка
  PDF (печать браузера, кириллица) + TXT + список. Шаблон формы Екатерины Юровой в
  `prompts/nutritionist/reports/recommendations_for_clients.md`.
- **Настройки (перенос со Streamlit)**: каталог показателей + пороги алертов + доверенные
  источники + llm_config (system_settings под RLS) + редактор промптов (эндпоинты
  `/nutritionist/prompt(s)`). Компоненты в `features/nutritionist/settings/`.
- **Применены миграции** Supabase: 007, 008.
- **Коммит + PR:** ветка `stage6-utils` → `main`, PR #1.
- **Пост-PR фиксы (22 июня):**
  - **pgvector-формат:** `query_embedding`/`embedding` в RPC `match_*` и в INSERT чанков
    передаются как pgvector-литерал `'[...]'` (`queries._vector_literal`) — PostgREST не
    кастует JSON-массив → vector. Конфликт сервис↔БД устранён (проверить нельзя, пока OpenAI 429).
  - **Dockerfile:** точка входа `uvicorn api.main:app` на `$PORT` (вместо Streamlit/8501);
    requirements актуализированы (Streamlit → legacy).
  - **analytics_system.md → тема-адаптивный:** анализ строится вокруг вопроса; при отсутствии
    данных по теме — честно «данных нет: …» + что собрать, без generic-«весовой» простыни.
- **Среда (блокеры качества):** OpenAI ключ — 429 insufficient_quota (эмбеддинги/vector не
  работают); Claude — без кредитов (синтез на резерве Groq/Gemini). Векторный фикс не проверен.
- **Не сделано (по плану позже):** web-шаг аналитики и анализ группы клиентов (ждут Claude);
  аудит правок настроек из фронта; PDF одним кликом (jsPDF+кириллический шрифт).

### Сессия 20 июня 2026 — кабинет клиента (React) + отказоустойчивость LLM
- **Запуск локально:** FastAPI (`api/`) :8000 + Vite (`frontend/`) :5173 в Codespaces;
  порт 8000 — public (кросс-доменный fetch фронта к API); окружение API из `.env` без load_dotenv.
- **Загрузка анализов:** миграция `005_storage_client_documents.sql` (бакет `client-documents`
  + storage-RLS); санитизация ключей Storage (кириллица/скобки ломали «Invalid key»).
- **Ассистент видит данные клиента:** `queries.get_latest_measurement/get_recent_lab_results`,
  загрузка в контекст (`orchestrator.load_context_node`), общий `build_health_lines`
  (вес + анализы с динамикой) в dialog/nutrition; промпты разрешают озвучивать СВОИ данные
  (факты + лёгкая трактовка, без диагнозов). Вопросы о своих данных → роутинг на Groq.
- **Взаиморезервирование LLM** (`utils/llm.py`): `TASK_FALLBACK_CHAINS` + перебор кандидатов;
  при сбое модели автопереключение (Claude→Groq→Gemini; vision→Claude), иначе
  `LLMUnavailableError` + «подождите и повторите». Claude без кредитов → работает резерв.
- **UX чата:** авто-ресайз поля ввода; панель чата фиксирована на экране (внутренний скролл)
  и шире на 30% за счёт центральной панели (`ClientShell` 300/1fr/468).
- **Per-client показатели анализов (реализовано):** миграция `006_tracked_lab_indicators.sql`
  (колонка `client_profiles.tracked_lab_indicators` JSONB); редактор нутрициолога
  `LabIndicatorsManager` (вкладка «Показатели анализов»: клиент → key/label/unit/нормы/порядок,
  каталог из `lab_indicators_top`); клиентский график рисует только выбранное (с полосой нормы
  ReferenceArea + плейсхолдер); ассистент использует нормы для лёгкой трактовки.
  Ввод значений анализов — форма `LabValuesForm` в той же вкладке (insert в `lab_results`,
  source='nutritionist', + список последних значений).
- **Панель алертов нутрициолога (реализовано):** вкладка «Алерты» (первая) — `AlertsPanel`
  читает `client_events` (severity ∈ medium/high/critical) под RLS + join clients(name);
  фильтры окно/severity, цвет по уровню. Добавлен персист `weight_increase` как severity-события
  в `diary_agent` (раньше в панель не попадал).
- **Реестр + карточка клиента (реализовано):** вкладка «Реестр клиентов» — `Registry` (список из
  clients + профиль, создание клиента) → клик открывает `ClientCard`: профиль (цель/пол/возраст/
  вес/аллергии/хронические/ограничения), план питания + ЗОЖ, задачи, график веса и анализов
  (с нормами), последние события, редактируемые заметки нутрициолога (update clients под RLS).
  Переиспользует хуки client/queries; новые — features/nutritionist/queries.ts.
- **Чат нутрициолога с агентом (реализовано):** вкладка «Ассистент-агент» — `NutritionistChat`
  шлёт запросы в `/nutritionist/query` (analytics + management с двухшаговым подтверждением;
  pending_action хранится на бэке по nutritionist_id). Исправлен баг: analytics_agent и
  management_agent звали `call_llm(task_type='analysis')` — нет такого типа → теперь 'analytics'
  (с взаимозаменой Claude→Groq/Gemini). Проверено: сводка и создание задачи отвечают на Groq.
- **Редактор планов/задач (реализовано):** в карточке клиента — `TaskEditor` (список + создание
  задач + смена статуса done/cancel) и `PlanEditor` (история версий + создание нового плана:
  деактивируем старый активный ДО вставки нового — EXCLUDE «один активный план», триггер
  деактивации AFTER INSERT; version проставляет триггер). plan_json: description/target_calories/
  restrictions, supplements_json.items. Всё под RLS (nutritionist); логика проверена на БД.
- **Редактор ЗОЖ-плана (реализовано):** `WellnessEditor` в карточке клиента — редактирует
  последнюю запись `wellness_plans` (update по id) либо создаёт первую (insert): сон/активность/
  восстановление/стресс/заметки. Под RLS; проверено на БД.

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
  - [x] router.py — входной маршрутизатор (роль → ветка агентов) + обработка observer
  - [x] client/state.py — ClientState TypedDict для LangGraph
  - [x] client/orchestrator.py — LangGraph граф (5 узлов: load_context → check_alerts → dialog_agent → format_response → save_to_db)
  - [x] client/dialog_agent.py — работающий агент диалога (использует Groq llama-3.3-70b)
  - [x] nutritionist/orchestrator.py — заглушка (направление к
   веб-интерфейсу)
- [x] **app.py** — веб-интерфейс обновлён ✅
  - [x] Интеграция с agents/router.py (вместо прямого ChatGroq)
  - [x] Поддержка 3 ролей: client ✅, nutritionist ✅, observer (зарезервирован)
  - [x] Ветка клиента: чат работает через dialog_agent
  - [x] Ветка нутрициолога: заглушка с табами (Реестр, Аналитика, Настройки)
- [x] **Миграции БД** — создана система миграций ✅
  - [x] docs/migrations/001_add_observer_role.sql — добавить observer в users.role
  - [x] docs/migrations/README.md — инструкции по применению
  - [x] docs/schema.sql обновлён (v1.3.1 — observer включён)
- [x] **telegram/** — Telegram бот готов ✅
  - [x] bot.py — основной бот (python-telegram-bot)
  - [x] commands.py — /start, /help, /status (работают)
  - [x] handlers.py — текст через route_message(), фото/голос (заглушки для Этапа 6)
  - [x] test_bot.py — тесты команд и обработчиков
  - [x] README.md — документация

### Этап 6 — Часть A (ветка клиента) — ✅ КОД ГОТОВ (на ветке stage6-utils)
- [x] **requirements.txt** — +openai (ada-002 + Whisper); убраны chromadb/sentence-transformers;
      модернизирован LangGraph (langgraph>=1.0, langchain-core>=0.3, сняты langchain*/langsmith-пины)
- [x] **docs/migrations/002_add_vector_search.sql** — RPC match_knowledge_base / match_client_documents (cosine, pgvector)
- [x] **database/queries.py** — обёртки search_knowledge_base / search_client_documents (supabase.rpc)
- [x] **utils/knowledge.py** — get_embedding (OpenAI ada-002, 1536) + семантический поиск + сборка контекста
- [x] **utils/vision.py** — analyze_image + analyze_food_plate (приоритет: состав/ингредиенты/форма; КБЖУ вторично) + extract_ingredient_names
- [x] **utils/voice.py** — transcribe_voice (OpenAI Whisper)
- [x] **utils/web_access.py** — build_web_search_tool() (серверный инструмент Claude web_search) + allowed_domains из trusted_sources [обновлено 19 июня: Tavily убран]
- [x] **agents/client/food_analysis.py** — общий анализ состава против рациона (DRY): analyze_against_plan / determine_food_routing / highest_severity
- [x] **agents/client/vision_agent.py** — фото еды: 3 исхода, анализ против рациона, событие calories_logged, уведомление нутрициолога при отклонениях
- [x] **agents/client/diary_agent.py** — дневник текстом: ветки meal/weight/wellbeing/other; события weight_logged/bad_wellbeing/calories_logged
- [x] **agents/client/nutrition_agent.py** — вопросы о рационе (Claude); знания: knowledge_base + client_documents (pgvector) + веб через серверный инструмент Claude web_search с allowed_domains из system_settings.trusted_sources
- [x] **prompts/client/** — vision_system.md, diary_system.md, nutrition_system.md
- [x] **agents/client/orchestrator.py** — роутинг: ingest(голос→текст) → load_context → route → [vision|diary|nutrition|dialog] → format_response → save_to_db; удалён check_alerts_node
- [x] **Фиксы:** save_to_db (insert_conversation→save_conversation + _sanitize_metadata); поля state route/food_items

### Этап 6 — Часть A — Шаги 3–4 — ✅ ЗАВЕРШЕНО (18 июня 2026)
- [x] **Шаг 3:** tg_bot/handlers.py — фото и голос подключены к графу
  - фото: скачивание наибольшего размера → `metadata['image_bytes']` + `mime_type='image/jpeg'`, caption → message, `message_type='photo'` → vision
  - голос: скачивание .ogg → `metadata['audio_bytes']` + `audio_name`, `message_type='voice'`, транскрипция в узле ingest оркестратора (Whisper)
  - вынесена общая логика `_ensure_registered()` + `_dispatch_to_router()` (DRY для text/photo/voice)
- [x] **Шаг 4:** тесты + прогон
  - tg_bot/test_bot.py: переведён на `IsolatedAsyncioTestCase` (раньше async-тесты не исполнялись), +4 теста фото/голоса → 10/10 ✅
  - agents/test_agents.py: 7/7 ✅
- [x] **Фикс коллизии имён:** пакет `telegram/` → `tg_bot/` (затенял библиотеку python-telegram-bot; `from telegram.ext` ломался). Обновлены импорты в test_bot.py + README. `bot.py`/`commands.py`/`handlers.py` используют относительные импорты — не тронуты.
- [x] **Фикс:** убран мёртвый импорт `get_user_by_id` в tg_bot/commands.py (ломал загрузку пакета)

## В процессе

### Код (Этапы по ТЗ v1.3)
- [x] **Этап 2:** database/ — ЗАВЕРШЁН ✅
- [x] **Этап 3:** business_rules/ — ЗАВЕРШЁН ✅
- [x] **Этап 4:** utils/ — ЗАВЕРШЁН (базовые модули) ✅
- [x] **Этап 5:** agents/ + prompts/ — ЗАВЕРШЁН (базовая инфраструктура) ✅
- [x] **Этап 7 (часть 1):** app.py — ЗАВЕРШЁН (веб-интерфейс интегрирован с agents/) ✅
- [x] **Этап 7 (часть 2):** telegram/bot.py — ЗАВЕРШЁН (базовый функционал) ✅
- [x] **Этап 6 Часть A (клиент):** vision/diary/nutrition агенты + utils + роутинг + Telegram фото/голос + тесты — ЗАВЕРШЕНО ✅
- [x] **Этап 6 Часть B (нутрициолог):** analytics_agent + management_agent — ЗАВЕРШЕНО ✅
  - state.py — NutritionistState + helpers (thread нутрициолога, pending_action)
  - orchestrator.py — реальный LangGraph граф: parse_request → [analytics|management|help] → format_response → save_to_db (заменил заглушку; общий для Telegram и web)
  - parse_request — классификатор intent (Groq) + резолв клиента по имени + детект подтверждения/отмены
  - analytics_agent.py — read-only анализ клиента/базы (Claude), промпт analytics_system.md
  - management_agent.py — запись через ДВУХШАГОВОЕ ПОДТВЕРЖДЕНИЕ (pending_action в conversations.metadata_json); действия: create_task / create_nutrition_plan / update_client_status / add_trusted_source; всё с created_by='nutritionist' + write_audit_log
  - prompts/nutritionist/management_system.md — разбор команды в строгий JSON
  - тесты: agents/nutritionist/test_nutritionist.py — 13/13 ✅
- [x] **Этап 8:** app.py (полный интерфейс нутрициолога) — ЗАВЕРШЕНО ✅
  - [x] Шаг 1: Реестр + Аналитика — web/nutritionist.py (render_registry / render_analytics);
        queries.get_client_registry() (из client_registry_view); AI-анализ через analytics_node
  - [x] Шаг 2: Настройки — render_settings(): пороги алертов (JSON), trusted_sources (список +
        добавление/удаление), редактор промптов (list/load/save_prompt), llm_config (JSON);
        запись через update_system_setting + write_audit_log
  - [x] тесты web/test_nutritionist_views.py — 10/10 ✅
- [x] **Этап 9:** monitoring/langfuse.py — ЗАВЕРШЕНО ✅
  - monitoring/langfuse.py — обёртка LangFuse: trace_llm_call / is_enabled / flush; graceful no-op без SDK/ключей, трейсинг никогда не роняет вызов LLM
  - utils/llm.py — call_llm трейсит каждый вызов (тайминг + успех/ошибка) через _trace(); удалена старая закомментированная заготовка
  - единая точка: все агенты (клиент + нутрициолог) трейсятся автоматически
  - тесты monitoring/test_monitoring.py — 7/7 ✅

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

## TODO (вне текущего фронта)
- **Telegram-резолв роли:** `agents/router.py:get_user_info()` зовёт несуществующие
  `queries.get_user()`/`queries.get_user_by_telegram_id()` → Telegram-путь возвращает
  «user_not_found». Веб обходит через `database/auth.py`. Починить: добавить
  `get_user_by_telegram_id`/`get_user_by_auth_id` в `queries.py`.

## Следующий шаг
**Дорожная карта ТЗ v1.3 (Этапы 1–9) — ПОЛНОСТЬЮ ЗАВЕРШЕНА.** ✅
Остаётся подготовка к продакшену перед слиянием `stage6-utils` → `main`:
1. Применить миграции в Supabase (001 observer, 002 vector search)
2. Прописать ключи в Render (OPENAI / GOOGLE / TELEGRAM_BOT_TOKEN / LANGFUSE_*); включить web search в Claude Console
3. Живой smoke-тест (сообщение клиента + запрос нутрициолога + фото/голос)
4. PR `stage6-utils` → `main` (автодеплой выкатит рабочую версию)

## Важно перед запуском
⚠️ **Установить зависимости:** `pip install -r requirements.txt` (новое: openai; tavily удалён)
⚠️ **Выполнить миграции в Supabase (SQL Editor):**
- `docs/migrations/001_add_observer_role.sql` — роль observer — ⏳ ожидает
- `docs/migrations/002_add_vector_search.sql` — RPC векторного поиска — ⏳ ожидает
⚠️ **Ключи окружения:** OPENAI_API_KEY (эмбеддинги+Whisper), GOOGLE_API_KEY (vision); веб-поиск — серверный инструмент Claude web_search (ключ не нужен, включить в Console)
⚠️ **Пред­существующий конфликт:** streamlit 1.32.0 ↔ protobuf 5.29.6 — разобрать перед запуском веба

## Ключевые решения Этапа 6 (14 июня 2026)
- **Эмбеддинги:** OpenAI text-embedding-ada-002 (1536 = схема, миграция БД не нужна)
- **Голос:** перенесён в Часть A (делаем сразу), Whisper через openai
- **Vision приоритет:** состав/ингредиенты/форма приготовления первичны, КБЖУ вторично (для контроля рациона)
- **DRY:** общий food_analysis.py для vision и diary
- **Знания nutrition_agent:** knowledge_base + client_documents (pgvector) + веб через серверный инструмент Claude web_search с allowed_domains из system_settings.trusted_sources (редактирует нутрициолог/агент по его команде)
- **[19 июня] Веб-поиск: Tavily → Claude web_search.** ТЗ механизм не задавало; Tavily был выбором Этапа 6. Переведено на встроенный серверный инструмент Claude (web_search_20250305): минус зависимость и ключ, контроль источников сохранён через allowed_domains. Требует включения web search в Claude Console.
- **Роутинг:** photo→vision (без LLM), текст→Groq-классификатор (diary|nutrition|dialog); check_alerts_node убран (алерты формируют агенты)
- **LangGraph модернизирован:** код использует только StateGraph/END → апгрейд до langgraph 1.x безопасен