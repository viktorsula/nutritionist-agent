# GOTO — НАЧАЛО СЛЕДУЮЩЕЙ СЕССИИ

**Обновлено:** 18 июня 2026, после Этапа 6 Часть B (ветка нутрициолога завершена)

---

## 🎯 ЦЕЛЬ СЛЕДУЮЩЕЙ СЕССИИ

**Этап 8 — Шаг 2: таб «Настройки»** в `web/nutritionist.py` — пороги алертов (system_settings),
trusted_sources, редактор промптов (list_available_prompts/load_prompt/save_prompt), LLM-модели.

### ✅ Этап 8 Шаг 1 (готово): Реестр + Аналитика
- `web/nutritionist.py` — `render_registry()` (из `client_registry_view`) + `render_analytics()`
  (метрики из `get_client_summary` + AI-анализ через `analytics_node`)
- `queries.get_client_registry()` — чтение реестра из view
- `app.py` — табы 1/2 подключены; тесты `web/test_nutritionist_views.py` 6/6 ✅

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
- **utils/** — knowledge.py (ada-002 + pgvector-поиск), vision.py (фото еды), voice.py (Whisper), web_access.py (Tavily + доверенные домены)
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

1. `pip install -r requirements.txt` (новые: openai, tavily)
2. Применить миграции в Supabase → SQL Editor:
   - `docs/migrations/001_add_observer_role.sql` ⏳
   - `docs/migrations/002_add_vector_search.sql` ⏳
3. Ключи окружения: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `GOOGLE_API_KEY`
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
