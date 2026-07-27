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
- React SPA (Vite + TypeScript) — веб-интерфейс; FastAPI — бэкенд
- Telegram Bot / python-telegram-bot (основной канал клиента)
- Groq llama-3.3-70b (диалог, бесплатно)
- Claude Sonnet (аналитика, ~$3/M токенов)
- Gemini 2.5 Flash (фото/vision; 1.5 снята Google 06.2026). Модели/резерв — в system_settings.llm_config, правятся нутрициологом в окне «Настройки → LLM-модели» (живой список моделей, «Проверить», резерв). Новый OpenAI-совместимый провайдер — конфигом через llm_config._providers (base_url+api_key_env), без кода
- OpenAI Whisper (голос → текст, v1.1)
- n8n cloud (автоматизация расписаний)
- LangFuse (мониторинг и трейсинг)

## Архитектура
Telegram / React SPA
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
├── api/                      ← FastAPI (точка входа бэкенда: api/main.py)
├── frontend/                 ← React SPA (кабинеты нутрициолога и клиента)
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
## Текущий статус (24 июля 2026)
> ⚠️ Этот раздел раньше был датирован 14 июня и сильно отставал от реальности (описывал
> Streamlit/старый граф, которых давно нет). **Источник правды по прогрессу — `docs/progress.md`**
> (журнал по сессиям, актуализируется каждой сессией), по диагностике —
> `docs/docs/diagnostic_report.md` (мастер-список находок + план устранения, ветка
> `claude/project-status-next-steps-zznj8o`). Здесь — только краткий снимок.

Стек фактически: React SPA (Vite/TS) + FastAPI (`api/`) на Render (2 сервиса — Docker бэкенд
`nutritionist-agent` + Static фронт `nutritionist-agent-1`), Telegram через webhook
(`tg_bot/`), LLM-оркестратор (Claude tool-calling, `agents/*/agent_orchestrator.py` /
`agent_adapter.py`) как основной путь для обеих ролей, граф LangGraph — fallback при сбое.
БД Supabase — 22 таблицы (не 14 — `docs/schema.sql` устарел с миграции 003, не актуализировался),
миграции 001–019 применены и проверены на живой БД.

**22–24 июля 2026 — полная диагностика + закрытие всех блокеров P0/LEGAL.** Мастер-список:
6 юридических + 5 P0 + 15 P1 + 21 P2 (+ P2-22 добавлен по ходу) + 1 новая фича (проактивный
аудит клиента). Устранено по одному PR за раз, все влиты в main:
- **PR-A** (#81) — алерты по еде: сломанный `food_forbidden`, теряющийся текст алерта.
- **PR-C** (#80/#82) — LLM-оркестратор клиента видит полный профиль (мед. данные/цель/ЗОЖ/
  анкету), просмотр анкеты в кабинете нутрициолога, редактирование анкеты клиентом с историей
  версий и LLM-саммари вместо построчного дампа в промпте.
- **PR-D** (#83) — `web_search` для клиента, ограниченный объективными фактами о еде (КБЖУ/
  рецепты), без domain-гейта (доверенные источники — предпочтение в промпте, не хардфильтр).
- **LEGAL-1** (#84) — блокирующее согласие на обработку данных перед анкетой онбординга (два
  пункта: здоровье, Telegram — трансграничную передачу убрали по решению владельца).
- **P0-4** (#85) — запрет тихой потери tool-calling при смене провайдера оркестратора
  (`TOOL_CAPABLE_PROVIDERS` — расширяемый список, не хардкод бренда).
- **LEGAL-3** (#86) — все FK на `clients(id)` переведены из `CASCADE` в `RESTRICT`:
  физическое удаление клиента с данными теперь невозможно на уровне БД.

Остаются из мастер-списка: LEGAL-2 (локализация в ОАЭ, осознанно отложена на пилот),
UX-перенос ConsentGate в конец анкеты (обсуждено, не реализовано), NEW-1 (проактивный аудит),
P1 (15 пунктов), P2 (22 пункта). Подробности — в `docs/docs/diagnostic_report.md` и
`docs/progress.md`.

## Следующий шаг
Дальше по мастер-списку — на выбор владельца: (1) перенос ConsentGate в последний шаг анкеты
(юридически корректно — обработка начинается при сохранении, а не при вводе в поля), (2)
NEW-1 (проактивный аудит клиента), (3) P1/P2 по приоритету. Тем же порядком: план →
подтверждение владельца → реализация → тесты → отдельная ветка от main → пуш.

## Важно перед продолжением
⚠️ Разделы ниже (зависимости/миграции) описывают историческое состояние Этапа 6 (июнь) —
актуальный список зависимостей в `requirements.txt`, актуальный список env-ключей проверен
диагностикой (`docs/docs/diagnostic_report.md`, находка «7 ключей не в `.env.example`»).

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
- `docs/schema.sql` — схема БД, ⚠️ устарела с миграции 003 (19 июня) — не отражает 6 таблиц
  (measurements/lab_results/client_reports/reminders/reminder_occurrences/client_metrics)
- `docs/progress.md` — журнал прогресса (источник правды по истории сессий)
- `docs/docs/diagnostic_report.md` — полная диагностика проекта (код/БД/ТЗ/E2E/юридика),
  мастер-список находок с приоритизацией + план устранения (ветка
  `claude/project-status-next-steps-zznj8o`)
- `docs/docs/technical_specification.docx` (v1.2) / `_V1.3.docx` / `_V1.4.docx` — эволюция ТЗ,
  v1.4 актуальнее всех — отражает факт реализации (React+FastAPI, APScheduler, LLM-оркестратор)
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