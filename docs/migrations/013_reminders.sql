-- =============================================
-- Миграция 013: Напоминания клиенту (Фаза 1)
-- =============================================
-- Нутрициолог заводит напоминания клиенту с временем и регулярностью; ассистент
-- шлёт их в Telegram по расписанию (в часовом поясе клиента), пакетом на одно время.
--
-- Модель В: reminders (шаблон) + reminder_occurrences (срабатывания).
-- Ежедневный шаблон не имеет терминального статуса — «закрывается» его срабатывание.
-- Спецификация: docs/spec_reminders.md
-- =============================================

-- ── Шаблон напоминания ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    remind_at TIME NOT NULL,                 -- локальное время клиента (timezone из clients)
    recurrence TEXT NOT NULL DEFAULT 'daily'
        CHECK (recurrence IN ('once', 'daily', 'weekly')),
    weekday SMALLINT,                        -- для weekly: 0=Пн … 6=Вс (Python date.weekday())
    remind_date DATE,                        -- для once: дата единственного срабатывания
    requires_response BOOLEAN NOT NULL DEFAULT false,  -- задел Фазы 2 (контроль ответа)
    active BOOLEAN NOT NULL DEFAULT true,
    created_by TEXT NOT NULL DEFAULT 'nutritionist',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reminders_client
    ON reminders(client_id) WHERE active = true;

COMMENT ON TABLE reminders IS
    'Напоминания клиенту (Фаза 1): расписание + регулярность. requires_response — задел Ф2.';
COMMENT ON COLUMN reminders.weekday IS 'weekly: 0=Пн … 6=Вс (Python date.weekday())';

-- ── Срабатывания (дедуп отправки; основа контроля ответа в Фазе 2) ────────────
CREATE TABLE IF NOT EXISTS reminder_occurrences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reminder_id UUID NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    due_date DATE NOT NULL,                  -- локальная дата клиента, когда сработало
    sent_at TIMESTAMP DEFAULT NOW(),
    -- Ф2 добавит: status, response_event_id, followups_sent, next_followup_at
    CONSTRAINT uq_occurrence_per_day UNIQUE (reminder_id, due_date)
);

CREATE INDEX IF NOT EXISTS idx_reminder_occurrences_client
    ON reminder_occurrences(client_id, due_date DESC);

COMMENT ON TABLE reminder_occurrences IS
    'Срабатывания напоминаний: дедуп «одно в день» (UNIQUE reminder_id+due_date). Ф2 добавит контроль ответа.';

-- ── RLS: доступ только через сервисный бэкенд (клиент напоминания НЕ видит) ────
-- Сервисный ключ обходит RLS; отдельных permissive-политик нет → прямой доступ
-- из клиентского/анонимного контекста запрещён. Управление — через API нутрициолога.
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminder_occurrences ENABLE ROW LEVEL SECURITY;

-- ── Аудит: разрешить entity_type='reminder' ──────────────────────────────────
ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_entity_type_check;
ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_entity_type_check
    CHECK (entity_type IN ('client', 'plan', 'task', 'schedule', 'settings', 'profile', 'reminder'));

-- =============================================
-- ПРОВЕРКА:
--   SELECT table_name FROM information_schema.tables
--     WHERE table_name IN ('reminders','reminder_occurrences');
-- РЕЗУЛЬТАТ: ✅ 2 таблицы + RLS enabled (backend-only)
-- =============================================
