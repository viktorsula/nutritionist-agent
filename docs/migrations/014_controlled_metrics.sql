-- =============================================
-- Миграция 014: Контролируемые показатели (Слайс 2A напоминаний)
-- =============================================
-- Единая модель произвольных показателей клиента, которые контролирует нутрициолог
-- (замеры талии/шеи/бёдер, сон, пульс, часы сна, стресс и т.п.). По образцу
-- client_profiles.tracked_lab_indicators.
--
-- Категории → хранилище: physical (weight/waist/neck/hips) → measurements (колонки уже
-- есть); lab → lab_results; sleep/custom → client_metrics (эта таблица).
-- Спецификация: docs/spec_reminders.md
-- =============================================

-- ── Каталог показателей клиента (задаёт нутрициолог) ─────────────────────────
ALTER TABLE client_profiles
    ADD COLUMN IF NOT EXISTS controlled_metrics JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN client_profiles.controlled_metrics IS
    'Контролируемые показатели клиента (задаёт нутрициолог): '
    '[{"key":"waist","label_ru":"Талия","label_en":"Waist","unit":"см","category":"physical"}]. '
    'category: physical|lab|sleep|custom. physical→measurements, lab→lab_results, '
    'sleep/custom→client_metrics.';

-- ── Значения произвольных показателей (long-формат) ──────────────────────────
CREATE TABLE IF NOT EXISTS client_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    category TEXT,                          -- sleep | custom (physical/lab пишутся в свои таблицы)
    value_num NUMERIC,                      -- числовое значение (пульс, часы сна, продолжительность)
    value_text TEXT,                        -- текстовое значение, если не число
    unit TEXT,
    meta JSONB,                             -- для сна: {"bedtime":"23:30","wake":"07:00"}
    measured_at DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_metrics_key
    ON client_metrics(client_id, metric_key, measured_at DESC);

COMMENT ON TABLE client_metrics IS
    'Значения контролируемых показателей клиента (sleep/custom). physical→measurements, lab→lab_results.';

-- ── RLS: доступ через сервисный бэкенд (как reminders) ────────────────────────
-- Запись — оркестратор (сервисный ключ, обходит RLS). Чтение для кабинета — через
-- бэкенд-эндпоинты (2C). Прямой клиентский/анонимный доступ запрещён (нет политик).
ALTER TABLE client_metrics ENABLE ROW LEVEL SECURITY;

-- =============================================
-- ПРОВЕРКА:
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='client_profiles' AND column_name='controlled_metrics';
--   SELECT table_name FROM information_schema.tables WHERE table_name='client_metrics';
-- РЕЗУЛЬТАТ: ✅ controlled_metrics (JSONB) + таблица client_metrics + RLS
-- =============================================
