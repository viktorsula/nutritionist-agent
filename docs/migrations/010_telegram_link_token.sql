-- =============================================
-- МИГРАЦИЯ 010: Токен привязки Telegram-аккаунта клиента
-- Дата: 28 июня 2026
-- Описание: самопривязка Telegram (Вариант B). Нутрициолог в карточке клиента
--           генерирует одноразовую ссылку t.me/<bot>?start=<token>; клиент кликает,
--           бот по токену находит клиента и записывает clients.telegram_id.
--           Токен одноразовый (гасится после привязки) и со сроком годности
--           (expires_at). Контроль остаётся у нутрициолога: отвязка обнуляет
--           telegram_id, перевыпуск ссылки инвалидирует старый токен.
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
-- Зависит от: базовая схема (clients.telegram_id BIGINT UNIQUE).
-- =============================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS telegram_link_token TEXT,
    ADD COLUMN IF NOT EXISTS telegram_link_token_expires_at TIMESTAMPTZ;

-- Уникальность токена (частичный индекс: NULL не конфликтуют между собой).
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_telegram_link_token
    ON clients (telegram_link_token)
    WHERE telegram_link_token IS NOT NULL;

COMMENT ON COLUMN clients.telegram_link_token IS
    'Одноразовый токен привязки Telegram (t.me/<bot>?start=<token>). NULL — нет активной '
    'ссылки. Гасится в NULL после успешной привязки или при перевыпуске/отвязке.';
COMMENT ON COLUMN clients.telegram_link_token_expires_at IS
    'Срок годности токена привязки (TIMESTAMPTZ). После истечения ссылка недействительна.';

-- =============================================
-- ПРОВЕРКА
-- =============================================
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name='clients'
--     AND column_name IN ('telegram_link_token','telegram_link_token_expires_at');

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ clients.telegram_link_token (TEXT, UNIQUE partial index)
-- ✅ clients.telegram_link_token_expires_at (TIMESTAMPTZ)
-- =============================================
