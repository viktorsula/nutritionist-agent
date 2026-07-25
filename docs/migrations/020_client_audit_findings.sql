-- =============================================
-- Миграция 020: Проактивный аудит клиента (NEW-1)
-- =============================================
-- Контекст: docs/docs/diagnostic_report.md, раздел NEW. Ассистент 2 раза в неделю
-- (по умолчанию Пн/Чт) сверяет заметки нутрициолога/назначения/динамику клиента/базу
-- знаний, ищет расхождения и возможные ошибки назначений. Находки пишутся сюда ТОЛЬКО
-- если что-то реально найдено ("порог срабатывания — только при находке") — таблица
-- не растёт на пустом месте. Вывод — в карточку клиента нутрициологу (фронт), НЕ в
-- Telegram: severity ограничен ('low'|'medium'), критичные вещи по-прежнему идут через
-- существующий детерминированный путь алертов (business_rules), не через этот аудит.
-- =============================================

CREATE TABLE IF NOT EXISTS client_audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'dismissed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dismissed_at TIMESTAMPTZ,
    dismissed_by UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_client_audit_findings_client
    ON client_audit_findings(client_id, status, created_at DESC);

COMMENT ON TABLE client_audit_findings IS
    'Находки проактивного аудита клиента (NEW-1) — расхождения/противоречия/возможные '
    'ошибки назначений, обнаруженные ассистентом при сверке заметок/плана/динамики/базы '
    'знаний. Пишется только при находке (нет строки = нет расхождений на момент прогона). '
    'severity ограничен low/medium — это не канал критичных алертов (те идут через '
    'business_rules и Telegram отдельно), а материал для планового просмотра нутрициологом.';

-- RLS: только нутрициолог (находки для него, не для клиента) — тот же паттерн, что
-- system_settings/knowledge_base/audit_logs (миграция 004).
ALTER TABLE client_audit_findings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_findings_nutri ON client_audit_findings;
CREATE POLICY audit_findings_nutri ON client_audit_findings FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

-- =============================================
-- ПРОВЕРКА:
--   SELECT to_regclass('public.client_audit_findings');
--   SELECT tablename, policyname FROM pg_policies WHERE tablename='client_audit_findings';
-- РЕЗУЛЬТАТ: ✅ client_audit_findings (RLS enabled, 1 policy: audit_findings_nutri)
-- =============================================
