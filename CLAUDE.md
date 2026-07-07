# CLAUDE.md — Контекст проекта для ИИ-ассистента

## Что это за проект
Агент-ассистент для нутрициолога. Два режима работы:
- **Режим нутрициолога:** аналитика клиентов, управление планами, сводки
- **Режим клиента:** ежедневный диалог, дневник питания, фото еды, голосовые сообщения

## Репозиторий
github.com/viktorsula/nutritionist-agent

## Деплой
Render: nutritionist-agent-gvxp.onrender.com

## Стек
- Python 3.11
- LangGraph (оркестрация агентов)
- Supabase (база данных, Auth, Storage, pgvector)
- Streamlit (веб-интерфейс)
- Telegram Bot / python-telegram-bot (основной канал клиента)
- Groq llama-3.3-70b (диалог, бесплатно)
- Claude Sonnet (аналитика, ~$3/M токенов)
- Gemini 2.5 Flash (фото/vision; 1.5 снята Google 06.2026). Модели/резерв — в system_settings.llm_config, правятся нутрициологом в окне «Настройки → LLM-модели» (живой список моделей, «Проверить», резерв). Новый OpenAI-совместимый провайдер — конфигом через llm_config._providers (base_url+api_key_env), без кода
- OpenAI Whisper (голос → текст, v1.1)
- n8n cloud (автоматизация расписаний)
- LangFuse (мониторинг и трейсинг)

## Архитектура
Telegram / Streamlit
↓
router.py
↓
business_rules  ←→  Supabase (queries.py)
↓
orchestrator.py (LangGraph)
↓
агенты
↓
llm.py → Groq / Claude / Gemini
↓
сохранить в Supabase → ответ
## Роли и правила

### Роли пользователей:
- **nutritionist** (Нутрициолог) — v1.0 ✅
  - Полный доступ ко всем данным и функциям
  - Единственный источник назначений (планы, задачи, пороги)
  
- **client** (Клиент) — v1.0 ✅
  - Доступ только к своим данным
  - Исполнитель и информатор
  
- **observer** (Наблюдатель) — зарезервировано для v2.0 (продакшн-версия для клиник)
  - Ассистент нутрициолога / родственник клиента
  - Права: только чтение данных назначенных клиентов + комментарии
  - В v1.0: роль существует в БД, но недоступна в интерфейсах

### Философия системы:
- **Нутрициолог** = единственный источник назначений (планы, задачи, пороги)
- **Агент** = аналитик и советник для нутрициолога
- **Клиент** = исполнитель и информатор

## База данных Supabase ✅ ГОТОВА (v1.3)
Проект: nutritionist-agent (FREE tier)  
Security Advisor: **0 errors, 0 warnings**  
Схема: `docs/schema.sql` (актуализирована 8 июня 2026)

### Таблицы (14):
**Блок 1 — Пользователи и профили:**
- `users` — единый источник для Supabase Auth (role: nutritionist/client)
- `clients` — профили клиентов (статусы: client_status, payment_status, access_status)
- `client_profiles` — медданные, аллергии, цели, индивидуальные пороги алертов
- `wellness_plans` — планы ЗОЖ: сон, активность, восстановление, стресс

**Блок 2 — Коммуникация:**
- `conversations` — история диалогов (channel: telegram/web), поле: message_timestamp
- `client_events` — журнал событий с severity (low/medium/high/critical)

**Блок 3 — Рабочие инструменты:**
- `nutrition_plans` — планы питания + БАДы (supplements_json), версионирование
- `tasks` — задачи клиентам, связь с plan_id

**Блок 4 — Инфраструктура:**
- `notification_schedule` — персональное расписание (timezone-aware)
- `audit_logs` — полный аудит всех действий, поле: action_timestamp
- `system_settings` — настройки и пороги алертов (без правки кода)

**Блок 5 — Документы и pgvector:**
- `document_metadata` — метаданные документов (источники, тип, привязка к клиенту)
- `knowledge_base` — база знаний, чанки с эмбеддингами (pgvector, vector(1536))
- `client_documents` — документы клиентов, чанки с эмбеддингами (pgvector, vector(1536))

### View (1):
- `client_registry_view` — реестр клиентов с агрегацией (SECURITY INVOKER)

### Триггеры (2):
- `trg_plan_version` — автоинкремент версии плана по клиенту
- `trg_deactivate_old_plans` — деактивация старого плана при создании нового

### Индексы:
- `idx_knowledge_base_embedding` — ivfflat для векторного поиска (cosine)
- `idx_client_documents_embedding` — ivfflat для векторного поиска (cosine)
- + стандартные индексы для conversations, client_events, tasks, audit_logs

## Система алертов (5 типов)
Все пороги настраиваются нутрициологом — глобально в system_settings,
индивидуально в client_profiles:

| Алерт | Триггер | Источник |
|-------|---------|----------|
| `weight_increase` | Вес > порог за день | client_events (event_type: 'weight_logged') |
| `food_incompatible` | Несочетаемые продукты | knowledge_base (pgvector поиск) |
| `food_forbidden` | Запрещённый продукт | nutrition_plans (restrictions) |
| `no_response` | Нет ответа N часов | conversations (message_timestamp) |
| `bad_wellbeing` | "нехорошо" + причина на чек-ин | client_events (severity + payload_json) |

## Business Rules (детерминированный слой)
Обрабатывают критические ситуации ДО вызова LLM:
business_rules/
├── access_rules.py      — check_access(), check_payment()
├── medical_rules.py     — check_medical_alerts(), check_allergies()
├── payment_rules.py     — проверка статуса подписки
└── notification_rules.py — расписание, timezone, on/off
## Структура проекта (план)
nutritionist-agent/
├── .env / .env.example
├── requirements.txt
├── Dockerfile
├── app.py                    ← Streamlit (точка входа веб)
├── database/
│   ├── client.py             ← подключение к Supabase
│   ├── models.py             ← dataclasses
│   └── queries.py            ← все функции работы с БД
├── business_rules/
│   ├── access_rules.py
│   ├── medical_rules.py
│   ├── payment_rules.py
│   └── notification_rules.py
├── utils/
│   ├── llm.py                ← call_llm(provider, model, messages, task_type)
│   ├── voice.py              ← Whisper (v1.1)
│   ├── vision.py             ← Gemini Flash
│   └── helpers.py
├── agents/
│   ├── router.py
│   ├── client/
│   │   ├── orchestrator.py
│   │   ├── dialog_agent.py
│   │   ├── nutrition_agent.py
│   │   ├── diary_agent.py
│   │   └── vision_agent.py
│   └── nutritionist/
│       ├── orchestrator.py
│       ├── analytics_agent.py
│       └── management_agent.py
├── telegram/
│   └── bot.py
├── monitoring/
│   └── langfuse.py
└── docs/
├── schema.sql            ← актуальная схема БД
└── progress.md
## Текущий статус (14 июня 2026)
> Этап 6 Часть A (ветка клиента) — код готов на ветке `stage6-utils` (не влита в main).
> Осталось: Telegram фото/голос (Шаг 3) + тесты (Шаг 4), затем Часть B (нутрициолог).
- [x] Репозиторий и деплой на Render
- [x] База данных Supabase v1.3 — ПОЛНОСТЬЮ ГОТОВА (14 таблиц + VIEW + триггеры)
- [x] schema.sql актуализирован (v1.3)
- [x] Блок 5: document_metadata + pgvector + knowledge_base + client_documents
- [x] **database/client.py** — подключение к Supabase готово
- [x] **database/models.py** — 14 моделей готовы
- [x] **database/queries.py** — 43 функции реализованы (добавлена get_setting())
- [x] **business_rules/** — ГОТОВО ✅
  - [x] access_rules.py — проверка доступа (анкета, оплата, режимы)
  - [x] medical_rules.py — 5 типов алертов + маршрутизация
  - [x] notification_rules.py — проверка расписания (timezone-aware)
- [x] **utils/** — ГОТОВО ✅
  - [x] llm.py — мультипровайдерный LLM клиент (Groq, Claude, Gemini)
  - [x] helpers.py — вспомогательные функции (структура готова)
  - [x] knowledge.py — эмбеддинги ada-002 + pgvector-поиск (Этап 6)
  - [x] vision.py — фото еды через Gemini Flash (Этап 6)
  - [x] voice.py — Whisper (Этап 6)
  - [x] web_access.py — Tavily + доверенные домены (Этап 6)
- [x] **prompts/** — ГОТОВО ✅
  - [x] Система управления промптами (БД приоритет → файлы fallback)
  - [x] client/dialog_system.md — промпт для диалога
  - [x] nutritionist/analytics_system.md — промпт для аналитики
- [x] **agents/** — ГОТОВО (базовая инфраструктура) ✅
  - [x] router.py — входной маршрутизатор (роль → ветка) + observer
  - [x] client/orchestrator.py — LangGraph граф + роутинг (ingest→load_context→route→[vision|diary|nutrition|dialog]→format→save)
  - [x] client/dialog_agent.py — работающий агент диалога
  - [x] client/vision_agent.py — фото еды (Этап 6)
  - [x] client/diary_agent.py — дневник текстом: еда/вес/самочувствие (Этап 6)
  - [x] client/nutrition_agent.py — вопросы о рационе, Claude (Этап 6)
  - [x] client/food_analysis.py — общий анализ состава против рациона (DRY)
  - [x] nutritionist/orchestrator.py — заглушка (TODO аналитика)
  - [ ] analytics_agent, management_agent ← Этап 6 Часть B
- [x] **app.py** — ОБНОВЛЁН ✅
  - [x] Интеграция с agents/router.py
  - [x] Поддержка 3 ролей (client, nutritionist, observer)
  - [x] Ветка клиента: чат через dialog_agent
  - [x] Ветка нутрициолога: заглушка с табами
- [x] **telegram/** — ГОТОВО (базовый функционал) ✅
  - [x] bot.py — основной бот (python-telegram-bot)
  - [x] commands.py — /start, /help, /status
  - [x] handlers.py — текст (работает); фото/голос ← Шаг 3 (контракт metadata готов)
  - [x] test_bot.py — тесты команд и обработчиков
- [x] monitoring/langfuse.py — РЕАЛИЗОВАН (подключён через _trace() в utils/llm.py::call_llm; graceful no-op без ключей/пакета)

## Следующий шаг
**Этап 6 Часть A — Шаг 3:** telegram/handlers.py — подключить фото/голос к графу
(metadata: image_bytes+mime_type / audio_bytes+audio_name). Затем Шаг 4 (тесты) → Часть B.

## Важно перед продолжением
⚠️ **Установить зависимости:** `pip install -r requirements.txt` (новые: openai, tavily)
⚠️ **Выполнить миграции в Supabase (SQL Editor):**
- `docs/migrations/001_add_observer_role.sql` — роль observer — ⏳ ожидает
- `docs/migrations/002_add_vector_search.sql` — RPC векторного поиска (Этап 6) — ⏳ ожидает
⚠️ **Ключи окружения:** OPENAI_API_KEY, TAVILY_API_KEY, GOOGLE_API_KEY

business_rules/ готов и протестирован:
- `access_rules.py` — 2 режима работы (full_program, ai_support)
- `medical_rules.py` — 5 типов алертов + determine_routing() для маршрутизации
- `notification_rules.py` — timezone-aware проверки расписания
- Все импорты работают ✅

## Важные решения (зафиксированы)
1. `wellness_plans` отдельно от `nutrition_plans` —
   "как жить" vs "что есть"
2. `supplements_json` отдельное поле в nutrition_plans —
   гибко для фрилансера и клиники
3. Индивидуальные пороги алертов в `client_profiles` —
   переопределяют глобальные из system_settings
4. `created_by = 'nutritionist'` only в plans и tasks —
   агент не назначает, только советует
5. Триггеры версионирования с SECURITY INVOKER + SET search_path —
   прошли Security Advisor Supabase без ошибок
6. `bad_wellbeing` алерт включает обязательную причину в payload_json
## Документация
- `docs/schema.sql` — актуальная схема БД
- `docs/progress.md` — журнал прогресса  
- `docs/technical_specification.docx` — полное ТЗ v1.2
## Правила работы с разработчиком

### Обязательно перед каждым действием:
1. Покажи план что собираешься сделать
2. Жди подтверждения перед началом
3. Не выполняй несколько шагов сразу без подтверждения каждого

### Язык общения:
- Всегда отвечай и задавай вопросы на русском языке
- Технические термины (названия функций, переменных) оставляй как есть

### Безопасность (критично):
- НИКОГДА не используй load_dotenv() 
- НИКОГДА не хардкодь ключи и credentials в коде или командах
- Всегда используй os.environ.get() для всех секретов
- Если видишь необходимость использовать ключи — спроси меня

### Стиль работы:
- Объясняй что делаешь и почему
- Если есть несколько вариантов решения — покажи варианты и жди выбора
- При ошибках объясняй причину понятным языком

## Владелец проекта
Виктор Сула, Дубай.