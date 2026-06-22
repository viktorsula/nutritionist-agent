-- =============================================
-- МИГРАЦИЯ 004: Row Level Security (RLS) для веб-доступа клиентов
-- Дата: 19 июня 2026
-- Описание: безопасность многопользовательского веба. Браузер ходит в Supabase
--           под JWT пользователя (роль authenticated) — RLS ограничивает доступ.
--           service_role (агент, n8n, серверный API) RLS ОБХОДИТ — это намеренно.
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА (DROP POLICY IF EXISTS).
--
-- Модель ролей: users.role ∈ {nutritionist, client, observer}, связь с
-- auth.users через users.auth_id = auth.uid().
--   • client      — видит/правит только свои данные; НЕ может менять свой
--                   статус/оплату/доступ/роль (нет UPDATE на clients/users).
--   • nutritionist — полный доступ ко всем данным.
--   • observer     — только чтение (на будущее, v2.0).
-- =============================================

-- ---------------------------------------------
-- 0. Функции-хелперы (SECURITY DEFINER — обходят RLS, без рекурсии в политиках)
-- ---------------------------------------------
CREATE OR REPLACE FUNCTION app_user_role()
RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT role FROM users WHERE auth_id = auth.uid();
$$;

CREATE OR REPLACE FUNCTION app_current_client_id()
RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT c.id FROM clients c
    JOIN users u ON c.user_id = u.id
    WHERE u.auth_id = auth.uid();
$$;

CREATE OR REPLACE FUNCTION app_is_nutritionist()
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT app_user_role() = 'nutritionist';
$$;

CREATE OR REPLACE FUNCTION app_can_read_client(target UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT app_is_nutritionist()
        OR app_user_role() = 'observer'
        OR target = app_current_client_id();
$$;

-- ---------------------------------------------
-- Гранты на новые таблицы (existing tables уже имеют гранты Supabase по умолчанию)
-- ---------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON measurements TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON lab_results  TO authenticated;

-- ---------------------------------------------
-- 1. users — роль/учётка. Клиент НЕ может менять роль.
-- ---------------------------------------------
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_select ON users;
CREATE POLICY users_select ON users FOR SELECT TO authenticated
    USING (auth_id = auth.uid() OR app_is_nutritionist());
-- INSERT/UPDATE/DELETE: только service_role (создание/смена роли — через серверный API).

-- ---------------------------------------------
-- 2. clients — статусы/оплата/доступ. Клиент: только чтение своей строки.
-- ---------------------------------------------
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS clients_select ON clients;
CREATE POLICY clients_select ON clients FOR SELECT TO authenticated
    USING (app_can_read_client(id));
DROP POLICY IF EXISTS clients_write_nutri ON clients;
CREATE POLICY clients_write_nutri ON clients FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());
-- Клиент НЕ имеет UPDATE/INSERT/DELETE → не может менять свой статус/оплату.
-- Правки своих настроек (язык/таймзона) — через серверный API при необходимости.

-- ---------------------------------------------
-- 3. client_profiles — медданные/опросник. Клиент правит только свой.
-- ---------------------------------------------
ALTER TABLE client_profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cprofiles_select ON client_profiles;
CREATE POLICY cprofiles_select ON client_profiles FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS cprofiles_insert ON client_profiles;
CREATE POLICY cprofiles_insert ON client_profiles FOR INSERT TO authenticated
    WITH CHECK (app_is_nutritionist() OR client_id = app_current_client_id());
DROP POLICY IF EXISTS cprofiles_update ON client_profiles;
CREATE POLICY cprofiles_update ON client_profiles FOR UPDATE TO authenticated
    USING (app_is_nutritionist() OR client_id = app_current_client_id())
    WITH CHECK (app_is_nutritionist() OR client_id = app_current_client_id());

-- ---------------------------------------------
-- 4. measurements — замеры. Клиент: чтение своих + добавление своих.
-- ---------------------------------------------
ALTER TABLE measurements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS measurements_select ON measurements;
CREATE POLICY measurements_select ON measurements FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS measurements_insert ON measurements;
CREATE POLICY measurements_insert ON measurements FOR INSERT TO authenticated
    WITH CHECK (app_is_nutritionist() OR client_id = app_current_client_id());
DROP POLICY IF EXISTS measurements_update_nutri ON measurements;
CREATE POLICY measurements_update_nutri ON measurements FOR UPDATE TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());
DROP POLICY IF EXISTS measurements_delete_nutri ON measurements;
CREATE POLICY measurements_delete_nutri ON measurements FOR DELETE TO authenticated
    USING (app_is_nutritionist());

-- ---------------------------------------------
-- 5. lab_results — анализы. Клиент: только чтение; вносит нутрициолог.
-- ---------------------------------------------
ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lab_select ON lab_results;
CREATE POLICY lab_select ON lab_results FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS lab_write_nutri ON lab_results;
CREATE POLICY lab_write_nutri ON lab_results FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

-- ---------------------------------------------
-- 6. conversations / client_events — чтение своих; запись серверная (service_role)
-- ---------------------------------------------
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversations_select ON conversations;
CREATE POLICY conversations_select ON conversations FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS conversations_write_nutri ON conversations;
CREATE POLICY conversations_write_nutri ON conversations FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

ALTER TABLE client_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cevents_select ON client_events;
CREATE POLICY cevents_select ON client_events FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS cevents_write_nutri ON client_events;
CREATE POLICY cevents_write_nutri ON client_events FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

-- ---------------------------------------------
-- 7. Планы/задачи/wellness — чтение своих; запись нутрициолога
-- ---------------------------------------------
ALTER TABLE nutrition_plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nplans_select ON nutrition_plans;
CREATE POLICY nplans_select ON nutrition_plans FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS nplans_write_nutri ON nutrition_plans;
CREATE POLICY nplans_write_nutri ON nutrition_plans FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

ALTER TABLE wellness_plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS wplans_select ON wellness_plans;
CREATE POLICY wplans_select ON wellness_plans FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS wplans_write_nutri ON wellness_plans;
CREATE POLICY wplans_write_nutri ON wellness_plans FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tasks_select ON tasks;
CREATE POLICY tasks_select ON tasks FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS tasks_write_nutri ON tasks;
CREATE POLICY tasks_write_nutri ON tasks FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

-- ---------------------------------------------
-- 8. notification_schedule — клиент: чтение/правка своих; нутрициолог: всё
-- ---------------------------------------------
ALTER TABLE notification_schedule ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nsched_select ON notification_schedule;
CREATE POLICY nsched_select ON notification_schedule FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS nsched_cud ON notification_schedule;
CREATE POLICY nsched_cud ON notification_schedule FOR ALL TO authenticated
    USING (app_is_nutritionist() OR client_id = app_current_client_id())
    WITH CHECK (app_is_nutritionist() OR client_id = app_current_client_id());

-- ---------------------------------------------
-- 9. Документы — клиент: свои (+ загрузка своих); нутрициолог: всё.
--    document_metadata.client_id может быть NULL (база знаний) → только нутрициолог.
-- ---------------------------------------------
ALTER TABLE document_metadata ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS docmeta_select ON document_metadata;
CREATE POLICY docmeta_select ON document_metadata FOR SELECT TO authenticated
    USING (app_is_nutritionist()
        OR (client_id IS NOT NULL AND client_id = app_current_client_id()));
DROP POLICY IF EXISTS docmeta_insert ON document_metadata;
CREATE POLICY docmeta_insert ON document_metadata FOR INSERT TO authenticated
    WITH CHECK (app_is_nutritionist() OR client_id = app_current_client_id());
DROP POLICY IF EXISTS docmeta_update_nutri ON document_metadata;
CREATE POLICY docmeta_update_nutri ON document_metadata FOR UPDATE TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

ALTER TABLE client_documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cdocs_select ON client_documents;
CREATE POLICY cdocs_select ON client_documents FOR SELECT TO authenticated
    USING (app_can_read_client(client_id));
DROP POLICY IF EXISTS cdocs_write_nutri ON client_documents;
CREATE POLICY cdocs_write_nutri ON client_documents FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

-- ---------------------------------------------
-- 10. Только нутрициолог: настройки, база знаний, аудит
--     (service_role всё равно обходит RLS — серверная запись работает)
-- ---------------------------------------------
ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS settings_nutri ON system_settings;
CREATE POLICY settings_nutri ON system_settings FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS kb_nutri ON knowledge_base;
CREATE POLICY kb_nutri ON knowledge_base FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_select_nutri ON audit_logs;
CREATE POLICY audit_select_nutri ON audit_logs FOR SELECT TO authenticated
    USING (app_is_nutritionist());
-- Запись в audit_logs — только service_role (серверный API).

-- =============================================
-- ПРОВЕРКА
-- =============================================
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
-- SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname='public' ORDER BY tablename;

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ RLS включён на всех клиентских таблицах
-- ✅ client видит/правит только свои данные; статус/оплату/роль менять не может
-- ✅ nutritionist — полный доступ; observer — чтение (через app_can_read_client)
-- ✅ service_role (агент/n8n/серверный API) RLS обходит — серверные пути работают
-- ⚠️ После применения проверить: вход клиентом не должен видеть чужие строки;
--    смена своего статуса из браузера должна отклоняться.
-- =============================================
