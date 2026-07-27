-- =============================================
-- Миграция 023: Разрешить entity_type='knowledge_base' в audit_logs (найдено при P2-8)
-- =============================================
-- Найдено при подготовке просмотра audit_logs (P2-8): api/main.py пишет
-- write_audit_log(entity_type="knowledge_base", ...) из ДВУХ мест —
-- POST /nutritionist/knowledge (загрузка документа) и DELETE /nutritionist/knowledge/{id}
-- (удаление) — но CHECK audit_logs_entity_type_check (миграция 018) разрешал только
-- 'client', 'plan', 'task', 'schedule', 'settings', 'profile', 'reminder', 'consent'.
--
-- Последствие на проде: сама операция (загрузка/удаление документа) выполнялась
-- успешно, но последующий write_audit_log падал на constraint violation — вызов
-- НИЧЕМ не обёрнут в api/main.py, поэтому необработанное исключение долетало до
-- FastAPI и нутрициолог получал 500 вместо успеха, хотя документ реально сохранён
-- (или удалён). Тесты этого не ловили: write_audit_log в них замокан, проверка
-- ограничения БД никогда не выполнялась.
-- =============================================

ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_entity_type_check;
ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_entity_type_check
    CHECK (entity_type IN (
        'client', 'plan', 'task', 'schedule', 'settings', 'profile',
        'reminder', 'consent', 'knowledge_base'
    ));

-- =============================================
-- ПРОВЕРКА:
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--     WHERE conname='audit_logs_entity_type_check';
-- РЕЗУЛЬТАТ: ✅ constraint включает 'knowledge_base'
-- =============================================
