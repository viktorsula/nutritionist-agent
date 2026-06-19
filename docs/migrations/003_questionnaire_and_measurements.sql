-- =============================================
-- МИГРАЦИЯ 003: Опросник онбординга + замеры тела + анализы
-- Дата: 19 июня 2026
-- Описание: хранилище полного опросника клиента (33 вопроса), динамика
--           замеров тела (вес/шея/талия/бёдра) и числовых анализов для графиков.
-- Применить: Supabase → SQL Editor.
-- =============================================

-- ---------------------------------------------
-- 1. Опросник онбординга (полный, 33 вопроса) — JSONB в профиле клиента
-- ---------------------------------------------
-- Ключевые поля (вес, рост, дата рождения, аллергии, цель, target_weight)
-- дублируются в существующие колонки client_profiles — нужны для алертов/графиков.
-- Полный текст ответов хранится здесь.
ALTER TABLE client_profiles
    ADD COLUMN IF NOT EXISTS questionnaire_json JSONB DEFAULT '{}';

COMMENT ON COLUMN client_profiles.questionnaire_json IS
    'Полный опросник онбординга (33 вопроса): {question_id: answer}';

-- ---------------------------------------------
-- 2. Замеры тела (динамика веса и объёмов)
-- ---------------------------------------------
CREATE TABLE IF NOT EXISTS measurements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    measured_at DATE NOT NULL DEFAULT CURRENT_DATE,
    weight DECIMAL(5,2),      -- кг
    neck DECIMAL(5,2),        -- объём шеи, см
    waist DECIMAL(5,2),       -- объём талии, см
    hips DECIMAL(5,2),        -- объём бёдер, см
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_measurements_client_date
    ON measurements(client_id, measured_at DESC);

COMMENT ON TABLE measurements IS
    'Замеры тела клиента во времени: вес, объёмы (для графиков динамики)';

-- ---------------------------------------------
-- 3. Анализы (числовые показатели для графиков)
-- ---------------------------------------------
-- indicator — название показателя (например, 'glucose', 'cholesterol_total').
-- Список «топ-10 для отображения» задаёт нутрициолог в system_settings.
CREATE TABLE IF NOT EXISTS lab_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    measured_at DATE NOT NULL DEFAULT CURRENT_DATE,
    indicator TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source TEXT,              -- откуда: 'nutritionist' | 'client_pdf' | 'lab'
    document_id UUID REFERENCES document_metadata(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lab_results_client_indicator
    ON lab_results(client_id, indicator, measured_at DESC);

COMMENT ON TABLE lab_results IS
    'Числовые показатели анализов клиента во времени (для графиков динамики)';

-- ---------------------------------------------
-- 4. Список отображаемых показателей анализов (до 10) — настройка нутрициолога
-- ---------------------------------------------
INSERT INTO system_settings (key, value, description) VALUES
('lab_indicators_top',
 '[]'::jsonb,
 'Показатели анализов для дашборда клиента (до 10), задаёт нутрициолог: [{"key":"glucose","label_ru":"Глюкоза","label_en":"Glucose","unit":"ммоль/л"}]')
ON CONFLICT (key) DO NOTHING;

-- =============================================
-- ПРОВЕРКА
-- =============================================
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='client_profiles' AND column_name='questionnaire_json';
-- SELECT to_regclass('public.measurements'), to_regclass('public.lab_results');
-- SELECT value FROM system_settings WHERE key='lab_indicators_top';

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ client_profiles.questionnaire_json (JSONB) — полный опросник
-- ✅ measurements — замеры тела (вес/шея/талия/бёдра)
-- ✅ lab_results — числовые анализы для графиков
-- ✅ system_settings.lab_indicators_top — список показателей (нутрициолог)
-- =============================================
