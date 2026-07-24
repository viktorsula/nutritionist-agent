-- =============================================
-- Миграция 019: Защита от физического удаления клиента (LEGAL-3)
-- =============================================
-- Контекст: диагностика проекта (docs/docs/diagnostic_report.md, раздел P0-LEGAL) нашла,
-- что Federal Law №2/2019 (ОАЭ) требует хранить данные о здоровье клиента ≥25 лет с даты
-- последней процедуры, а почти все таблицы ссылаются на clients(id) через
-- ON DELETE CASCADE — физическое удаление строки clients молча стирает ВСЁ (анкету,
-- дневник питания, анализы, историю согласий и т.д.) без возможности восстановить.
--
-- В приложении сейчас НЕТ пути физического удаления клиента вообще — «удаление» в
-- интерфейсе (кабинет нутрициолога) уже означает архивирование (client_status='archived',
-- см. StatusEditor.tsx). Эта миграция не меняет прикладной код (переделывать нечего) —
-- она закрывает саму возможность физического удаления НА УРОВНЕ БД: если кто-то (по
-- ошибке вручную через Supabase, или в будущей непродуманной фиче) попытается
-- DELETE FROM clients, Postgres откажет с ошибкой внешнего ключа, пока у клиента
-- остаётся хоть одна связанная запись — вместо того чтобы молча каскадно всё стереть.
--
-- Технически: DO-блок динамически находит ВСЕ внешние ключи, ссылающиеся на clients(id)
-- с ON DELETE CASCADE (через pg_constraint/confdeltype='c'), и меняет их на ON DELETE
-- RESTRICT. Не завязано на явный список из 20 таблиц — устойчиво к дрейфу схемы и
-- будущим таблицам с client_id, если они будут по тому же паттерну (FK на clients(id)).
-- Идемпотентно: при повторном запуске находить уже нечего (все уже RESTRICT).
--
-- Примечание: clients.user_id → users(id) ON DELETE CASCADE НЕ трогаем отдельно — этого
-- не требуется. Если кто-то удалит users-строку, Postgres попытается каскадно удалить
-- связанную clients-строку, но упрётся в RESTRICT-ограничения дочерних таблиц (measurements,
-- client_profiles и т.д.) и откатит всю транзакцию — то есть защита работает и для этого
-- пути тоже, без отдельного изменения.
-- =============================================

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT c.conname AS constraint_name,
               c.conrelid::regclass::text AS table_name,
               a.attname AS column_name
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.confrelid = 'clients'::regclass
          AND c.contype = 'f'
          AND c.confdeltype = 'c'  -- 'c' = CASCADE
    LOOP
        EXECUTE format(
            'ALTER TABLE %s DROP CONSTRAINT %I',
            r.table_name, r.constraint_name
        );
        EXECUTE format(
            'ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES clients(id) ON DELETE RESTRICT',
            r.table_name, r.constraint_name, r.column_name
        );
        RAISE NOTICE 'client_data_retention: % (%) CASCADE -> RESTRICT', r.table_name, r.constraint_name;
    END LOOP;
END $$;

-- =============================================
-- ПРОВЕРКА:
--   -- Не должно остаться НИ ОДНОЙ строки (все FK на clients(id) теперь RESTRICT/NO ACTION):
--   SELECT c.conname, c.conrelid::regclass AS table_name, c.confdeltype
--   FROM pg_constraint c
--   WHERE c.confrelid = 'clients'::regclass AND c.contype = 'f' AND c.confdeltype = 'c';
--
--   -- Пример проверки поведения (ожидаем ошибку foreign key violation, НЕ каскадное удаление):
--   -- DELETE FROM clients WHERE id = '<любой существующий client_id с данными>';
-- РЕЗУЛЬТАТ: ✅ первый запрос возвращает 0 строк (CASCADE не осталось);
--   второй — foreign key constraint violation вместо удаления
-- =============================================
