-- =============================================
-- МИГРАЦИЯ v1.3 - ШАГ 3: БЛОК 2 (КОММУНИКАЦИЯ)
-- =============================================

-- 5. ИСТОРИЯ ДИАЛОГОВ
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

CREATE INDEX idx_conversations_client_timestamp ON conversations(client_id, message_timestamp DESC);
CREATE INDEX idx_conversations_thread ON conversations(thread_id);

COMMENT ON TABLE conversations IS 'История диалогов (telegram/web)';

-- 6. ЖУРНАЛ СОБЫТИЙ
CREATE TABLE IF NOT EXISTS client_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    event_date TIMESTAMP DEFAULT NOW(),
    payload_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_client_events_client ON client_events(client_id, event_date DESC);
CREATE INDEX idx_client_events_severity ON client_events(severity) WHERE severity IS NOT NULL;

COMMENT ON TABLE client_events IS 'Журнал событий клиента с severity';

-- ШАГ 3 ЗАВЕРШЁН
SELECT 'ШАГ 3: Блок 2 создан' AS status;
