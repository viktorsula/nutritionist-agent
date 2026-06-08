-- =============================================
-- ИСПРАВЛЕНИЕ: VIEW с SECURITY INVOKER
-- =============================================

-- Удаляем старый VIEW
DROP VIEW IF EXISTS client_registry_view CASCADE;

-- Создаём заново с SECURITY INVOKER
CREATE VIEW client_registry_view
WITH (security_invoker = true)
AS
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

-- Проверка
SELECT 'VIEW пересоздан с SECURITY INVOKER' AS status;
