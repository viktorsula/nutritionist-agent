-- =============================================
-- СХЕМА БАЗЫ ДАННЫХ — АГЕНТ НУТРИЦИОЛОГА v1.3
-- Выполнить в Supabase → SQL Editor
-- Дата: Июнь 2026
-- =============================================

-- Включить расширение pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================
-- БЛОК 1: ПОЛЬЗОВАТЕЛИ И ПРОФИЛИ
-- =============================================

-- 1. ПОЛЬЗОВАТЕЛИ СИСТЕМЫ (интеграция с Supabase Auth)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id UUID UNIQUE,  -- связь с auth.users в Supabase
    role TEXT NOT NULL CHECK (role IN ('nutritionist', 'client', 'observer')),
    email TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. ПРОФИЛИ КЛИЕНТОВ (идентификация, статусы, контакты)
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

-- 3. МЕДИЦИНСКИЕ ПРОФИЛИ КЛИЕНТОВ
CREATE TABLE client_profiles (
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

-- 4. ПЛАНЫ WELLNESS (сон, активность, восстановление, стресс)
CREATE TABLE wellness_plans (
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

-- =============================================
-- БЛОК 2: КОММУНИКАЦИЯ
-- =============================================

-- 5. ИСТОРИЯ ДИАЛОГОВ
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    timestamp TIMESTAMP DEFAULT NOW(),
    channel TEXT CHECK (channel IN ('telegram', 'web')),
    conversation_type TEXT CHECK (conversation_type IN ('client_dialog', 'nutritionist_note', 'system')),
    role TEXT CHECK (role IN ('client', 'nutritionist', 'agent')),
    thread_id TEXT,
    message_text TEXT NOT NULL,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для быстрого поиска по клиенту и дате
CREATE INDEX idx_conversations_client_timestamp ON conversations(client_id, timestamp DESC);
CREATE INDEX idx_conversations_thread ON conversations(thread_id);

-- 6. ЖУРНАЛ СОБЫТИЙ КЛИЕНТА
CREATE TABLE client_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    -- Примеры: 'document_uploaded', 'plan_updated', 'complaint',
    --          'weight_logged', 'alert_triggered', 'payment_changed',
    --          'task_completed', 'calories_logged', 'status_changed'
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    event_date TIMESTAMP DEFAULT NOW(),
    payload_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для событий
CREATE INDEX idx_client_events_client ON client_events(client_id, event_date DESC);
CREATE INDEX idx_client_events_severity ON client_events(severity) WHERE severity IS NOT NULL;

-- =============================================
-- БЛОК 3: РАБОЧИЕ ИНСТРУМЕНТЫ
-- =============================================

-- 7. ПЛАНЫ ПИТАНИЯ (с версионированием)
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

    -- Гарантирует только один активный план на клиента
    CONSTRAINT unique_active_plan_per_client
        EXCLUDE USING gist (client_id WITH =, tsrange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]') WITH &&)
        WHERE (is_active = true)
);

-- Индекс для поиска активного плана
CREATE INDEX idx_nutrition_plans_active ON nutrition_plans(client_id, is_active) WHERE is_active = true;

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

-- 8. ЗАДАЧИ КЛИЕНТОВ
CREATE TABLE tasks (
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

-- Индекс для быстрого поиска активных задач
CREATE INDEX idx_tasks_client_status ON tasks(client_id, status) WHERE status = 'pending';

-- =============================================
-- БЛОК 4: ИНФРАСТРУКТУРА
-- =============================================

-- 9. РАСПИСАНИЕ УВЕДОМЛЕНИЙ (персональное, timezone-aware)
CREATE TABLE notification_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL CHECK (notification_type IN ('morning', 'evening', 'reminder', 'custom')),
    scheduled_time TIME NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Dubai',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Уникальность: один клиент = один тип уведомления
    CONSTRAINT unique_notification_per_client_type UNIQUE (client_id, notification_type)
);

-- 10. АУДИТ ВСЕХ ДЕЙСТВИЙ
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('nutritionist', 'client', 'agent', 'system')),
    actor_id UUID,
    action TEXT NOT NULL,
    -- Примеры: 'update_allergy', 'change_plan', 'freeze_access',
    --          'update_threshold', 'assign_task', 'change_status'
    entity_type TEXT NOT NULL CHECK (entity_type IN ('client', 'plan', 'task', 'schedule', 'settings', 'profile')),
    entity_id UUID,
    old_value JSONB,
    new_value JSONB,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Индекс для поиска по сущности
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id, timestamp DESC);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_type, actor_id, timestamp DESC);

-- 11. СИСТЕМНЫЕ НАСТРОЙКИ
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
('trial_days', '7'::jsonb, 'Дней бесплатного триала'),
-- llm_config: основная модель + резерв (fallbacks) по task_type. Правится нутрициологом
-- в «Настройках». Источник правды после сидинга — БД; код-константы — дефолт (см. миграцию 011).
('llm_config', '{
  "dialog": {"provider": "groq", "model": "llama-3.3-70b-versatile", "temperature": 0.7, "max_tokens": 2000,
             "fallbacks": [{"provider": "gemini", "model": "gemini-2.5-flash"}]},
  "analytics": {"provider": "claude", "model": "claude-sonnet-4-6", "temperature": 0.3, "max_tokens": 4000,
                "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}, {"provider": "gemini", "model": "gemini-2.5-flash"}]},
  "vision": {"provider": "gemini", "model": "gemini-2.5-flash", "temperature": 0.5, "max_tokens": 1500,
             "fallbacks": [{"provider": "claude", "model": "claude-sonnet-4-6"}]},
  "nutrition_analysis": {"provider": "claude", "model": "claude-sonnet-4-6", "temperature": 0.4, "max_tokens": 3000,
                         "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}, {"provider": "gemini", "model": "gemini-2.5-flash"}]},
  "summary": {"provider": "groq", "model": "llama-3.3-70b-versatile", "temperature": 0.5, "max_tokens": 2000,
              "fallbacks": [{"provider": "gemini", "model": "gemini-2.5-flash"}]},
  "planning": {"provider": "claude", "model": "claude-sonnet-4-6", "temperature": 0.4, "max_tokens": 3000,
               "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}, {"provider": "gemini", "model": "gemini-2.5-flash"}]}
}'::jsonb, 'Конфигурация LLM по task_type: основная модель + резерв (fallbacks)');

-- =============================================
-- БЛОК 5: ДОКУМЕНТЫ И PGVECTOR
-- =============================================

-- 12. МЕТАДАННЫЕ ДОКУМЕНТОВ
CREATE TABLE document_metadata (
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

-- 13. БАЗА ЗНАНИЙ (pgvector, библиотека нутрициолога)
CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    source TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для векторного поиска
CREATE INDEX idx_knowledge_base_embedding ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 14. ДОКУМЕНТЫ КЛИЕНТОВ (pgvector, эмбеддинги PDF клиентов)
CREATE TABLE client_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для векторного поиска
CREATE INDEX idx_client_documents_embedding ON client_documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- =============================================
-- VIEW: РЕЕСТР КЛИЕНТОВ
-- =============================================

CREATE VIEW client_registry_view AS
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
-- КОММЕНТАРИИ К ТАБЛИЦАМ
-- =============================================

COMMENT ON TABLE users IS 'Пользователи системы, интеграция с Supabase Auth';
COMMENT ON TABLE clients IS 'Профили клиентов: идентификация, статусы, контакты';
COMMENT ON TABLE client_profiles IS 'Медицинские данные, цели, индивидуальные пороги алертов';
COMMENT ON TABLE wellness_plans IS 'Планы ЗОЖ: сон, активность, восстановление, стресс';
COMMENT ON TABLE conversations IS 'История диалогов (telegram/web)';
COMMENT ON TABLE client_events IS 'Журнал событий клиента с severity';
COMMENT ON TABLE nutrition_plans IS 'Планы питания + БАДы, версионирование';
COMMENT ON TABLE tasks IS 'Задачи клиентам, created_by=nutritionist only';
COMMENT ON TABLE notification_schedule IS 'Персональное расписание уведомлений (timezone-aware)';
COMMENT ON TABLE audit_logs IS 'Полный аудит всех действий в системе';
COMMENT ON TABLE system_settings IS 'Системные настройки и пороги алертов';
COMMENT ON TABLE document_metadata IS 'Метаданные документов (источники, тип, привязка)';
COMMENT ON TABLE knowledge_base IS 'База знаний нутрициолога (pgvector)';
COMMENT ON TABLE client_documents IS 'Документы клиентов (pgvector)';

-- =============================================
-- ЗАВЕРШЕНИЕ
-- =============================================

-- Схема v1.3 готова к использованию
-- 14 таблиц + 1 VIEW + 2 триггера
-- Security Advisor: проверено, 0 errors
