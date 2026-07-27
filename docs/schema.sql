-- =============================================
-- СХЕМА БАЗЫ ДАННЫХ — АГЕНТ НУТРИЦИОЛОГА v1.6
-- Дата: 27 июля 2026
-- =============================================
-- Это КОНСОЛИДИРОВАННОЕ состояние схемы: базовая версия v1.3 + все миграции 001–021
-- (docs/migrations/). Файл описательный — на живой БД миграции уже применены, повторно
-- выполнять его целиком НЕ нужно; он нужен, чтобы видеть актуальную структуру целиком.
-- Реестр применённых миграций и verify-SQL для проверки дрейфа — docs/migrations/README.md.
--
-- До 27.07.2026 файл отставал с миграции 003 (P2-10): в нём не хватало 9 таблиц и ~12
-- колонок, а FK на clients(id) значились как ON DELETE CASCADE, хотя миграция 019 давно
-- перевела их в RESTRICT. Читавший файл получал неверную картину именно там, где она
-- важнее всего — в защите данных (LEGAL-3).
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
    paid_until DATE,                                   -- миграция 007: гейт доступа по оплате
    conversation_summary TEXT,                         -- миграция 009: rolling-summary диалога
    summary_message_count INTEGER NOT NULL DEFAULT 0,  -- миграция 009
    summary_updated_at TIMESTAMPTZ,                    -- миграция 009
    telegram_link_token TEXT,                          -- миграция 010: самопривязка Telegram
    telegram_link_token_expires_at TIMESTAMPTZ,        -- миграция 010
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. МЕДИЦИНСКИЕ ПРОФИЛИ КЛИЕНТОВ
CREATE TABLE client_profiles (
    client_id UUID PRIMARY KEY REFERENCES clients(id) ON DELETE RESTRICT,
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
    questionnaire_json JSONB DEFAULT '{}',       -- миграция 003: анкета онбординга (33 вопроса)
    questionnaire_summary TEXT,                  -- миграция 017: LLM-саммари анкеты для контекста
    tracked_lab_indicators JSONB DEFAULT '[]',   -- миграция 006: показатели анализов на графике
    controlled_metrics JSONB DEFAULT '[]',       -- миграция 014: показатели на контроле
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. ПЛАНЫ WELLNESS (сон, активность, восстановление, стресс)
CREATE TABLE wellness_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
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
-- БЛОК 6: ЗАМЕРЫ, АНАЛИЗЫ, ОТЧЁТЫ (миграции 003, 008, 016)
-- =============================================

-- 15. ЗАМЕРЫ ТЕЛА (динамика веса и объёмов)
CREATE TABLE measurements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    measured_at DATE NOT NULL DEFAULT CURRENT_DATE,
    weight DECIMAL(5,2),      -- кг
    neck DECIMAL(5,2),        -- см
    waist DECIMAL(5,2),       -- см
    hips DECIMAL(5,2),        -- см
    chest DECIMAL(5,2),       -- см (миграция 016)
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 16. РЕЗУЛЬТАТЫ АНАЛИЗОВ (числовые показатели во времени)
CREATE TABLE lab_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    measured_at DATE NOT NULL DEFAULT CURRENT_DATE,
    indicator TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source TEXT,              -- 'nutritionist' | 'client_pdf' | 'lab'
    document_id UUID REFERENCES document_metadata(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 17. ОТЧЁТЫ ПО КЛИЕНТУ (черновик → финал, с правками нутрициолога)
CREATE TABLE client_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final')),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- БЛОК 7: НАПОМИНАНИЯ И КОНТРОЛЬ ОТВЕТА (миграции 013, 015, 016, 021)
-- =============================================
-- Заменили прежний путь через notification_schedule (тот остался пустым, см. ниже).

-- 18. ШАБЛОН НАПОМИНАНИЯ (что и когда спрашивать у клиента)
CREATE TABLE reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    remind_at TIME NOT NULL,                 -- локальное время клиента
    recurrence TEXT NOT NULL DEFAULT 'daily'
        CHECK (recurrence IN ('once', 'daily', 'weekly')),
    weekday SMALLINT,                        -- weekly: 0=Пн … 6=Вс
    remind_date DATE,                        -- once: дата единственного срабатывания
    requires_response BOOLEAN NOT NULL DEFAULT false,
    expected_response TEXT,                  -- миграция 015: что закрывает срабатывание
    followup_after_hours INT,                -- миграция 016: per-item кадэнс догона
    max_followups INT,                       -- миграция 016
    response_deadline TIME,                  -- миграция 016: дедлайн отчёта (еда)
    active BOOLEAN NOT NULL DEFAULT true,
    created_by TEXT NOT NULL DEFAULT 'nutritionist',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 19. СРАБАТЫВАНИЯ НАПОМИНАНИЙ (дедуп отправки + жизненный цикл ответа)
CREATE TABLE reminder_occurrences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reminder_id UUID NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    due_date DATE NOT NULL,                  -- локальная дата клиента
    sent_at TIMESTAMP DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'sent'      -- миграция 015
        CHECK (status IN ('sent', 'answered', 'expired')),
    response_ref JSONB,                      -- миграция 015: чем закрыто
    followups_sent SMALLINT NOT NULL DEFAULT 0,   -- миграция 015
    next_followup_at TIMESTAMP,              -- миграция 015
    resolved_at TIMESTAMP,                   -- миграция 015
    last_notified_date DATE,                 -- миграция 021: кросс-джоб дедуп по теме (P1-7)
    CONSTRAINT uq_occurrence_per_day UNIQUE (reminder_id, due_date)
);

-- 20. ЗНАЧЕНИЯ КОНТРОЛИРУЕМЫХ ПОКАЗАТЕЛЕЙ (сон и произвольные: пульс, стресс…)
-- physical → measurements, lab → lab_results, sleep/custom → сюда.
CREATE TABLE client_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    metric_key TEXT NOT NULL,
    category TEXT,                           -- sleep | custom
    value_num NUMERIC,
    value_text TEXT,
    unit TEXT,
    meta JSONB,                              -- для сна: {"bedtime":"23:30","wake":"07:00"}
    measured_at DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- БЛОК 8: АНКЕТА, СОГЛАСИЯ, АУДИТ КЛИЕНТА (миграции 017, 018, 020)
-- =============================================

-- 21. ИСТОРИЯ ВЕРСИЙ АНКЕТЫ (клиент может редактировать анкету после онбординга)
CREATE TABLE client_questionnaire_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE RESTRICT,
    questionnaire_json JSONB NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW()
);

-- 22. СОГЛАСИЯ КЛИЕНТА (LEGAL-1/LEGAL-5 — доказуемость информированного согласия)
CREATE TABLE client_consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    consent_version TEXT NOT NULL,           -- смена версии → согласие запрашивается заново
    health_data BOOLEAN NOT NULL,
    telegram_channel BOOLEAN NOT NULL,
    channel TEXT NOT NULL DEFAULT 'web',
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT client_consents_all_required CHECK (
        health_data AND telegram_channel
    )
);

-- 23. НАХОДКИ ПРОАКТИВНОГО АУДИТА КЛИЕНТА (NEW-1, 2×/нед, только при находке)
CREATE TABLE client_audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'dismissed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dismissed_at TIMESTAMPTZ,
    dismissed_by UUID REFERENCES users(id)
);

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
COMMENT ON TABLE notification_schedule IS 'LEGACY (не используется): путь уведомлений v0. Записей в неё не создаёт никто — заменена reminders/reminder_occurrences. Код удалён в P2-4, таблица оставлена пустой; её удаление — отдельная миграция';
COMMENT ON TABLE audit_logs IS 'Полный аудит всех действий в системе';
COMMENT ON TABLE system_settings IS 'Системные настройки и пороги алертов';
COMMENT ON TABLE document_metadata IS 'Метаданные документов (источники, тип, привязка)';
COMMENT ON TABLE knowledge_base IS 'База знаний нутрициолога (pgvector)';
COMMENT ON TABLE client_documents IS 'Документы клиентов (pgvector)';
COMMENT ON TABLE measurements IS 'Замеры тела во времени (вес/шея/талия/бёдра/грудь)';
COMMENT ON TABLE lab_results IS 'Числовые показатели анализов во времени';
COMMENT ON TABLE client_reports IS 'Отчёты по клиенту: черновик → финал';
COMMENT ON TABLE reminders IS 'Шаблоны напоминаний клиенту + параметры контроля ответа';
COMMENT ON TABLE reminder_occurrences IS 'Срабатывания напоминаний: дедуп отправки и жизненный цикл ответа';
COMMENT ON TABLE client_metrics IS 'Значения показателей: сон и произвольные (пульс, стресс)';
COMMENT ON TABLE client_questionnaire_history IS 'История версий анкеты онбординга';
COMMENT ON TABLE client_consents IS 'Согласия клиента на обработку данных (LEGAL-1/5)';
COMMENT ON TABLE client_audit_findings IS 'Находки проактивного аудита клиента (NEW-1)';

-- =============================================
-- ЗАВЕРШЕНИЕ
-- =============================================

-- Консолидированная схема v1.6 (база v1.3 + миграции 001–021)
-- 23 таблицы + 1 VIEW + 2 триггера
--
-- Важное по защите данных (LEGAL-3, миграция 019): ВСЕ внешние ключи на clients(id)
-- переведены в ON DELETE RESTRICT. Физически удалить клиента, у которого есть хоть одна
-- связанная запись, нельзя — Postgres откажет. «Удаление» в интерфейсе означает
-- архивирование (client_status='archived'). Требование закона ОАЭ — хранение данных
-- о здоровье ≥25 лет.
--
-- notification_schedule оставлена как LEGACY: пустая, кодом не используется (см. P2-4).
