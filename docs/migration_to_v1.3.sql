-- =============================================
-- МИГРАЦИЯ БАЗЫ ДАННЫХ: v1.2 → v1.3
-- Агент-ассистент нутрициолога
-- Дата: Июнь 2026
-- =============================================
-- ИНСТРУКЦИЯ:
-- 1. Скопировать весь файл
-- 2. Открыть Supabase Dashboard → SQL Editor
-- 3. Вставить и выполнить
-- 4. Проверить результат (0 errors)
-- =============================================

-- ШАГ 1: УДАЛЕНИЕ СТАРЫХ ТАБЛИЦ
-- =============================================

-- Удаляем таблицы, которые больше не нужны
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS nutrition_diary CASCADE;
DROP TABLE IF EXISTS measurements CASCADE;
DROP TABLE IF EXISTS nutritionist_tasks CASCADE;

-- =============================================
-- ШАГ 2: ВКЛЮЧЕНИЕ PGVECTOR
-- =============================================

CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================
-- ШАГ 3: СОЗДАНИЕ НОВЫХ ТАБЛИЦ (БЛОК 1)
-- =============================================

-- 1. ПОЛЬЗОВАТЕЛИ СИСТЕМЫ
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id UUID UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('nutritionist', 'client')),
    email TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE users IS 'Пользователи системы, интеграция с Supabase Auth';

-- =============================================
-- ШАГ 4: ИЗМЕНЕНИЕ ТАБЛИЦЫ CLIENTS
-- =============================================

-- Удаляем старую таблицу clients полностью (данных нет)
DROP TABLE IF EXISTS clients CASCADE;

-- Создаём новую таблицу clients с правильной структурой
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    telegram_id BIGINT UNIQUE,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    language TEXT DEFAULT 'ru' CHECK (language IN ('ru', 'en', 'ar', 'ur')),
    timezone TEXT DEFAULT 'Asia/Dubai',
    payment_status TEXT DEFAULT 'trial' CHECK (payment_status IN ('trial', 'active', 'inactive')),
    access_status TEXT DEFAULT 'active' CHECK (access_status IN ('active', 'frozen')),
    client_status TEXT DEFAULT 'lead' CHECK (client_status IN ('lead', 'onboarding', 'active', 'paused', 'completed', 'archived')),
    nutritionist_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE clients IS 'Профили клиентов: идентификация, статусы, контакты';

-- =============================================
-- ШАГ 5: СОЗДАНИЕ ТАБЛИЦЫ CLIENT_PROFILES
-- =============================================

CREATE TABLE IF NOT EXISTS client_profiles (
    client_id UUID PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
    birth_date DATE,
    weight DECIMAL(5,2),
    height INTEGER,
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    goals TEXT,
    restrictions TEXT[],
    allergies TEXT[],
    chronic_conditions TEXT[],
    activity_level TEXT CHECK (activity_level IN ('low', 'medium', 'high')),
    target_weight DECIMAL(5,2),
    onboarding_completed_at TIMESTAMP,
    custom_alert_thresholds JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE client_profiles IS 'Медицинские данные, цели, индивидуальные пороги алертов';

-- =============================================
-- ШАГ 6: СОЗДАНИЕ ТАБЛИЦЫ WELLNESS_PLANS
-- =============================================

CREATE TABLE IF NOT EXISTS wellness_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    sleep_target TEXT,
    activity_target TEXT,
    recovery TEXT,
    stress_management TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE wellness_plans IS 'Планы ЗОЖ: сон, активность, восстановление, стресс';

-- =============================================
-- ШАГ 7: СОЗДАНИЕ ТАБЛИЦЫ CONVERSATIONS (БЛОК 2)
-- =============================================

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    message_timestamp TIMESTAMP DEFAULT NOW(),
    channel TEXT CHECK (channel IN ('telegram', 'web')),
    conversation_type TEXT CHECK (conversation_type IN ('client_dialog', 'nutritionist_note', 'system')),
    role TEXT CHECK (role IN ('client', 'nutritionist', 'agent')),
    thread_id TEXT,
    message_text TEXT NOT NULL,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_client_timestamp ON conversations(client_id, message_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_thread ON conversations(thread_id);

COMMENT ON TABLE conversations IS 'История диалогов (telegram/web)';

-- =============================================
-- ШАГ 8: СОЗДАНИЕ ТАБЛИЦЫ CLIENT_EVENTS
-- =============================================

CREATE TABLE IF NOT EXISTS client_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    event_date TIMESTAMP DEFAULT NOW(),
    payload_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_events_client ON client_events(client_id, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_client_events_severity ON client_events(severity) WHERE severity IS NOT NULL;

COMMENT ON TABLE client_events IS 'Журнал событий клиента с severity';

-- =============================================
-- ШАГ 9: ИЗМЕНЕНИЕ ТАБЛИЦЫ NUTRITION_PLANS (БЛОК 3)
-- =============================================

-- Удаляем старую таблицу nutrition_plans полностью (данных нет)
DROP TABLE IF EXISTS nutrition_plans CASCADE;

-- Создаём новую таблицу nutrition_plans с правильной структурой
CREATE TABLE nutrition_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    created_by TEXT NOT NULL CHECK (created_by IN ('nutritionist', 'agent')),
    effective_from DATE NOT NULL,
    effective_to DATE,
    is_active BOOLEAN DEFAULT true,
    plan_json JSONB DEFAULT '{}',
    supplements_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_active_plan_per_client
        EXCLUDE USING gist (client_id WITH =, tsrange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]') WITH &&)
        WHERE (is_active = true)
);

CREATE INDEX IF NOT EXISTS idx_nutrition_plans_active ON nutrition_plans(client_id, is_active) WHERE is_active = true;

COMMENT ON TABLE nutrition_plans IS 'Планы питания + БАДы, версионирование';

-- =============================================
-- ШАГ 10: СОЗДАНИЕ ТРИГГЕРОВ ДЛЯ NUTRITION_PLANS
-- =============================================

-- Триггер: автоинкремент версии плана по клиенту
CREATE OR REPLACE FUNCTION increment_plan_version()
RETURNS TRIGGER
SECURITY INVOKER
SET search_path = public, pg_temp
LANGUAGE plpgsql AS $$
BEGIN
    SELECT COALESCE(MAX(version), 0) + 1 INTO NEW.version
    FROM nutrition_plans
    WHERE client_id = NEW.client_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_plan_version
    BEFORE INSERT ON nutrition_plans
    FOR EACH ROW
    EXECUTE FUNCTION increment_plan_version();

-- Триггер: деактивация старого активного плана при создании нового
CREATE OR REPLACE FUNCTION deactivate_old_plans()
RETURNS TRIGGER
SECURITY INVOKER
SET search_path = public, pg_temp
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.is_active = true THEN
        UPDATE nutrition_plans
        SET is_active = false, effective_to = NEW.effective_from, updated_at = NOW()
        WHERE client_id = NEW.client_id
          AND id != NEW.id
          AND is_active = true;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deactivate_old_plans
    AFTER INSERT ON nutrition_plans
    FOR EACH ROW
    WHEN (NEW.is_active = true)
    EXECUTE FUNCTION deactivate_old_plans();

-- =============================================
-- ШАГ 11: СОЗДАНИЕ ТАБЛИЦЫ TASKS
-- =============================================

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    plan_id UUID REFERENCES nutrition_plans(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMP,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'overdue', 'cancelled')),
    created_by TEXT NOT NULL CHECK (created_by IN ('nutritionist', 'agent')),
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_client_status ON tasks(client_id, status) WHERE status = 'pending';

COMMENT ON TABLE tasks IS 'Задачи клиентам, created_by=nutritionist only';

-- =============================================
-- ШАГ 12: СОЗДАНИЕ ТАБЛИЦ БЛОКА 4
-- =============================================

-- NOTIFICATION_SCHEDULE
CREATE TABLE IF NOT EXISTS notification_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL CHECK (notification_type IN ('morning', 'evening', 'reminder', 'custom')),
    scheduled_time TIME NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Dubai',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_notification_per_client_type UNIQUE (client_id, notification_type)
);

COMMENT ON TABLE notification_schedule IS 'Персональное расписание уведомлений (timezone-aware)';

-- AUDIT_LOGS
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('nutritionist', 'client', 'agent', 'system')),
    actor_id UUID,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('client', 'plan', 'task', 'schedule', 'settings', 'profile')),
    entity_id UUID,
    old_value JSONB,
    new_value JSONB,
    action_timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id, action_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_type, actor_id, action_timestamp DESC);

COMMENT ON TABLE audit_logs IS 'Полный аудит всех действий в системе';

-- SYSTEM_SETTINGS (изменяем структуру)
DROP TABLE IF EXISTS system_settings CASCADE;

CREATE TABLE system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Начальные настройки
INSERT INTO system_settings (key, value, description) VALUES
('alert_thresholds', '{
    "glucose_critical": 15,
    "glucose_high": 10,
    "weight_increase_kg": 2,
    "no_response_hours": 48
}'::jsonb, 'Пороги алертов (глобальные)'),
('default_language', '"ru"'::jsonb, 'Язык по умолчанию'),
('default_timezone', '"Asia/Dubai"'::jsonb, 'Часовой пояс по умолчанию'),
('trial_days', '7'::jsonb, 'Дней бесплатного триала');

COMMENT ON TABLE system_settings IS 'Системные настройки и пороги алертов';

-- =============================================
-- ШАГ 13: СОЗДАНИЕ ТАБЛИЦ БЛОКА 5 (PGVECTOR)
-- =============================================

-- DOCUMENT_METADATA (уже должна существовать, проверяем)
CREATE TABLE IF NOT EXISTS document_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    external_id TEXT,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    document_type TEXT CHECK (document_type IN ('knowledge_base', 'client_document', 'report', 'other')) DEFAULT 'other',
    title TEXT,
    description TEXT,
    mime_type TEXT,
    storage_url TEXT,
    file_name TEXT,
    file_size_bytes BIGINT,
    extracted_text TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE document_metadata IS 'Метаданные документов (источники, тип, привязка)';

-- KNOWLEDGE_BASE (уже должна существовать, проверяем)
CREATE TABLE IF NOT EXISTS knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    source TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_embedding ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON TABLE knowledge_base IS 'База знаний нутрициолога (pgvector)';

-- CLIENT_DOCUMENTS (уже должна существовать, проверяем)
CREATE TABLE IF NOT EXISTS client_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_documents_embedding ON client_documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON TABLE client_documents IS 'Документы клиентов (pgvector)';

-- =============================================
-- ШАГ 14: СОЗДАНИЕ VIEW
-- =============================================

CREATE OR REPLACE VIEW client_registry_view AS
SELECT
    c.id,
    c.name,
    c.email,
    c.phone,
    c.telegram_id,
    c.language,
    c.timezone,
    c.client_status,
    c.payment_status,
    c.access_status,
    c.nutritionist_notes,
    cp.goals,
    cp.weight,
    cp.target_weight,
    cp.onboarding_completed_at,
    np.version AS plan_version,
    np.title AS plan_title,
    np.effective_from AS plan_from,
    np.effective_to AS plan_to,
    c.created_at AS registered_at,
    last_event.event_date AS last_contact,
    active_tasks.count AS open_tasks
FROM clients c
LEFT JOIN client_profiles cp ON c.id = cp.client_id
LEFT JOIN nutrition_plans np ON c.id = np.client_id AND np.is_active = true
LEFT JOIN (
    SELECT client_id, MAX(event_date) AS event_date
    FROM client_events
    GROUP BY client_id
) last_event ON c.id = last_event.client_id
LEFT JOIN (
    SELECT client_id, COUNT(*) AS count
    FROM tasks
    WHERE status = 'pending'
    GROUP BY client_id
) active_tasks ON c.id = active_tasks.client_id;

-- =============================================
-- ЗАВЕРШЕНИЕ МИГРАЦИИ
-- =============================================

-- Проверка: вывести список всех таблиц
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Ожидаемый результат:
-- 1. users
-- 2. clients
-- 3. client_profiles
-- 4. wellness_plans
-- 5. conversations
-- 6. client_events
-- 7. nutrition_plans
-- 8. tasks
-- 9. notification_schedule
-- 10. audit_logs
-- 11. system_settings
-- 12. document_metadata
-- 13. knowledge_base
-- 14. client_documents
-- ИТОГО: 14 таблиц + 1 VIEW (client_registry_view)

-- =============================================
-- МИГРАЦИЯ ЗАВЕРШЕНА
-- =============================================
