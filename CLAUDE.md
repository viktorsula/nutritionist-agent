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
- Gemini 1.5 Flash (фото/vision, бесплатно)
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
## Текущий статус (9 июня 2026)
- [x] Репозиторий и деплой на Render
- [x] База данных Supabase v1.3 — ПОЛНОСТЬЮ ГОТОВА (14 таблиц + VIEW + триггеры)
- [x] schema.sql актуализирован (v1.3)
- [x] Блок 5: document_metadata + pgvector + knowledge_base + client_documents
- [x] **database/client.py** — подключение к Supabase готово
- [x] **database/models.py** — 14 моделей готовы
- [x] **database/queries.py** — 42 функции реализованы (для business_rules, agents, n8n)
- [x] **business_rules/** — ГОТОВО ✅
  - [x] access_rules.py — проверка доступа (анкета, оплата, режимы)
  - [x] medical_rules.py — 5 типов алертов + маршрутизация
  - [x] notification_rules.py — проверка расписания (timezone-aware)
- [ ] utils/ (llm.py, vision.py, voice.py, helpers.py) ← **СЛЕДУЮЩИЙ ШАГ**
- [ ] agents/ (router.py + оркестраторы + агенты)
- [ ] telegram/bot.py
- [ ] monitoring/langfuse.py

## Следующий шаг
**Этап 4:** Создание utils/ — вспомогательные модули (llm.py, vision.py, voice.py, helpers.py).

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