-- =============================================
-- Миграция 016: Дедлайны отчётов, per-item кадэнс, замер груди (Слайс 2.1a)
-- =============================================
-- Контроль приёмов пищи по дедлайнам (завтрак до 12:00, обед до 17:00, ужин до 22:00) +
-- per-элемент настройки догона + столбец груди. Спецификация: docs/spec_reminders.md (v2).
-- =============================================

ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS followup_after_hours INT,   -- переопределяет профиль (NULL → профиль)
    ADD COLUMN IF NOT EXISTS max_followups INT,          -- переопределяет профиль (NULL → профиль)
    ADD COLUMN IF NOT EXISTS response_deadline TIME;     -- дедлайн отчёта (лок. время): еда 12/17/22

COMMENT ON COLUMN reminders.response_deadline IS
    'Дедлайн ответа клиента (локальное время). Если задан — «сдались» наступает в этот момент '
    'сегодня (а не sent_at + give_up_hours). Для приёмов пищи: завтрак 12:00, обед 17:00, ужин 22:00.';

-- Замер груди (для полноты набора замеров тела; остальные — weight/neck/waist/hips в 003).
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS chest DECIMAL(5,2);

COMMENT ON COLUMN measurements.chest IS 'Объём груди, см';

-- =============================================
-- ПРОВЕРКА:
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='reminders'
--       AND column_name IN ('followup_after_hours','max_followups','response_deadline');
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='measurements' AND column_name='chest';
-- РЕЗУЛЬТАТ: ✅ per-item кадэнс + дедлайн + measurements.chest
-- =============================================
