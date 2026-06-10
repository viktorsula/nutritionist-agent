-- =============================================
-- МИГРАЦИЯ 001: Добавление роли 'observer'
-- Дата: 10 июня 2026
-- Описание: Резервирование роли observer для продакшн-версии (v2.0 для клиник)
-- =============================================

-- Шаг 1: Удалить старый constraint
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

-- Шаг 2: Добавить новый constraint с observer
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('nutritionist', 'client', 'observer'));

-- Проверка: показать текущий constraint
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'users'::regclass
AND conname = 'users_role_check';

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ Роль 'observer' добавлена в users.role
-- ✅ В v1.0 роль зарезервирована, но не используется
-- ✅ В v2.0 будет активирована для клиник
-- =============================================
