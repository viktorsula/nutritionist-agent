-- =============================================
-- МИГРАЦИЯ v1.3 - ШАГ 1: ОЧИСТКА
-- Удаление старых таблиц
-- =============================================

-- Удаляем ВСЕ таблицы для полной пересборки
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS nutrition_diary CASCADE;
DROP TABLE IF EXISTS measurements CASCADE;
DROP TABLE IF EXISTS nutritionist_tasks CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS client_events CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS notification_schedule CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS wellness_plans CASCADE;
DROP TABLE IF EXISTS client_profiles CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS nutrition_plans CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Удаляем VIEW если существует
DROP VIEW IF EXISTS client_registry_view CASCADE;

-- Включить расширение pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ШАГ 1 ЗАВЕРШЁН
SELECT 'ШАГ 1: Очистка завершена' AS status;
