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
- Python 3.11 + FastAPI (бэкенд, точка входа `api/main.py`)
- LLM-оркестратор на tool-calling (`agents/*/agent_orchestrator.py`, `agent_adapter.py`) —
  ОСНОВНОЙ путь обработки для обеих ролей
- LangGraph — устаревший граф, оставлен как fallback при сбое оркестратора
- APScheduler (`api/scheduler.py`) — напоминания, алерты, отчёты, аудит (n8n НЕ используется)
- Supabase (база данных, Auth, Storage, pgvector)
- React SPA (Vite + TypeScript) — веб-интерфейс; FastAPI — бэкенд
- Telegram Bot / python-telegram-bot (основной канал клиента)
- Groq llama-3.3-70b (диалог, бесплатно)
- Claude Sonnet (аналитика, ~$3/M токенов)
- Gemini 2.5 Flash (фото/vision; 1.5 снята Google 06.2026). Модели/резерв — в system_settings.llm_config, правятся нутрициологом в окне «Настройки → LLM-модели» (живой список моделей, «Проверить», резерв). Новый OpenAI-совместимый провайдер — конфигом через llm_config._providers (base_url+api_key_env), без кода
- OpenAI Whisper (голос → текст)
- LangFuse (мониторинг и трейсинг)
- CI: GitHub Actions (`.github/workflows/ci.yml`) — тесты бэкенда и фронта на каждый PR

## Архитектура
Telegram (webhook, tg_bot/) / React SPA
↓
api/main.py (FastAPI)
↓
agents/router.py
↓
business_rules  ←→  Supabase (database/queries.py)
↓
agent_orchestrator.py — LLM с tool-calling (ОСНОВНОЙ путь)
   ↳ при сбое: откат на граф LangGraph (orchestrator.py)
↓
utils/llm.py → Claude / Groq / Gemini
↓
сохранить в Supabase → ответ

Долю ходов оркестратора и число откатов на граф видно в кабинете:
«Настройки → Покрытие оркестратором».
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

## База данных Supabase (v1.6 — миграции 001–021)
Проект: nutritionist-agent (FREE tier)
Схема: `docs/schema.sql` — консолидированное состояние, актуализирована 27 июля 2026.
Реестр миграций и verify-SQL для проверки дрейфа: `docs/migrations/README.md`.
⚠️ Миграции применяются ВРУЧНУЮ через Supabase → SQL Editor; после накатки отмечать в реестре.

### Таблицы (23):
**Блок 1 — Пользователи и профили:**
- `users` — единый источник для Supabase Auth (role: nutritionist/client/observer)
- `clients` — профили клиентов (статусы, `paid_until`, rolling-summary, токен привязки Telegram)
- `client_profiles` — медданные, аллергии, цели, анкета, индивидуальные пороги алертов
- `wellness_plans` — планы ЗОЖ: сон, активность, восстановление, стресс

**Блок 2 — Коммуникация:**
- `conversations` — история диалогов (channel: telegram/web), поле: message_timestamp
- `client_events` — журнал событий с severity (low/medium/high/critical)

**Блок 3 — Рабочие инструменты:**
- `nutrition_plans` — планы питания + БАДы (supplements_json), версионирование
- `tasks` — задачи клиентам, связь с plan_id

**Блок 4 — Инфраструктура:**
- `audit_logs` — полный аудит всех действий, поле: action_timestamp
- `system_settings` — настройки, пороги алертов, llm_config, rag_config (без правки кода)
- `notification_schedule` — ⚠️ LEGACY, пустая: путь уведомлений v0, заменён `reminders`

**Блок 5 — Документы и pgvector:**
- `document_metadata` — метаданные документов (источники, тип, привязка к клиенту)
- `knowledge_base` — база знаний, чанки с эмбеддингами (pgvector, vector(1536))
- `client_documents` — документы клиентов, чанки с эмбеддингами (pgvector, vector(1536))

**Блок 6 — Замеры, анализы, отчёты:**
- `measurements` — вес/шея/талия/бёдра/грудь во времени
- `lab_results` — числовые показатели анализов во времени
- `client_reports` — отчёты по клиенту (черновик → финал)

**Блок 7 — Напоминания и контроль ответа:**
- `reminders` — шаблоны напоминаний + параметры контроля ответа
- `reminder_occurrences` — срабатывания: дедуп отправки, детект ответа, догон, просрочка
- `client_metrics` — значения показателей: сон и произвольные (пульс, стресс)

**Блок 8 — Анкета, согласия, аудит:**
- `client_questionnaire_history` — история версий анкеты
- `client_consents` — согласия на обработку данных (LEGAL-1/5)
- `client_audit_findings` — находки проактивного аудита клиента (NEW-1)

### View (1):
- `client_registry_view` — реестр клиентов с агрегацией (SECURITY INVOKER)

### Триггеры (2):
- `trg_plan_version` — автоинкремент версии плана по клиенту
- `trg_deactivate_old_plans` — деактивация старого плана при создании нового

### Защита данных (LEGAL-3, миграция 019):
Все FK на `clients(id)` — `ON DELETE RESTRICT`. Физически удалить клиента с данными нельзя;
«удаление» в интерфейсе = архивирование (`client_status='archived'`). Требование закона ОАЭ —
хранение данных о здоровье ≥25 лет.

## Система алертов
Пороги настраиваются нутрициологом — глобально в `system_settings.alert_thresholds`,
индивидуально в `client_profiles.custom_alert_thresholds`.

`business_rules/medical_rules.py::check_medical_alerts()` — 4 проверки:

| Алерт | Триггер | Источник |
|-------|---------|----------|
| `weight_increase` | Вес > порог за день | measurements |
| `food_incompatible` | Несочетаемые продукты | knowledge_base (pgvector, порог похожести) |
| `food_forbidden` | Запрещённый продукт | nutrition_plans.plan_json.restrictions |
| `no_response` | Нет ответа N часов | conversations (message_timestamp) |

Отдельно, НЕ через `check_medical_alerts`:
- `bad_wellbeing` — создаётся в `agents/client/intake_store.py::_persist_wellbeing`, плюс
  независимый детерминированный скан симптомов в `agent_orchestrator` (P1-11): если модель
  сама не вызвала `log_wellbeing`, алерт всё равно создаётся.
- `meal_not_reported` / `reminder_unanswered` — просрочка ответа на напоминание (планировщик).
- `plan_exception_claimed` — клиент заявил, что нутрициолог разрешил исключение (P1-10).

⚠️ Матчинг запрещённых продуктов сейчас ПОДСТРОЧНЫЙ, не смысловой (открытая находка P1-13):
«козий сыр» не совпадёт с ограничением «молочные продукты». Переработка согласована —
см. `docs/docs/diagnostic_report.md`, блок решений по P1-13/P2-1.

## Business Rules (детерминированный слой)
Обрабатывают критические ситуации ДО вызова LLM:
business_rules/
├── access_rules.py   — check_access() (включает проверку оплаты: _payment_active)
└── medical_rules.py  — check_medical_alerts(), check_allergies()

Отдельного `payment_rules.py` НЕТ — логика оплаты живёт в `access_rules`.
`notification_rules.py` удалён в P2-4 вместе с мёртвым путём уведомлений v0.
## Структура проекта
```
nutritionist-agent/
├── README.md                 ← обзор, запуск, тесты, деплой
├── .env.example              ← ВСЕ env-ключи (паритет с кодом проверен)
├── Dockerfile                ← бэкенд: uvicorn api.main:app
├── .github/workflows/ci.yml  ← CI: pytest + tsc + vitest на каждый PR
├── api/
│   ├── main.py               ← FastAPI: роуты, гейты ролей
│   ├── auth.py               ← get_current_user / require_role
│   ├── scheduler.py          ← APScheduler: напоминания, алерты, отчёты, аудит
│   └── telegram_webhook.py   ← приём апдейтов Telegram
├── frontend/                 ← React SPA (кабинеты нутрициолога и клиента)
├── database/
│   ├── client.py             ← подключение к Supabase
│   ├── models.py             ← dataclasses
│   ├── auth.py               ← резолв пользователя по токену
│   └── queries.py            ← все функции работы с БД
├── business_rules/
│   ├── access_rules.py
│   └── medical_rules.py
├── utils/
│   ├── llm.py                ← call_llm(task_type=...) + tool-calling + резерв моделей
│   ├── knowledge.py          ← эмбеддинги + pgvector-поиск (порог релевантности)
│   ├── voice.py / vision.py  ← Whisper / Gemini
│   ├── notify.py             ← тексты алертов нутрициологу
│   ├── web_access.py         ← web_search + доверенные источники
│   └── mailer.py             ← Gmail SMTP (временный пароль клиенту)
├── agents/
│   ├── router.py             ← вход: роль, доступ, маршрутизация
│   ├── core/
│   │   ├── agent_engine.py   ← role-agnostic цикл tool-calling
│   │   └── coverage.py       ← счётчики «оркестратор vs откат на граф»
│   ├── client/
│   │   ├── agent_orchestrator.py  ← ОСНОВНОЙ путь (LLM + инструменты)
│   │   ├── orchestrator.py        ← граф LangGraph (fallback)
│   │   ├── intake_*.py            ← схема/валидация/запись фактов дня
│   │   └── food_analysis.py, vision_agent.py, diary_agent.py, …
│   └── nutritionist/
│       ├── agent_adapter.py       ← ОСНОВНОЙ путь (LLM + инструменты)
│       ├── orchestrator.py        ← граф (fallback)
│       ├── analytics_agent.py, management_agent.py, audit_agent.py, reports.py
├── prompts/                  ← системные промпты (.md); приоритет БД над файлами
├── tg_bot/                   ← Telegram-бот (handlers, turn-буфер)
├── monitoring/               ← LangFuse
└── docs/
    ├── schema.sql            ← схема БД (консолидированная)
    ├── migrations/           ← SQL-миграции + README с реестром
    ├── progress.md           ← журнал сессий
    └── docs/diagnostic_report.md  ← мастер-список находок и решений
```

## Текущий статус (27 июля 2026)
> **Источники правды:** прогресс — `docs/progress.md`; находки и решения —
> `docs/docs/diagnostic_report.md`; состояние БД — `docs/migrations/README.md`.
> Здесь — только краткий снимок.

Ресурс временно отключён от клиентов; включается в тестовом режиме на этой неделе после
устранения находок и наполнения базы знаний.

**22–27 июля 2026 — полная диагностика и устранение находок.** Мастер-список: 6 юридических +
5 P0 + 15 P1 + 22 P2 + 1 новая фича. Устранялось по одному PR за раз, каждый влит в main.

Закрыто: **все P0 и LEGAL-блокеры** (алерты по еде, заземление контекста, web_search,
согласие на обработку данных, защита от tool-calling-регрессии, RESTRICT на удаление),
**NEW-1** (проактивный аудит клиента), **P1-3…P1-12** (пороги алертов, читаемые события,
тон напоминаний, кросс-джоб дедуп, дата/время в промпте, фиксация исключений, независимый
safety-скан, safe-fail контекста), **10 пунктов P2** (CI, README, env-ключи, секрет вебхука,
порог релевантности RAG, catch-all Telegram, задачи, показатели, покрытие, чистка мёртвого кода).

Открыто и осознанно отложено:
- **LEGAL-2** (локализация health data в ОАЭ) и **LEGAL-4** (экспорт копии данных) — до
  масштабирования/юридического ревью, решение владельца.
- **P1-13 + P2-1** (смысловой матчинг продуктов и гейт аллергенов) — ПЕРЕФОРМУЛИРОВАНО:
  выяснилось, что нужной информации нет в данных (аллергия и непереносимость в одном поле,
  ограничения режутся по запятой). Решения владельца зафиксированы в диагностике, реализация
  впереди.
- Остальные P1/P2 — см. мастер-список.

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
- `README.md` — обзор проекта, локальный запуск, тесты, деплой
- `docs/schema.sql` — консолидированная схема БД (база v1.3 + миграции 001–021)
- `docs/migrations/README.md` — реестр миграций, их статус на проде + verify-SQL
- `docs/progress.md` — журнал прогресса по сессиям (источник правды по истории)
- `docs/docs/diagnostic_report.md` — полная диагностика (код/БД/ТЗ/E2E/юридика):
  мастер-список находок, решения владельца, что уже устранено
- `docs/spec_reminders.md` — спецификация напоминаний и контроля ответа
- `docs/architecture_llm_orchestrator.md` — устройство LLM-оркестратора
- `docs/DEPLOY.md` — деплой на Render
- `docs/docs/technical_specification_V1.4.docx` — актуальная версия ТЗ (v1.2/v1.3 — история)
- `docs/archive/` — исторические сводки сессий за июнь (не поддерживаются, оставлены как архив)

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