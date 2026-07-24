-- =============================================
-- Миграция 017: Саммари анкеты + история изменений (редактирование анкеты клиентом)
-- =============================================
-- Контекст: LLM-оркестратор клиента раньше подавал остаток анкеты построчным дампом
-- (~24 поля) в системный промпт КАЖДЫЙ ход — дорого и избыточно. Плюс до этой миграции
-- анкета была write-once: submitQuestionnaire() делал upsert, повторная отправка стирала
-- старые ответы без следа. Эта миграция добавляет:
--   1) questionnaire_summary — компактное LLM-саммари (генерируется один раз при отправке,
--      не на каждый ход диалога);
--   2) client_questionnaire_history — снимок ответов при КАЖДОЙ отправке (первичной и любой
--      последующей), ничего не перезаписывается.
-- =============================================

ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS questionnaire_summary TEXT;

COMMENT ON COLUMN client_profiles.questionnaire_summary IS
    'Компактное саммари анкеты онбординга (LLM, task_type=summary), генерируется/обновляется '
    'при каждой отправке анкеты (POST /questionnaire-summary). Подаётся в системный промпт '
    'LLM-оркестратора клиента вместо построчного дампа questionnaire_json; при NULL (старые '
    'клиенты до этой миграции, либо сбой генерации) оркестратор откатывается на построчный '
    'формат из questionnaire_json.';

CREATE TABLE IF NOT EXISTS client_questionnaire_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    questionnaire_json JSONB NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questionnaire_history_client
    ON client_questionnaire_history(client_id, submitted_at DESC);

COMMENT ON TABLE client_questionnaire_history IS
    'Снимок полных ответов анкеты при каждой отправке (первичной и повторных) — история '
    'изменений, append-only. client_profiles.questionnaire_json хранит только ТЕКУЩИЙ снимок '
    '(последняя запись здесь по submitted_at desc == текущий questionnaire_json).';

-- RLS: тот же паттерн, что client_profiles/measurements (миграция 004) — клиент видит
-- и добавляет только своё, нутрициолог видит всё; append-only (UPDATE/DELETE не даём никому
-- через RLS — история неизменяема, кроме service_role, который RLS обходит).
ALTER TABLE client_questionnaire_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS qhistory_select ON client_questionnaire_history;
CREATE POLICY qhistory_select ON client_questionnaire_history FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));

DROP POLICY IF EXISTS qhistory_insert ON client_questionnaire_history;
CREATE POLICY qhistory_insert ON client_questionnaire_history FOR INSERT TO authenticated
    WITH CHECK (app_is_nutritionist() OR client_id = app_current_client_id());

-- =============================================
-- ПРОВЕРКА:
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='client_profiles' AND column_name='questionnaire_summary';
--   SELECT to_regclass('public.client_questionnaire_history');
--   SELECT tablename, policyname FROM pg_policies
--     WHERE tablename='client_questionnaire_history';
-- РЕЗУЛЬТАТ: ✅ questionnaire_summary + client_questionnaire_history (RLS enabled, 2 policies)
-- =============================================
