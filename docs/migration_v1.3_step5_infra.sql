-- =============================================
-- МИГРАЦИЯ v1.3 - ШАГ 5: БЛОК 4 (ИНФРАСТРУКТУРА)
-- =============================================

-- 9. РАСПИСАНИЕ УВЕДОМЛЕНИЙ
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

-- 10. АУДИТ
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

CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id, action_timestamp DESC);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_type, actor_id, action_timestamp DESC);

COMMENT ON TABLE audit_logs IS 'Полный аудит всех действий в системе';

-- 11. СИСТЕМНЫЕ НАСТРОЙКИ
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT NOW()
);

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

-- ШАГ 5 ЗАВЕРШЁН
SELECT 'ШАГ 5: Блок 4 создан' AS status;
