-- =============================================
-- СХЕМА БАЗЫ ДАННЫХ — АГЕНТ НУТРИЦИОЛОГА
-- Выполнить в Supabase → SQL Editor
-- =============================================

CREATE EXTENSION IF NOT EXISTS vector;

-- 1. КЛИЕНТЫ
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    birth_date DATE,
    gender TEXT CHECK (gender IN ('male', 'female')),
    height_cm INTEGER,
    weight_kg DECIMAL(5,2),
    target_weight_kg DECIMAL(5,2),
    activity_level TEXT CHECK (activity_level IN ('low', 'medium', 'high')),
    allergies TEXT[],
    medical_conditions TEXT[],
    medications TEXT[],
    subscription_status TEXT DEFAULT 'trial' CHECK (subscription_status IN ('trial', 'active', 'paused', 'expired')),
    subscription_end_date TIMESTAMP,
    notifications_enabled BOOLEAN DEFAULT true,
    notification_time TIME DEFAULT '09:00',
    timezone TEXT DEFAULT 'Asia/Dubai',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. СЕССИИ (история диалогов)
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    session_type TEXT CHECK (session_type IN ('daily_checkin', 'meal_log', 'question', 'analysis'))
);

-- 3. СООБЩЕНИЯ
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    role TEXT CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'text' CHECK (message_type IN ('text', 'voice', 'image', 'document')),
    media_url TEXT,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. ДНЕВНИК ПИТАНИЯ
CREATE TABLE nutrition_diary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    logged_at TIMESTAMP DEFAULT NOW(),
    meal_type TEXT CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    description TEXT,
    photo_url TEXT,
    calories INTEGER,
    protein_g DECIMAL(6,2),
    fat_g DECIMAL(6,2),
    carbs_g DECIMAL(6,2),
    water_ml INTEGER,
    ai_analysis TEXT
);

-- 5. ЗАМЕРЫ И ПОКАЗАТЕЛИ
CREATE TABLE measurements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    measured_at TIMESTAMP DEFAULT NOW(),
    weight_kg DECIMAL(5,2),
    waist_cm DECIMAL(5,2),
    hips_cm DECIMAL(5,2),
    chest_cm DECIMAL(5,2),
    blood_sugar DECIMAL(5,2),
    blood_pressure_sys INTEGER,
    blood_pressure_dia INTEGER,
    energy_level INTEGER CHECK (energy_level BETWEEN 1 AND 10),
    sleep_hours DECIMAL(4,2),
    notes TEXT
);

-- 6. ПЛАНЫ ПИТАНИЯ
CREATE TABLE nutrition_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    created_by_nutritionist BOOLEAN DEFAULT true,
    title TEXT NOT NULL,
    description TEXT,
    daily_calories INTEGER,
    protein_percent INTEGER,
    fat_percent INTEGER,
    carbs_percent INTEGER,
    restrictions TEXT[],
    plan_content JSONB,
    valid_from DATE,
    valid_until DATE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 7. ЗАДАЧИ НУТРИЦИОЛОГА
CREATE TABLE nutritionist_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    task_type TEXT CHECK (task_type IN ('review', 'call', 'plan_update', 'analysis', 'alert')),
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMP,
    completed BOOLEAN DEFAULT false,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 8. СИСТЕМНЫЕ НАСТРОЙКИ
CREATE TABLE system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Начальные настройки
INSERT INTO system_settings (key, value, description) VALUES
('max_blood_sugar', '11.0', 'Критический уровень сахара ммоль/л'),
('min_blood_sugar', '3.5', 'Минимальный уровень сахара ммоль/л'),
('trial_days', '7', 'Дней бесплатного периода'),
('default_timezone', 'Asia/Dubai', 'Временная зона по умолчанию');

-- 9. ДОКУМЕНТЫ И VECTOR
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
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    source TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE client_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    document_id UUID REFERENCES document_metadata(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_client_documents_embedding ON client_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
