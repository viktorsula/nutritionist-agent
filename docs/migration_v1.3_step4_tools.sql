-- =============================================
-- МИГРАЦИЯ v1.3 - ШАГ 4: БЛОК 3 (РАБОЧИЕ ИНСТРУМЕНТЫ)
-- =============================================

-- 7. ПЛАНЫ ПИТАНИЯ
CREATE TABLE IF NOT EXISTS nutrition_plans (
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
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_nutrition_plans_active ON nutrition_plans(client_id, is_active) WHERE is_active = true;

COMMENT ON TABLE nutrition_plans IS 'Планы питания + БАДы, версионирование';

-- Триггер: автоинкремент версии
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

-- Триггер: деактивация старого плана
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

-- 8. ЗАДАЧИ
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

CREATE INDEX idx_tasks_client_status ON tasks(client_id, status) WHERE status = 'pending';

COMMENT ON TABLE tasks IS 'Задачи клиентам, created_by=nutritionist only';

-- ШАГ 4 ЗАВЕРШЁН
SELECT 'ШАГ 4: Блок 3 создан' AS status;
