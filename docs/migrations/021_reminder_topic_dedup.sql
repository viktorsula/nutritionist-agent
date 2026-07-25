-- =============================================
-- Миграция 021: Кросс-джобовый дедуп напоминаний по теме (P1-7)
-- =============================================
-- Раньше run_reminders() (утренний пакет) и run_reminder_followups() (повторы) слали
-- сообщения клиенту независимо, без координации. Счётчик повторов (followups_sent)
-- считался только внутри ОДНОГО reminder_occurrence — если у клиента больше одного
-- активного напоминания с одинаковым expected_response (напр. два напоминания про воду),
-- в один день клиент мог получить несколько независимых сообщений об одном и том же.
--
-- last_notified_date — локальная (клиентская) дата последнего фактического сообщения по
-- этому срабатыванию: due_date при первой отправке (record_occurrence), обновляется при
-- каждом повторе (bump_occurrence_followup). Проверка «уже спрашивали сегодня об этой теме»
-- идёт по всем occurrences клиента с тем же reminders.expected_response, а не только по
-- текущему occurrence — отсюда и «кросс-джобовый».
-- Спецификация: docs/spec_reminders.md, docs/docs/diagnostic_report.md (P1-7 / 7.3)
-- =============================================

ALTER TABLE reminder_occurrences
    ADD COLUMN IF NOT EXISTS last_notified_date DATE;

-- Бэкофилл существующих строк: на момент создания last_notified_date = due_date.
UPDATE reminder_occurrences SET last_notified_date = due_date WHERE last_notified_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_reminder_occurrences_last_notified
    ON reminder_occurrences(client_id, last_notified_date);

COMMENT ON COLUMN reminder_occurrences.last_notified_date IS
    'Локальная (клиентская) дата последнего реального сообщения по этому срабатыванию '
    '(создание ИЛИ повтор) — основа кросс-джобового дедупа «одно сообщение по теме в день» (P1-7).';

-- =============================================
-- ПРОВЕРКА:
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='reminder_occurrences' AND column_name='last_notified_date';
-- РЕЗУЛЬТАТ: ✅ last_notified_date DATE, бэкофилл из due_date, индекс на (client_id, last_notified_date)
-- =============================================
