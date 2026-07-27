# Nutritionist Agent

ИИ-ассистент для нутрициолога. Два режима работы:

- **Режим нутрициолога** — аналитика по клиентам, управление планами и напоминаниями, алерты, проактивный аудит клиентов.
- **Режим клиента** — ежедневный диалог, дневник питания (текст/фото/голос), напоминания, личный кабинет.

Владелец проекта: Виктор Сула, Дубай.

## Архитектура

```
Telegram (webhook)                React SPA (Vite + TS)
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
              FastAPI (api/main.py)
                       │
                agents/router.py
                       │
              business_rules/  ←→  Supabase (database/queries.py)
                       │
      LLM-оркестратор (agents/*/agent_orchestrator.py, Claude tool-calling)
                       │   ↳ при сбое — откат на граф LangGraph
                       ▼
                   utils/llm.py → Claude / Groq / Gemini
```

**Ключевой принцип:** нутрициолог — единственный источник назначений (планы, задачи, пороги).
Агент анализирует и советует, но ничего не назначает сам. Безопасность (алерты, проверка
ограничений и аллергий) считается детерминированно в `business_rules/`, а не «на усмотрение»
модели.

## Стек

| Слой | Технология |
|------|-----------|
| Бэкенд | Python 3.11, FastAPI, APScheduler (планировщик уведомлений) |
| Фронт | React 18, TypeScript, Vite, TailwindCSS, TanStack Query |
| БД | Supabase (PostgreSQL + Auth + Storage + pgvector) |
| LLM | Claude (оркестрация, аналитика), Groq llama-3.3-70b (напоминания), Gemini 2.5 Flash (фото) |
| Голос | OpenAI Whisper |
| Каналы | Telegram Bot (основной для клиента), веб-кабинет |
| Мониторинг | LangFuse |

Модели меняются без правки кода — через кабинет нутрициолога («Настройки → LLM-модели»,
хранится в `system_settings.llm_config`).

## Структура

```
api/              FastAPI: роуты, аутентификация, планировщик (scheduler.py)
agents/           router.py + оркестраторы клиента и нутрициолога, LangGraph-граф (fallback)
business_rules/   Детерминированный слой: доступ, оплата, медицинские алерты
database/         Клиент Supabase, запросы (queries.py), аутентификация
utils/            LLM, зрение, голос, эмбеддинги/RAG, уведомления, веб-поиск
prompts/          Системные промпты (.md); приоритет БД над файлами
tg_bot/           Telegram-бот (webhook)
frontend/         React SPA (кабинеты нутрициолога и клиента)
monitoring/       LangFuse-трейсинг
docs/             Схема БД, миграции, ТЗ, журнал прогресса, диагностика
```

## Запуск локально

**Бэкенд:**

```bash
pip install -r requirements.txt
cp .env.example .env          # заполнить ключи
uvicorn api.main:app --reload
```

**Фронт:**

```bash
cd frontend
npm ci
npm run dev
```

Переменные окружения — см. `.env.example`. Секреты только через окружение:
`load_dotenv()` в коде не используется намеренно, ключи не хардкодятся.

## Тесты

```bash
python -m pytest -q          # бэкенд
cd frontend && npm run typecheck && npm test    # фронт
```

Гоняются автоматически на каждый PR и push в `main` — см. `.github/workflows/ci.yml`.

## Миграции БД

SQL-миграции лежат в `docs/migrations/` и применяются **вручную** через Supabase → SQL Editor.
Реестр применённых миграций и verify-SQL для проверки дрейфа — в `docs/migrations/README.md`.
При добавлении новой миграции обязательно дописать строку в реестр.

## Деплой

Render, два сервиса:

- `nutritionist-agent` — бэкенд, Docker (см. `Dockerfile`, точка входа `uvicorn api.main:app`)
- `nutritionist-agent-1` — фронт, статика из `frontend/dist`

Telegram работает через webhook на бэкенд.

## Документация

| Файл | Что внутри |
|------|-----------|
| `CLAUDE.md` | Контекст проекта для ИИ-ассистента, правила работы, ключевые решения |
| `docs/progress.md` | Журнал прогресса по сессиям (источник правды по истории) |
| `docs/docs/diagnostic_report.md` | Полная диагностика: находки с приоритетами + статус устранения |
| `docs/migrations/README.md` | Реестр миграций и их статус на проде |
| `docs/schema.sql` | Схема БД — консолидированная (база v1.3 + миграции 001–022) |
| `docs/archive/` | Исторические документы, не поддерживаются в актуальном состоянии |
