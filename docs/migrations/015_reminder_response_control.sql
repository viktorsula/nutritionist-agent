-- =============================================
-- Миграция 015: Контроль ответа на напоминания (Слайс 2B)
-- =============================================
-- Расширяет напоминания и срабатывания под контур обратной связи: напоминание может
-- ЖДАТЬ ответа определённого типа (вес/замер/анализы/сон/текст). Планировщик отслеживает
-- срабатывание: пришёл ответ → закрыто; нет ответа → повтор; вышел срок → «сдались» (алерт).
-- Спецификация: docs/spec_reminders.md
-- =============================================

-- ── Что за ответ ждём (ключ показателя | 'text' | NULL=не ждём) ───────────────
ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS expected_response TEXT;

COMMENT ON COLUMN reminders.expected_response IS
    'Что закрывает срабатывание: ключ показателя (weight/waist/neck/hips/sleep/labs/<custom>) '
    'либо ''text'' (любой ответ клиента). NULL = ответа не ждём. Работает при requires_response=true.';

-- ── Жизненный цикл срабатывания ──────────────────────────────────────────────
ALTER TABLE reminder_occurrences
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'sent'
        CHECK (status IN ('sent', 'answered', 'expired')),
    ADD COLUMN IF NOT EXISTS response_ref JSONB,       -- чем закрыто (таблица/значение) — справочно
    ADD COLUMN IF NOT EXISTS followups_sent SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_followup_at TIMESTAMP,  -- когда слать повтор (для ждущих ответа)
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;      -- когда закрылось (answered/expired)

CREATE INDEX IF NOT EXISTS idx_reminder_occurrences_open
    ON reminder_occurrences(status) WHERE status = 'sent';

COMMENT ON COLUMN reminder_occurrences.status IS
    'sent → ждёт ответа/повтора; answered → ответ получен; expired → срок вышел (алерт нутрициологу)';

-- Профили кадэнса догона (повтор через / макс повторов / срок сдаться по типу ответа)
-- живут в system_settings.reminder_cadence (правятся без кода); код содержит дефолты.

-- =============================================
-- ПРОВЕРКА:
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='reminder_occurrences'
--       AND column_name IN ('status','followups_sent','next_followup_at','resolved_at');
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='reminders' AND column_name='expected_response';
-- РЕЗУЛЬТАТ: ✅ expected_response + жизненный цикл срабатывания
-- =============================================
