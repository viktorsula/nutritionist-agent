-- =============================================
-- МИГРАЦИЯ v1.3 - ШАГ 2: БЛОК 1 (ПОЛЬЗОВАТЕЛИ)
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

-- 2. ПРОФИЛИ КЛИЕНТОВ
CREATE TABLE IF NOT EXISTS clients (
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

-- 3. МЕДИЦИНСКИЕ ПРОФИЛИ
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

-- 4. ПЛАНЫ WELLNESS
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

-- ШАГ 2 ЗАВЕРШЁН
SELECT 'ШАГ 2: Блок 1 создан' AS status;
