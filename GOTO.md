# GOTO — НАЧАЛО СЛЕДУЮЩЕЙ СЕССИИ

**Обновлено:** 14 июня 2026, после Этапа 6 Часть A (код агентов клиента + роутинг)

---

## 🎯 ЦЕЛЬ СЛЕДУЮЩЕЙ СЕССИИ

**Этап 6, Часть A — Шаг 3:** подключить Telegram (фото и голос) к графу оркестратора.
Затем **Шаг 4** (тесты), потом **Часть B** (ветка нутрициолога).

---

## 📍 ГДЕ МЫ СЕЙЧАС

Вся работа Этапа 6 — на ветке **`stage6-utils`** (НЕ влита в main, push мог быть сделан вручную).

### ✅ Сделано (Часть A, ветка клиента):
- **requirements.txt** — +openai; модернизирован LangGraph (langgraph>=1.0, langchain-core>=0.3)
- **utils/** — knowledge.py (ada-002 + pgvector-поиск), vision.py (фото еды), voice.py (Whisper), web_access.py (Tavily + доверенные домены)
- **migration 002** — RPC match_knowledge_base / match_client_documents
- **agents/client/** — vision_agent, diary_agent, nutrition_agent, общий food_analysis.py
- **orchestrator.py** — роутинг: ingest → load_context → route → [vision|diary|nutrition|dialog] → format → save
- **prompts/client/** — vision_system.md, diary_system.md, nutrition_system.md
- **Фиксы** — сохранение диалога (save_conversation), удалён check_alerts_node

### ⬜ Осталось в Части A:
- **Шаг 3:** `telegram/handlers.py` — фото/голос → граф
- **Шаг 4:** тесты + прогон

---

## 📋 ПЛАН ШАГА 3 (Telegram)

`telegram/handlers.py` сейчас: текст работает через `route_message()`, фото/голос — заглушки.
Нужно:
1. **Фото** (`handle_photo`): скачать файл из Telegram → `bytes` → передать в обработку с
   `message_type='photo'`, `metadata={'image_bytes': <bytes>, 'mime_type': 'image/jpeg'}`,
   подпись к фото → как `message` (caption).
2. **Голос** (`handle_voice`): скачать `.ogg` → `bytes` → `message_type='voice'`,
   `metadata={'audio_bytes': <bytes>, 'audio_name': 'voice.ogg'}`. Транскрипцию делает
   сам оркестратор (узел `ingest`), здесь только передать байты.
3. Проверить путь вызова: handlers → router.route_message → process_client_message (граф).

**Контракт metadata (уже ожидается агентами/оркестратором):**
- фото: `metadata['image_bytes']`, `metadata['mime_type']`
- голос: `metadata['audio_bytes']`, `metadata['audio_name']`

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
