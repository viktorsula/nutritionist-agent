-- =============================================
-- МИГРАЦИЯ 009: Скользящая сводка диалога клиента (rolling-summary)
-- Дата: 24 июня 2026
-- Описание: долговременная память клиентского диалога. Вместо жёсткого окна
--           «последние 10 реплик» агент дополнительно получает краткую сводку
--           прошлых разговоров (durable-факты: цели, предпочтения, ограничения,
--           повторяющиеся темы). Сводка обновляется по мере накопления сообщений.
-- Поля на clients (их уже грузит load_context через get_client_by_id — без лишних чтений):
--   conversation_summary   — текст сводки;
--   summary_message_count  — сколько сообщений уже отражено в сводке (маркер буфера);
--   summary_updated_at      — когда сводка обновлялась.
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
-- Зависит от: clients.
-- =============================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS conversation_summary TEXT,
    ADD COLUMN IF NOT EXISTS summary_message_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS summary_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN clients.conversation_summary IS
    'Скользящая сводка прошлых разговоров клиента (rolling-summary): durable-факты для контекста агента.';
COMMENT ON COLUMN clients.summary_message_count IS
    'Сколько сообщений диалога уже отражено в conversation_summary (маркер summary-буфера).';
