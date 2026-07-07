# Описание модели (факт): как устроен ассистент нутрициолога

**Дата среза:** 7 июля 2026 · **Статус:** в разработке, прод на Render (React + FastAPI + Supabase).

Документ описывает систему **как она реализована сейчас**, а не план. Это «as-built» —
опорная карта для разработки и онбординга. Хронология изменений ТЗ — в `docs/docs/` (v1.2→v1.3→v1.4);
данный документ фиксирует состояние ПОСЛЕ v1.4 (когда произошёл поворот на LLM-оркестратор,
появились напоминания, редизайн кабинета и еженедельный отчёт — в ТЗ они не отражены).

---

## 1. Назначение и роли

ИИ-ассистент нутрициолога: снимает рутину (сбор данных, мониторинг, аналитика, коммуникация),
оставляя нутрициологу профессиональные решения. Клиент получает ассистента 24/7.

- **Нутрициолог** — владелец системы (в v1.0 один). Полный доступ. **Единственный источник
  назначений** (планы, задачи, пороги, напоминания). Работает через веб-кабинет.
- **Клиент** — доступ только к своим данным. Исполнитель и информатор. Основной канал — Telegram;
  также веб-кабинет (анкета, графики, чат, загрузка документов).
- **Observer** — зарезервировано для v2.0 (клиники). В v1.0 в интерфейсах отключено.

Философия: **нутрициолог = источник назначений; агент = аналитик/советник; клиент = исполнитель.**
Изоляция данных — на уровне БД (Supabase RLS): клиент физически не видит чужие данные.

---

## 2. Архитектура (поток обработки)

```
Telegram (webhook) / React SPA
        ↓
    agents/router.py          — резолвит роль/пользователя (web: JWT; telegram: telegram_id)
        ↓
  business_rules (детерминир.) — доступ, оплата, расписание, медицинские проверки ДО LLM
        ↓
  ┌─────────────────────────── развилка по фиче-флагу ───────────────────────────┐
  │  LLM-ОРКЕСТРАТОР (основной путь)         │   LangGraph-граф (fallback)         │
  │  agents/core/agent_engine.run_agent      │   client/orchestrator + nutritionist│
  │  «один движок, две роли» + tool-calling  │   (остаётся страховкой)             │
  └──────────────────────────────────────────────────────────────────────────────┘
        ↓
  utils/llm.py  → Groq / Claude / Gemini / OpenAI-совместимые (по task_type из llm_config)
        ↓
  Supabase (сохранение: conversations, client_events, measurements, …) → ответ
```

**Ключевое архитектурное решение (пост-v1.4):** уход от жёсткого графа детерминированных рёбер
к **LLM-оркестратору с tool-calling**. Причина: граф давал цепочку последовательных LLM-вызовов
(determine→extract→present→summary), где каждое звено множит ошибку и рассинхронизирует шаги.
Оркестратор сам понимает тему, выбирает инструменты и объём контекста. Миграция — strangler-паттерном
за фиче-флагом; граф оставлен как fallback.

---

## 3. Ядро `run_agent` — «один движок, две роли»

`agents/core/agent_engine.py::run_agent` — role-agnostic цикл tool-calling (модель зовёт инструменты →
`tool_result` → продолжает, пока не сформирует ответ). Поверх ядра — тонкие адаптеры на каждую роль.

**Клиент** (`agents/client/agent_orchestrator.py`), инструменты:
`log_meal` · `log_water` · `log_weight` · `log_wellbeing` · `log_labs` · `log_measurement` · `log_sleep`
(запись через `intake_store.persist_record` + медицинские алерты), `get_client_data(scope)`,
`search_knowledge(query)` (pgvector). Тёплый ответ пишет сама модель.

**Нутрициолог** (`agents/nutritionist/agent_adapter.py`), инструменты:
`find_client` · `run_analytics` (обёртка над `analytics_node` — RAG + графики) · `get_client_data` ·
`search_knowledge` + 4 write-staging инструмента (план/задача/статус/заметка).

**Подтверждение записи нутрициолога — ДЕТЕРМИНИРОВАНО, вне модели.** Write-инструменты не пишут в БД —
лишь готовят `pending_action` (→ `conversations.metadata_json`) и просят подтверждения. Детект «да/нет»
и исполнение (`_execute_action` + audit) — вне LLM. Модель не может записать в карту сама.

**Включение (фиче-флаги + белые списки):**
- Клиент: `CLIENT_ORCHESTRATOR_ENABLED` + `CLIENT_ORCHESTRATOR_CLIENT_IDS`.
- Нутрициолог: `NUTRITIONIST_ORCHESTRATOR_ENABLED` + `NUTRITIONIST_ORCHESTRATOR_IDS`.
- На проде включён клиентский оркестратор для обкатки (Екатерина). При ошибке/недоступности LLM —
  молчаливый откат на граф.

**Наблюдаемость покрытия:** `agents/core/coverage.py` помечает каждый ход одним путём
(`orchestrator` / `graph_flag_off` / `graph_fallback`); `GET /nutritionist/coverage` + лог `COVERAGE`.
Критерии чистки графа (решение проекта): 100% ходов на оркестраторе, ноль `graph_fallback`, снят белый список.

---

## 4. Детерминированный слой безопасности (`business_rules/`)

Критические ситуации обрабатываются кодом ДО/помимо LLM — модель их не «решает».

- `access_rules.py` — `check_access` / `check_web_access`; `_payment_active` (статус + не истёкший
  `paid_until`). Модель доступа — **2 оси:** `client_status` (жизненный цикл, `paused` = единый
  рубильник, блокирует и веб) + `payment_status`/`paid_until` (авто-блок по истечении даты).
  `access_status` из гейтов **убран** (дублировал `paused`).
- `medical_rules.py` — 5 типов алертов + маршрутизация.
- `notification_rules.py` — timezone-aware расписание.

**Алерты (факт):** 5 медицинских (`weight_increase`, `food_incompatible`, `food_forbidden`,
`no_response`, `bad_wellbeing`) + `reminder_unanswered` (low, панель) + `meal_not_reported`
(medium, пуш — пропуск приёма пищи к дедлайну 12/17/22). Пуш нутрициологу в Telegram = high/critical
+ bad_wellbeing (планировщик, независимо от канала). Пороги — глобально в `system_settings`,
индивидуально в `client_profiles`.

---

## 5. Данные и память (Supabase: PostgreSQL + pgvector + Storage)

**Ядро v1.3 (`docs/schema.sql`) — 14 таблиц + `client_registry_view` + триггеры версионирования планов:**
`users`, `clients`, `client_profiles`, `wellness_plans`, `conversations`, `client_events`,
`nutrition_plans` (+`supplements_json`, версионирование), `tasks`, `notification_schedule`,
`audit_logs`, `system_settings`, `document_metadata`, `knowledge_base` (pgvector),
`client_documents` (pgvector).

**Добавлены миграциями (003/008/013/014/015):** `measurements` (вес/объёмы/грудь — временной ряд),
`lab_results` (числовые анализы), `client_reports` (отчёты), `reminders` + `reminder_occurrences`
(напоминания + срабатывания), `client_metrics` (произвольные/сон-показатели).

**Виды памяти:**
- Диалоговая: `conversations`. Краткосрочно — последние ~10 реплик; долгосрочно — **rolling-summary**
  (`clients.conversation_summary`, обновляется в фоне ~раз в 10 сообщений).
- Событийная: `client_events` (severity) — калории/вода/вес/самочувствие/сработавшие алерты.
- Измерения/анализы: `measurements`, `lab_results` (source: nutritionist | client | client_pdf),
  `client_metrics`. Per-client показатели анализов — `client_profiles.tracked_lab_indicators`;
  контролируемые показатели — `client_profiles.controlled_metrics`.
- Векторная (RAG): `knowledge_base` (труды нутрициолога) + `client_documents` (документы клиента),
  эмбеддинги OpenAI `ada-002` (1536), поиск через RPC `match_*` (cosine). Эмбеддинг в RPC/INSERT —
  строкой `'[...]'`, не list.
- Конфиг/аудит: `system_settings` (пороги, `trusted_sources`, `llm_config`, промпты, `weekly_report`,
  `reminder_cadence`), `audit_logs`.

**Реестр миграций** — `docs/migrations/README.md` (единственный источник правды по применённому на проде
+ verify-SQL). На 7 июля 2026 применены **001–016**.

---

## 6. Приём данных клиента

- **Текст / голос (Whisper) / фото / PDF** — единый вход через оркестратор.
- **Протокол `IntakeRecord`** — граница обратимости: кто бы ни распознавал вход (Claude в схеме
  `direct` / Gemini в схеме `gemini_tool`), на выходе `IntakeRecord` → **`validate`-гейт** →
  `persist_record`. Нормализация — один раз в `persist_record`.
- **Мультимодальность:** стратегия зрения из `llm_config.vision_strategy` per-kind
  (`direct` по умолчанию — фото напрямую в Claude-оркестратор; `lab_document → gemini_tool`).
- **Документы (PDF):** Storage + `document_metadata` + векторизация в `client_documents` +
  извлечение показателей в `lab_results` (`POST /documents/{id}/ingest`).

---

## 7. Напоминания, контроль и отчёты

**Напоминания клиенту** (`reminders` + `reminder_occurrences`, планировщик):
- Модель: отдельные таблицы (не расширение `tasks`). **Пакетная отправка** — все напоминания на одно
  локальное время идут одним сообщением. Регулярность: daily / weekly(+день) / once(+дата).
- **Контур ответа:** напоминание может ЖДАТЬ ответа заданного типа (`expected_response`). Планировщик
  детектит ответ → закрывает; молчание → догон (кадэнс из профиля/`system_settings.reminder_cadence`) →
  «сдались» → `reminder_unanswered`.
- **Контролируемые показатели** — единый каталог `controlled_metrics`; подаётся в промпт оркестратора →
  произвольные показатели детектятся по ключу.
- **Дедлайны еды** (12/17/22 локально): пропуск → `meal_not_reported` (medium + пуш); one-shot в дне
  (вчерашняя еда не тащится в сегодняшнее сообщение, внутридневного пинга по еде нет).
- **Управление — ТОЛЬКО у нутрициолога** (блок кабинета «Настройка уведомлений»). Клиент напоминания
  не настраивает (решение проекта, развилка B).
- Текст сообщения собирает ассистент (`compose_reminder_message`, `task_type='reminder'`, тёплый тон)
  с детерминированным fallback-шаблоном.

**Еженедельный автоотчёт нутрициологу** (`run_weekly_report`, ТЗ 6.2.1): раз в неделю (Пн 09:00 в
timezone нутрициолога по умолчанию, конфиг `system_settings.weekly_report`) — компактная сводка по
активным клиентам одним сообщением в Telegram. Дедуп по ISO-неделе. Детерминированный текст (не клиентский).

---

## 8. LLM-слой (`utils/llm.py`)

- **Мультипровайдер + failover** по `task_type`: Groq (диалог), Claude Sonnet (оркестраторы/аналитика),
  Gemini 2.5 Flash (vision; 1.5 снята Google), OpenAI (эмбеддинги ada-002 + Whisper). Новый
  OpenAI-совместимый провайдер добавляется конфигом `llm_config._providers` (base_url + api_key_env), без кода.
- `task_type` (факт): `dialog`, `orchestrator`, `nutritionist_orchestrator`, `reminder`, `vision`,
  `embedding`, `whisper` (+ аналитика на Claude).
- **Централизация из кабинета** (окно «LLM-модели»): основная модель + резерв (fallbacks) + стратегия
  зрения — из БД `llm_config` (приоритет) → код-дефолт. Модели/пороги/промпты/`trusted_sources` меняются
  без кода. Смена снятой провайдером модели = правка в «Настройках».
- **Взаимозамена:** при сбое модели — автопереключение на резерв; иначе честное «подождите». Для
  клиентского оркестратора резерв = откат на граф.
- **Веб-поиск:** серверный инструмент Claude `web_search` (allowed_domains из `trusted_sources`),
  вместо Tavily.

**Промпты:** файлы `prompts/**/*.md` (fallback) → БД (`system_settings`, приоритет) → веб-редактор
(2 вкладки: коммуникационные/системные, обе редактируемы). Модель — только через `task_type`, промпт —
только через `load_prompt` (не хардкодить).

---

## 9. Каналы, интерфейсы, планировщик

- **Telegram** (python-telegram-bot) — **webhook внутри FastAPI** (`POST /telegram/webhook`, защищён
  секретом). Текст/фото/голос/PDF. Самопривязка клиента по deep-link (`t.me/<bot>?start=<token>`).
  Пакет `tg_bot/` (не `telegram/` — коллизия с библиотекой).
- **Веб-кабинет** — React SPA (Vite/TS, react-query, i18n ru/en, Tailwind), общается с FastAPI (агент)
  и напрямую с Supabase под RLS (CRUD/Auth/Storage). Кабинет клиента (анкета, графики веса/анализов/
  питания, чат, документы) и нутрициолога (реестр + карточка «Профиль клиента», планы/ЗОЖ/рекомендации,
  напоминания, аналитика-RAG, отчёты, настройки, база знаний).
- **Планировщик** — встроенный APScheduler (`api/scheduler.py`, тик 60с, вместо n8n; n8n = опция v2).
  Джобы: `run_due_notifications` (morning/evening), `run_reminders`, `run_reminder_followups`,
  `run_no_response_check`, `run_nutritionist_alerts`, `run_weekly_report`. Инертен без бота; ENV
  `NOTIFICATIONS_ENABLED`.

---

## 10. Безопасность и мониторинг

- Авторизация — Supabase Auth (JWT). Бэкенд резолвит роль/клиента из БД, не из тела запроса.
- **RLS** — клиент физически не получает чужие данные; векторный поиск по `client_documents` изолирован.
- Секреты — только окружение (Codespaces/Render), `os.environ.get`, **запрет `load_dotenv()`** и хардкода.
- Полный аудит изменений — `audit_logs` (запись назначений идёт через эндпоинты с аудитом, не прямым
  Supabase-update).
- Telegram webhook — секрет `X-Telegram-Bot-Api-Secret-Token`.
- **Мониторинг — LangFuse** (`monitoring/langfuse.py`, подключён через `_trace()` в `call_llm`;
  graceful no-op без ключей/пакета).

---

## 11. Граница факта: чем отличается от ТЗ v1.4 и что отложено

**Реализовано иначе, чем в ТЗ (сознательно):**
- Оркестрация — LLM-оркестратор `run_agent` вместо жёсткого графа (граф = fallback).
- Задачи клиента → напоминания под нутрициологом (`TaskEditor` удалён); настройка уведомлений — только
  у нутрициолога.
- `payment_rules.py` — консолидирован в `access_rules._payment_active`.
- Модель доступа — 2 оси (`access_status` убран).

**Отложено (v1.1):** языки ar/ur (сейчас ru/en); фото холодильника → рецепты (сейчас только «совет»);
OCR PDF-бланков → lab_results; полный маппинг свободного текста клиента → каноничные ключи показателей.

**Архитектурный долг:** оркестратор за белым списком (не 100% клиентов); Ф3 (async + чистка графа) —
гейтится критериями покрытия; графики `client_metrics` (сон/произвольные) — бэкенд есть, фронта нет;
`datetime.utcnow()` устарел в Python 3.12 (тех-долг в планировщике).

---

*Опорные документы: `docs/schema.sql`, `docs/migrations/README.md`, `docs/progress.md`,
`docs/architecture_llm_orchestrator.md`, `docs/spec_reminders.md`. История ТЗ: `docs/docs/` (v1.2–v1.4).*
