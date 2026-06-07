-- =============================================
-- СХЕМА БАЗЫ ДАННЫХ — АГЕНТ НУТРИЦИОЛОГА v1.2
-- Последнее обновление: 07 июнь 2026
-- Выполнено в Supabase SQL Editor
-- Порядок: по зависимостям (FK)
-- =============================================


-- ── БЛОК 1: ПОЛЬЗОВАТЕЛИ И ПРОФИЛИ ───────────

-- Пользователи системы (единый источник для Auth)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id UUID UNIQUE,               -- FK → Supabase Auth
    role TEXT NOT NULL CHECK (role IN ('nutritionist', 'client')),
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Профили клиентов
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    telegram_id BIGINT UNIQUE,
    language TEXT DEFAULT 'ru' CHECK (language IN ('ru', 'en', 'ar', 'ur')),
    timezone TEXT DEFAULT 'Asia/Dubai',

    -- Статусы
    client_status TEXT NOT NULL DEFAULT 'lead'
        CHECK (client_status IN ('lead', 'onboarding', 'active', 'paused', 'completed', 'archived')),
    payment_status TEXT NOT NULL DEFAULT 'inactive'
        CHECK (payment_status IN ('active', 'inactive')),
    access_status TEXT NOT NULL DEFAULT 'active'
        CHECK (access_status IN ('active', 'frozen')),

    -- Заметки нутрициолога
    nutritionist_notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Медицинские профили клиентов
CREATE TABLE client_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL UNIQUE REFERENCES clients(id) ON DELETE CASCADE,

    -- Физические данные
    birth_date DATE,
    gender TEXT CHECK (gender IN ('male', 'female')),
    height_cm INTEGER,
    initial_weight_kg DECIMAL(5,2),
    target_weight_kg DECIMAL(5,2),

    -- Образ жизни
    activity_level TEXT CHECK (activity_level IN ('low', 'medium', 'high')),
    goals TEXT,

    -- Ограничения
    allergies TEXT[],
    food_restrictions TEXT[],
    chronic_conditions TEXT[],

    -- Индивидуальные пороги алертов (переопределяют system_settings)
    alert_weight_increase_kg DECIMAL(4,2),  -- порог роста веса за день
    alert_no_response_hours INTEGER,         -- часы без ответа

    onboarding_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Планы здорового образа жизни (wellness coaching)
CREATE TABLE wellness_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Версионирование
    version INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'nutritionist'
        CHECK (created_by IN ('nutritionist')),

    -- Даты действия
    effective_from DATE NOT NULL,
    effective_to DATE,                 -- NULL = действует сейчас
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Содержимое по разделам
    sleep JSONB,                       -- режим сна
    physical_activity JSONB,           -- физические нагрузки
    recovery JSONB,                    -- восстановление
    stress_management JSONB,           -- управление стрессом

    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_wellness_client ON wellness_plans(client_id);
CREATE INDEX idx_wellness_active ON wellness_plans(client_id, is_active)
    WHERE is_active = true;


-- ── БЛОК 2: КОММУНИКАЦИЯ ─────────────────────

-- История разговоров
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    channel TEXT NOT NULL CHECK (channel IN ('telegram', 'web')),
    conversation_type TEXT NOT NULL
        CHECK (conversation_type IN ('client_dialog', 'nutritionist_note', 'system')),
    role TEXT NOT NULL CHECK (role IN ('client', 'nutritionist', 'agent')),
    thread_id UUID,                    -- группировка по сессии

    message_text TEXT NOT NULL,
    metadata_json JSONB,
    -- {"model": "groq", "tokens": 800, "alert": false, "sentiment": "neutral"}

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conv_client ON conversations(client_id, created_at DESC);
CREATE INDEX idx_conv_thread ON conversations(thread_id);

-- Журнал событий клиента
CREATE TABLE client_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    event_type TEXT NOT NULL,
    -- weight_logged, bad_wellbeing, food_incompatible, food_forbidden,
    -- no_response, document_uploaded, plan_updated, task_completed,
    -- calories_logged, alert_triggered, payment_changed, status_changed

    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),

    event_date TIMESTAMPTZ DEFAULT NOW(),
    payload_json JSONB,
    -- bad_wellbeing: {"answer": "нехорошо", "reason": "болит голова", "checkin_time": "08:15"}
    -- weight_logged: {"weight_kg": 78.5, "previous_kg": 77.2, "delta_kg": 1.3}
    -- food_forbidden: {"product": "глютен", "detected_in": "овсянка"}

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_client ON client_events(client_id, event_date DESC);
CREATE INDEX idx_events_severity ON client_events(severity, event_date DESC)
    WHERE severity IN ('high', 'critical');


-- ── БЛОК 3: РАБОЧИЕ ИНСТРУМЕНТЫ ──────────────

-- Планы питания (с версионированием)
CREATE TABLE nutrition_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Версионирование
    version INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    created_by TEXT NOT NULL CHECK (created_by IN ('nutritionist')),

    -- Даты действия
    effective_from DATE NOT NULL,
    effective_to DATE,                 -- NULL = действует сейчас
    is_active BOOLEAN NOT NULL DEFAULT true,

    -- Содержимое
    plan_json JSONB NOT NULL,          -- рацион, КБЖУ, приёмы пищи
    supplements_json JSONB,            -- БАДы (nullable)

    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Только один активный план на клиента
    CONSTRAINT one_active_plan_per_client
        EXCLUDE USING btree (client_id WITH =)
        WHERE (is_active = true)
);

CREATE INDEX idx_nutrition_plans_client ON nutrition_plans(client_id);
CREATE INDEX idx_nutrition_plans_active ON nutrition_plans(client_id, is_active)
    WHERE is_active = true;

-- Триггер: автоинкремент версии по клиенту
CREATE OR REPLACE FUNCTION set_plan_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.version := COALESCE(
        (SELECT MAX(version) FROM nutrition_plans WHERE client_id = NEW.client_id),
        0
    ) + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
   SECURITY INVOKER
   SET search_path = public;

CREATE TRIGGER trg_plan_version
    BEFORE INSERT ON nutrition_plans
    FOR EACH ROW EXECUTE FUNCTION set_plan_version();

-- Триггер: деактивация старого плана при создании нового
CREATE OR REPLACE FUNCTION deactivate_old_plans()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_active = true THEN
        UPDATE nutrition_plans
        SET
            is_active = false,
            effective_to = NEW.effective_from - INTERVAL '1 day'
        WHERE
            client_id = NEW.client_id
            AND id != NEW.id
            AND is_active = true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
   SECURITY INVOKER
   SET search_path = public;

CREATE TRIGGER trg_deactivate_old_plans
    AFTER INSERT ON nutrition_plans
    FOR EACH ROW EXECUTE FUNCTION deactivate_old_plans();

-- Задачи клиентам от нутрициолога
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    plan_id UUID REFERENCES nutrition_plans(id) ON DELETE SET NULL,

    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMPTZ,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'overdue', 'cancelled')),
    completed_at TIMESTAMPTZ,

    created_by TEXT NOT NULL DEFAULT 'nutritionist'
        CHECK (created_by IN ('nutritionist')),

    completion_payload JSONB,          -- фото, текст, замер от клиента

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tasks_client ON tasks(client_id);
CREATE INDEX idx_tasks_pending ON tasks(client_id, status)
    WHERE status = 'pending';
CREATE INDEX idx_tasks_due ON tasks(due_date)
    WHERE status = 'pending';


-- ── БЛОК 4: ИНФРАСТРУКТУРА ───────────────────

-- Персональное расписание уведомлений
CREATE TABLE notification_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    notification_type TEXT NOT NULL
        CHECK (notification_type IN ('morning', 'evening', 'reminder')),
    scheduled_time TIME NOT NULL,
    timezone TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (client_id, notification_type)
);

CREATE INDEX idx_notif_active ON notification_schedule(notification_type, scheduled_time)
    WHERE is_active = true;

-- Аудит всех действий
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    actor_type TEXT NOT NULL
        CHECK (actor_type IN ('nutritionist', 'client', 'system')),
    actor_id UUID,

    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,

    old_value JSONB,
    new_value JSONB,

    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_actor ON audit_logs(actor_type, actor_id);
CREATE INDEX idx_audit_time ON audit_logs(timestamp DESC);

-- Системные настройки
CREATE TABLE system_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key TEXT UNIQUE NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    updated_by UUID,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO system_settings (key, value, description) VALUES

('alert_thresholds', '{
    "weight_increase_kg": 0.8,
    "no_response_hours": 4,
    "food_incompatible_check": true,
    "bad_wellbeing_check": true
}', 'Пороги алертов — настраиваются нутрициологом'),

('nutritionist_telegram_id', '{
    "chat_id": ""
}', 'Telegram chat_id нутрициолога для алертов'),

('feature_flags', '{
    "voice_enabled": false,
    "vision_enabled": true,
    "knowledge_base_enabled": true
}', 'Включение/выключение функций (voice → v1.1)'),

('default_notification_times', '{
    "morning": "08:00",
    "evening": "21:00"
}', 'Время уведомлений по умолчанию при регистрации'),

('trial_settings', '{
    "trial_days": 7,
    "default_timezone": "Asia/Dubai",
    "default_language": "ru"
}', 'Настройки для новых клиентов');


-- ── БЛОК 5: ДОКУМЕНТЫ ────────────────────────
-- document_metadata — следующий этап
-- pgvector (knowledge_base, client_documents) — следующий этап


-- ── VIEW: РЕЕСТР КЛИЕНТОВ ────────────────────
CREATE VIEW client_registry_view AS
SELECT
    c.id,
    c.name,
    c.telegram_id,
    c.language,
    c.timezone,
    c.client_status,
    c.payment_status,
    c.access_status,
    cp.goals,
    cp.initial_weight_kg,
    cp.target_weight_kg,
    np.version        AS plan_version,
    np.title          AS plan_title,
    np.effective_from AS plan_from,
    wp.title          AS wellness_plan_title,
    c.created_at,
    last_event.event_date AS last_contact,
    active_tasks.cnt      AS open_tasks
FROM clients c
LEFT JOIN client_profiles cp
    ON c.id = cp.client_id
LEFT JOIN nutrition_plans np
    ON c.id = np.client_id AND np.is_active = true
LEFT JOIN wellness_plans wp
    ON c.id = wp.client_id AND wp.is_active = true
LEFT JOIN (
    SELECT client_id, MAX(event_date) AS event_date
    FROM client_events
    GROUP BY client_id
) last_event ON c.id = last_event.client_id
LEFT JOIN (
    SELECT client_id, COUNT(*) AS cnt
    FROM tasks
    WHERE status = 'pending'
    GROUP BY client_id
) active_tasks ON c.id = active_tasks.client_id;
