-- =============================================
-- МИГРАЦИЯ 006: Per-client выбор показателей анализов нутрициологом
-- Дата: 20 июня 2026
-- Описание: список показателей анализов, которые отслеживаются и выводятся в график
--           динамики у КОНКРЕТНОГО клиента. Задаёт нутрициолог. Хранится в профиле.
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
-- Зависит от: 003 (lab_results), 004 (RLS на client_profiles — нутрициолог пишет).
-- =============================================

ALTER TABLE client_profiles
    ADD COLUMN IF NOT EXISTS tracked_lab_indicators JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN client_profiles.tracked_lab_indicators IS
    'Показатели анализов клиента для графика динамики (выбирает нутрициолог): '
    '[{"key":"cholesterol_total","label_ru":"Холестерин общий","label_en":"Total cholesterol",'
    '"unit":"ммоль/л","ref_min":3.0,"ref_max":5.2,"order":1}]. '
    'key совпадает с lab_results.indicator.';

-- =============================================
-- ПРОВЕРКА
-- =============================================
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='client_profiles' AND column_name='tracked_lab_indicators';

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ client_profiles.tracked_lab_indicators (JSONB) — per-client список показателей
--    График клиента рисует только их (в порядке order, с нормой ref_min/ref_max).
-- =============================================
