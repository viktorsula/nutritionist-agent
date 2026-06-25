# GOTO — НАЧАЛО СЛЕДУЮЩЕЙ СЕССИИ

## ▶️ НАЧАТЬ ОТСЮДА (25 июня)

Сессия 24 июня закрыла разрывы памяти + анализы клиента + Telegram-webhook + APScheduler.
Сессия 25 июня: **запушила всё на `origin/stage6-utils`** (вчера 9 коммитов висели только
локально!), закоммитила фичу **аудита настроек №6**, добавила ТЗ v1.4 в git, синхронизировала доки.
Ветка **`stage6-utils`** — на remote, НЕ влита в main. **Бэкенд-набор зелёный: 93 passed, 0 failed**
(починены 5 стале-тестов: `/clients` 422 → +paid; analytics-директива; failover-трейсинг).

**✅ Миграции 001–009 ПРИМЕНЕНЫ** (002 RPC `match_*` и 009 rolling-summary проверены
интроспекцией БД 25 июня). Блокер миграций снят.

**⚠️ ОСТАЛОСЬ перед merge в main — ENV бэкенда для Telegram** (иначе бот просто выключен,
прод не ломается):
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_URL` (= `https://nutritionist-agent-gvxp.onrender.com/telegram/webhook`),
`TELEGRAM_WEBHOOK_SECRET`. + E2E-прогон + merge `stage6-utils → main`.

**Что проверить E2E после деплоя:**
1. Документ клиента (веб): загрузка PDF → векторизация (`client_documents`) + анализы в `lab_results`.
2. База знаний: «Настройки → База знаний» → загрузка труда → используется в ответах агента.
3. Клиент: вес из диалога → график (`measurements`); «холестерин 5.2» → `lab_results`; фото бланка.
4. Долгий диалог (>10 реплик) → сводка (`clients.conversation_summary`) подтягивается в контекст.
5. Telegram: текст/фото/голос/PDF через webhook (после set_webhook).

**Открытые задачи (не блокеры):** ~~аудит правок настроек с фронта (№6)~~ ✅ закрыто;
~~актуализация ТЗ v1.3 → v1.4~~ ✅ в git; ~~стале-тесты (`/clients` 422 и др.)~~ ✅ починены
(93 passed); маппинг client-indicator → каноничные ключи нутрициолога (v1.1).

URL: фронт `https://nutritionist-agent-1-ljzi.onrender.com`, бэкенд
`https://nutritionist-agent-gvxp.onrender.com`. Runbook: `docs/DEPLOY.md`.

---

**Обновлено:** 25 июня 2026 — `stage6-utils` запушена; аудит настроек №6 + ТЗ v1.4 в git;
миграции 001–009 применены. Осталось: ENV Telegram + E2E + merge в main.

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
