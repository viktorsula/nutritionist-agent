-- =============================================
-- Миграция 018: Согласие на обработку персональных данных (LEGAL-1/LEGAL-5)
-- =============================================
-- Контекст: диагностика проекта (docs/docs/diagnostic_report.md, раздел P0-LEGAL) нашла,
-- что явное информированное согласие на обработку данных о здоровье (Federal Law №2/2019,
-- ОАЭ) в проекте отсутствовало полностью — grep по слову "consent" не находил ничего.
-- Требование закона: согласие ДО сбора данных, гранулярно (health data / канал связи),
-- с фиксацией версии текста/даты/канала для доказуемости.
--
-- Пункт про трансграничную передачу данных сознательно НЕ включён (решение владельца,
-- 24.07.2026): отдельное согласие не снимает юридический риск LEGAL-2 (локализация в ОАЭ,
-- отложена на этап пилота) — тот остаётся как есть независимо от этой галочки.
--
-- client_consents — append-only журнал согласий (не перезаписывается; повторное согласие —
-- новая строка, напр. при смене версии текста). CHECK гарантирует, что запись создаётся
-- только при ПОЛНОМ согласии на оба пункта — частичное согласие не пишется вовсе
-- (сервер отклоняет запрос до insert, см. POST /consent), это лишь defense-in-depth в БД.
-- =============================================

CREATE TABLE IF NOT EXISTS client_consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    consent_version TEXT NOT NULL,
    health_data BOOLEAN NOT NULL,
    telegram_channel BOOLEAN NOT NULL,
    channel TEXT NOT NULL DEFAULT 'web',
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT client_consents_all_required CHECK (
        health_data AND telegram_channel
    )
);

CREATE INDEX IF NOT EXISTS idx_client_consents_client
    ON client_consents(client_id, accepted_at DESC);

COMMENT ON TABLE client_consents IS
    'Журнал согласий клиента на обработку данных (LEGAL-1/LEGAL-5, Federal Law №2/2019). '
    'Append-only: новая строка на каждое согласие (первичное или повторное при смене версии '
    'текста в system_settings.consent_text). Актуальное согласие клиента = запись с '
    'MAX(accepted_at). Гейт в ClientArea.tsx: пускает дальше, только если consent_version '
    'последней записи совпадает с текущей версией текста.';

-- RLS: клиент видит своё согласие (для гейта), нутрициолог видит все (аудит/доказуемость).
-- INSERT — только через backend (service_role обходит RLS, см. POST /consent в api/main.py):
-- сервер сам проверяет, что оба пункта true, и сам определяет текущую версию текста —
-- эти инварианты не должны зависеть от клиентского JS. Отдельной INSERT-политики для
-- authenticated намеренно нет.
ALTER TABLE client_consents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS consents_select ON client_consents;
CREATE POLICY consents_select ON client_consents FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));

-- entity_type='consent' — новое значение в CHECK audit_logs (используется для аудита
-- принятия согласия в POST /consent, entity_type/actor_type паттерн из миграции 013).
ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_entity_type_check;
ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_entity_type_check
    CHECK (entity_type IN ('client', 'plan', 'task', 'schedule', 'settings', 'profile', 'reminder', 'consent'));

-- =============================================
-- ПРОВЕРКА:
--   SELECT to_regclass('public.client_consents');
--   SELECT tablename, policyname FROM pg_policies WHERE tablename='client_consents';
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--     WHERE conname='audit_logs_entity_type_check';
-- РЕЗУЛЬТАТ: ✅ client_consents (RLS enabled, 1 policy: consents_select) + 'consent' в
--   audit_logs_entity_type_check
-- =============================================
