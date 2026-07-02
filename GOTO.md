# GOTO — НАЧАЛО СЛЕДУЮЩЕЙ СЕССИИ

## ▶️ НАЧАТЬ ОТСЮДА (3 июля) — E2E редизайна кабинета + продолжение Ф3

**Где мы (всё влито в main, PR #49–#57):** архитектура «один движок, две роли» замкнута — `agents/core/agent_engine.py::run_agent`
+ клиентский и нутрициологовский адаптеры за фиче-флагами, граф — fallback. **ГОТОВЫ и на проде:** Ф1.5 мультимодальность
(фото через оркестратор, `vision_strategy`), NutritionistAdapter (Часть B), графики питания (C1/C2), редизайн кабинета
нутрициолога (PR A модель доступа + PR B фронт ClientCard). 340 passed (бэк) + tsc/19 vitest (фронт).

**⏳ E2E за владельцем (после деплоя #57):**
- **Кабинет нутрициолога (редизайн):** события наверху (само событие/дата слева/≤30vh); карточки «Задачи+Заметки»,
  «Доступ клиента» (Telegram+пароль); **редактор статусов** (смени статус/оплату/`paid_until`); 6 графиков питания 2-в-ряд;
  «Рекомендации нутрициолога», «Дополнительные сведения».
- **⚠️ Модель доступа ЖИВАЯ (PR #56):** авто-блок по `paid_until` — у активных клиентов дата должна быть в будущем
  (пустая — не блокирует; истёкшая — закрывает вход). `paused` теперь блокирует и веб-кабинет. `completed`=«Поддержка».
- **Оркестраторы:** клиент (Екатерина `d3c09f60-f4c6-4b0e-8271-85b7389a4d90`) — фото/дневник/жалоба→алерт; нутрициолог —
  включить `NUTRITIONIST_ORCHESTRATOR_ENABLED=true`, проверить аналитику/команды-с-подтверждением. Откат — снять флаг.

**▶️ ДАЛЬШЕ (согласовано):**
1. Мелочь: история планов **выпадающим списком** (внутри `PlanEditor`).
2. **Задачи → ежедневные ТЁПЛЫЕ Telegram-напоминания** — `recurrence` (once/daily/weekly) + джоб в `api/scheduler.py`,
   текст формулирует ассистент-оркестратор. Клиенту в кабинете задачи НЕ показываем (это инструмент нутрициолога).
3. **Ф3 (продолжение):** мониторить `GET /nutritionist/coverage` → когда `graph_fallback==0` за период и доля
   `orchestrator`→100% → снять белые списки → **чистка графа** (домейн/персист/безопасность переиспользуются, не удаляются).
   **Async** — под реальную нагрузку, отдельно (при 1–20 клиентах преждевременно; per-id `Lock` даёт корректность).
4. Опц.: «Каталог показателей анализов» → «Референсные значения анализов» (лейбл лаб-фичи).

**⚠️ Блокер вне кода:** OpenAI 429 (квота) — RAG (советы клиента, vector-аналитика нутрициолога) молчит, пока не пополнить.

**ENV на Render + E2E-чеклисты** — в локальном `РАБОЧИЙ.md`. Детали/решения — `docs/progress.md`, память
[[project_nutritionist_cabinet_redesign]], [[project_phase3_coverage]], [[project_orchestrator_multimodal]], [[project_nutritionist_adapter]].

---

<details><summary>Архив: НАЧАТЬ ОТСЮДА (27 июня)</summary>

## ▶️ (архив) 27 июня

Сессия 27 июня: **переделка приёма входящих клиента — ШАГ 1** (под-шаги 0–1.6). Исправлены две
структурные ошибки: «модальность вперёд темы» и отсутствие понятия «ход». Таксономия 8→3
(`intake`/`profile`/`advice` + под-типы хранения), граф пересобран линейно
(ingest → determine → load_context-по-веткам → dispatch-по-сегментам → format_response → save),
`classify_image` поднят в нормализацию (food/lab_document/fridge/other), исход **`clarify`**
(всегда уточняем при сомнении, данные наугад не пишем), **вода** (`water_logged`), **meal_type**,
фото холодильника (**`analyze_fridge`**, UC-3), флаг **`ack_only`** (нет лишнего LLM на ack).
**PR #18 ВЛИТ в `main`** (merge `0ea30a9`, код `87e8a46`), **задеплоен на Render (Live)**.
Бэкенд-набор **152 passed**. Детали — [[project_client_intake_rework]] (+саммари логики решений).

**⏳ СЕЙЧАС: E2E приёма входящих на проде** — Виктор гоняет через Telegram (от лица тестового клиента).
Чеклист 10 кейсов — в локальном `РАБОЧИЙ.md` (текст-еда→«Записал»; вес→measurements; вода→water_logged;
плохо→bad_wellbeing+уведомление; анализы→lab_results; «какой вес?»→ответ; «что приготовить?»→совет;
бессмыслица→clarify; «отчёт+вопрос»→answer+квитанция; фото/голос).

**▶️ ДАЛЬШЕ:** по итогам E2E — мелкие правки; затем **Фаза 2** (turn-буфер debounce 6–10с +
склейка `media_group_id`/альбомов) и **Фаза 3** (цель воды в плане + алерты воды/еды + end-of-day
напоминания + окна приёмов пищи + оживить `no_response`).

**⏳ ОТКРЫТО (Виктор думает):**
- **Промпт-архитектура** — провели полный анализ (17 промптов). Цель: вынести все инлайн-промпты
  в файлы (`prompts/system/` — разработчик; `prompts/client|nutritionist/` — нутрициолог через веб).
  Детали — [[project_prompt_architecture]] и локальный `РАБОЧИЙ.md`. Спорный: `management_system`.
- **`no_response` алерт МЁРТВ** — `_check_no_response` не на расписании; добавить джоб в `api/scheduler.py`.
- **Нет guardrail релевантности ответа.** task_type рассинхрон (summary/planning шлют `dialog`).
- **Веб «не открывается» у Виктора** — сервер ИСПРАВЕН (всё 200, бандл корректный); причина клиентская
  (кэш/браузер) — нужен вывод DevTools Console.

✅ **СБРОС ПАРОЛЯ РАБОТАЕТ (23 июня, PR #5–#9)** — по КОДУ из письма (не по ссылке: её прокликивает
сканер Gmail). Нужны в Supabase: Custom SMTP (Resend) + шаблон Reset Password с `{{ .Token }}`.
E2E проверен на проде. Шаблоны — `docs/email_templates/`. Детали — `docs/DEPLOY.md` (4b/4c), [[project_deploy_state]].

**✅ Миграции 001–009 ПРИМЕНЕНЫ** (002 RPC `match_*` и 009 rolling-summary проверены
интроспекцией БД 25 июня).

**✅ PR #15 ВЛИТ** (двусторонний Telegram-канал нутрициолога). **✅ PR #18 ВЛИТ** (приём входящих Шаг 1).
На проде живой Telegram-канал клиента и нутрициолога.

**⚙️ ENV Telegram (Render, бэкенд `nutritionist-agent-gvxp`):**
Прописаны: `TELEGRAM_BOT_TOKEN`, `NUTRITIONIST_TELEGRAM_ID`, `TELEGRAM_WEBHOOK_URL`.
Осталось вставить: **`TELEGRAM_WEBHOOK_SECRET`** (сгенерён, лежит в scratchpad).
`NUTRITIONIST_TELEGRAM_ID` теперь РАБОТАЕТ — двусторонний канал нутрициолога + пуш алертов
(см. [[project_nutritionist_telegram_channel]]). Вебхук ставится автоматически при старте.

**Что проверить E2E после деплоя:**
1. Документ клиента (веб): загрузка PDF → векторизация (`client_documents`) + анализы в `lab_results`.
2. База знаний: «Настройки → База знаний» → загрузка труда → используется в ответах агента.
3. Клиент: вес из диалога → график (`measurements`); «холестерин 5.2» → `lab_results`; фото бланка.
4. Долгий диалог (>10 реплик) → сводка (`clients.conversation_summary`) подтягивается в контекст.
5. Telegram-КЛИЕНТ: текст/фото/голос/PDF (нужен `clients.telegram_id` = ID из `/start`).
6. Telegram-НУТРИЦИОЛОГ: `/start` → приветствие; аналитический вопрос/команда → ответ как в вебе;
   критичный алерт по клиенту (high/critical/bad_wellbeing) приходит в личку.

**Открытые задачи (не блокеры):** ~~№6 аудит настроек~~ ✅; ~~ТЗ v1.3 → v1.4~~ ✅; ~~стале-тесты~~ ✅;
маппинг client-indicator → каноничные ключи нутрициолога (v1.1). Ветки `stage6-utils` и
`docs-email-templates` уже в main — можно удалить.

URL: фронт `https://nutritionist-agent-1-ljzi.onrender.com`, бэкенд
`https://nutritionist-agent-gvxp.onrender.com`. Runbook: `docs/DEPLOY.md`.

---

**Обновлено:** 25 июня 2026 (вечер) — PR #14 влит в main; PR #15 (Telegram-канал нутрициолога)
открыт; 100 passed; ENV Telegram частично прописаны (осталось `TELEGRAM_WEBHOOK_SECRET`).
Осталось: merge PR #15 + E2E Telegram.

## 🔜 СЛЕДУЮЩЕЕ (22 июня)
- **Кабинет нутрициолога (React)** — Фаза 3 собрана: 3 панели (инструменты/центр/чат с
  ресайзом и скрытием), создание клиента со статусами (+`paid_until`), фильтры реестра,
  индикатор истечения тарифа, агент наполняет центр (директива вида), аналитика-RAG
  (клиент+vector), отчёты (генерация→правка→PDF/TXT), полные «Настройки» (каталог/пороги/
  источники/llm/промпты). Подробности — `docs/progress.md` (сессия 22 июня).
- **Миграции применены:** 001–008 (007 paid_until, 008 client_reports).
- **Запуск локально:** `uvicorn api.main:app --port 8000` (env: `set -a; . ./.env; set +a`
  + `CORS_ORIGINS`) и `cd frontend && npm run dev` (:5173, публичный).
- **PR #1** `stage6-utils`→`main` открыт. Пост-PR фиксы: pgvector-литерал (формат сервис↔БД),
  Dockerfile→uvicorn, тема-адаптивный `analytics_system.md`.
- **Блокеры качества (среда):** OpenAI ключ 429 (нет эмбеддингов → vector пуст, фикс не проверен);
  Claude без кредитов (синтез на Groq). Пополнить → проверить векторный поиск и сильную аналитику.
- **Осталось:** web-шаг аналитики + группа клиентов (ждут Claude); аудит правок настроек с фронта;
  PDF одним кликом (jsPDF+шрифт); финальный smoke-тест и merge PR.
- **Новые формы отчётов (до 5)** — добавлять как `report_type` в `agents/nutritionist/reports.py`
  + шаблон `prompts/nutritionist/reports/<...>.md`.

## 🗄️ СТАРОЕ СЛЕДУЮЩЕЕ (20 июня)
- **Кабинет клиента (React)** работает: вход/роль/анкета/график веса/чат/загрузка анализов.
  Серверы локально: `uvicorn api.main:app --port 8000` (env: `set -a; . ./.env; set +a` +
  `CORS_ORIGINS` с URL фронта; порт 8000 — public) и `cd frontend && npm run dev` (:5173).
- **Миграции 001–005 ПРИМЕНЕНЫ** (005 — storage-бакет `client-documents`).
  ⏳ **006_tracked_lab_indicators.sql — ПРИМЕНИТЬ** (per-client показатели анализов; без неё
  select `tracked_lab_indicators` на фронте упадёт).
- **Claude без кредитов** (пополнять не стали) → всё работает на Groq/Gemini через
  взаиморезервирование (`utils/llm.py`). Когда пополнят — автоматически вернётся на Claude.
- **Per-client показатели анализов — РЕАЛИЗОВАНО** (JSONB в client_profiles, редактор
  нутрициолога «Показатели анализов», график рисует выбранное с нормой). Ввод значений в
  `lab_results` — форма в той же вкладке (LabValuesForm). Парсер PDF → lab_results — позже.
- **Панель алертов — РЕАЛИЗОВАНО** (вкладка «Алерты», `AlertsPanel`: client_events с severity
  под RLS, фильтры окно/severity). weight_increase теперь персистится в diary_agent.
- **Реестр + карточка клиента — РЕАЛИЗОВАНО** (вкладка «Реестр»: список → `ClientCard` с
  профилем/планами/задачами/графиками/событиями/заметками; всё под RLS).
- **Чат нутрициолога с агентом — РЕАЛИЗОВАНО** (вкладка «Ассистент-агент», `NutritionistChat`
  → `/nutritionist/query`; analytics + management с подтверждением «да»). Исправлен баг
  task_type='analysis' → 'analytics' в analytics_agent/management_agent.
- **Редакторы планов/задач/ЗОЖ — РЕАЛИЗОВАНЫ** (карточка клиента: `TaskEditor`, `PlanEditor`,
  `WellnessEditor`; всё под RLS; план — деактивация старого до вставки нового).
- **Дальше по Фазе 3:** React-вкладки «Аналитика» (дашборды) и «Настройки»
  (пороги/источники/промпты — перенести с Streamlit `web/nutritionist.py`). Затем
  smoke-тест и PR `stage6-utils` → `main`.

---

## 🐞 ИЗВЕСТНЫЕ TODO
- **Telegram-резолв роли сломан:** `agents/router.py` → `get_user_info()` вызывает
  `queries.get_user()` и `queries.get_user_by_telegram_id()`, которых НЕТ в `database/queries.py`.
  Значит `route_message()` для Telegram всегда вернёт «user_not_found». Веб это обходит
  (резолв в `database/auth.py`). Починить отдельно: добавить `get_user_by_telegram_id`
  и `get_user_by_auth_id` в `queries.py` (не смешивать с работой по фронту).

## 🎯 ЦЕЛЬ СЛЕДУЮЩЕЙ СЕССИИ

**Дорожная карта ТЗ v1.3 (Этапы 1–9) — ЗАВЕРШЕНА.** Дальше — подготовка к продакшену:
1. Миграции в Supabase (001 observer, 002 vector search)
2. Ключи в Render: OPENAI / GOOGLE / TELEGRAM_BOT_TOKEN / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
   (+ включить web search в Claude Console — Settings → Privacy; TAVILY больше не нужен)
3. Живой smoke-тест (клиент: текст/фото/голос; нутрициолог: аналитика/управление)
4. PR `stage6-utils` → `main` (автодеплой Render)

### ✅ Этап 9 (готово): трейсинг LangFuse
- `monitoring/langfuse.py` — `trace_llm_call` / `is_enabled` / `flush`; graceful no-op без SDK/ключей
- `utils/llm.py` — `call_llm` трейсит каждый вызов (тайминг + успех/ошибка); единая точка для всех агентов
- тесты `monitoring/test_monitoring.py` 7/7 ✅

### ✅ Этап 8 (готово): веб-интерфейс нутрициолога
- `web/nutritionist.py` — `render_registry` / `render_analytics` / `render_settings`
- `queries.get_client_registry()`; тесты `web/test_nutritionist_views.py` 10/10 ✅

### ✅ Сделано в Части B (ветка нутрициолога):
- `agents/nutritionist/state.py` — NutritionistState + helpers (thread, pending_action)
- `orchestrator.py` — реальный LangGraph граф (заменил заглушку), общий для Telegram и web:
  parse_request → [analytics|management|help] → format_response → save_to_db
- `analytics_agent.py` — read-only анализ клиента/базы (Claude)
- `management_agent.py` — запись ТОЛЬКО через двухшаговое подтверждение (pending_action
  в conversations.metadata_json); create_task / create_nutrition_plan / update_client_status /
  add_trusted_source; created_by='nutritionist' + write_audit_log
- `prompts/nutritionist/management_system.md`; тесты test_nutritionist.py — 13/13 ✅

---

## 📍 ГДЕ МЫ СЕЙЧАС

Вся работа Этапа 6 — на ветке **`stage6-utils`** (НЕ влита в main, push мог быть сделан вручную).

### ✅ Сделано (Часть A, ветка клиента — ПОЛНОСТЬЮ):
- **requirements.txt** — +openai; модернизирован LangGraph (langgraph>=1.0, langchain-core>=0.3)
- **utils/** — knowledge.py (ada-002 + pgvector-поиск), vision.py (фото еды), voice.py (Whisper), web_access.py (серверный инструмент Claude web_search + allowed_domains из trusted_sources)
- **migration 002** — RPC match_knowledge_base / match_client_documents
- **agents/client/** — vision_agent, diary_agent, nutrition_agent, общий food_analysis.py
- **orchestrator.py** — роутинг: ingest → load_context → route → [vision|diary|nutrition|dialog] → format → save
- **prompts/client/** — vision_system.md, diary_system.md, nutrition_system.md
- **Шаг 3 — `tg_bot/handlers.py`** — фото и голос подключены к графу:
  - фото → `image_bytes`+`mime_type`, caption→message, `message_type='photo'` → vision
  - голос → `audio_bytes`+`audio_name`, `message_type='voice'`, транскрипция в узле ingest
  - DRY: `_ensure_registered()` + `_dispatch_to_router()` для text/photo/voice
- **Шаг 4 — тесты:** tg_bot/test_bot.py 10/10 ✅, agents/test_agents.py 7/7 ✅
- **Фиксы:** пакет `telegram/` → `tg_bot/` (коллизия с библиотекой python-telegram-bot);
  убран мёртвый импорт `get_user_by_id`; tg_bot/test_bot.py на `IsolatedAsyncioTestCase`
- **Ранее:** сохранение диалога (save_conversation), удалён check_alerts_node

---

## ⚠️ ПЕРЕД РЕАЛЬНЫМ ЗАПУСКОМ (действия Виктора)

1. `pip install -r requirements.txt` (новое: openai; tavily удалён)
2. Применить миграции в Supabase → SQL Editor:
   - `docs/migrations/001_add_observer_role.sql` ⏳
   - `docs/migrations/002_add_vector_search.sql` ⏳
3. Ключи окружения: `OPENAI_API_KEY`, `GOOGLE_API_KEY` (веб-поиск — через Claude web search, ключ не нужен; включить в Console)
4. (Позже) конфликт `streamlit 1.32.0 ↔ protobuf 5.29.6` — перед запуском веба

---

## 🔭 ДАЛЬШЕ (после Части A)

**Часть B — ветка нутрициолога** (роль агента ШИРЕ советника — аналитик/контролёр/репортёр):
- `analytics_agent.py` — произвольные запросы по базе, мониторинг следования плану,
  выявление паттернов/связей (Claude), отчёты, эскалация проблем
- `management_agent.py` — клиенты/планы/задачи/реестр, корректировки по команде врача,
  пополнение trusted_sources по просьбе нутрициолога

---

## 📝 КЛЮЧЕВЫЕ ФАЙЛЫ ДЛЯ СПРАВКИ

- `docs/progress.md` — полный журнал
- `agents/client/orchestrator.py` — граф и роутинг
- `agents/client/food_analysis.py` — общий анализ против рациона
- `docs/migrations/002_add_vector_search.sql` — RPC pgvector
- ТЗ: `docs/docs/technical_specification.docx` (v1.2), `..._V1.3.docx` (читаются как UTF-8 текст)

</details>
