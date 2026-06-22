-- =============================================
-- МИГРАЦИЯ 005: Storage-бакет для документов/анализов клиента
-- Дата: 20 июня 2026
-- Описание: создаёт приватный бакет 'client-documents' (фронт грузит туда PDF
--           анализов и документы) и RLS-политики на storage.objects.
--           Путь файла во фронте: '{client_id}/{timestamp}_{name}'
--           → первая папка пути = client_id.
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
-- Зависит от хелперов из 004: app_is_nutritionist(), app_user_role(),
--           app_current_client_id().
-- =============================================

-- ---------------------------------------------
-- 1. Приватный бакет
-- ---------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('client-documents', 'client-documents', false)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------
-- 2. RLS-политики на storage.objects (RLS на storage.objects включён Supabase)
--    Доступ: клиент — только своя папка ('{client_id}/...'); нутрициолог — всё;
--    observer — чтение (на будущее, v2.0). service_role RLS обходит.
-- ---------------------------------------------

-- SELECT (в т.ч. для createSignedUrl)
DROP POLICY IF EXISTS cdocs_obj_select ON storage.objects;
CREATE POLICY cdocs_obj_select ON storage.objects FOR SELECT TO authenticated
    USING (
        bucket_id = 'client-documents'
        AND (
            app_is_nutritionist()
            OR app_user_role() = 'observer'
            OR (storage.foldername(name))[1] = app_current_client_id()::text
        )
    );

-- INSERT (загрузка файла)
DROP POLICY IF EXISTS cdocs_obj_insert ON storage.objects;
CREATE POLICY cdocs_obj_insert ON storage.objects FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'client-documents'
        AND (
            app_is_nutritionist()
            OR (storage.foldername(name))[1] = app_current_client_id()::text
        )
    );

-- UPDATE (перезапись)
DROP POLICY IF EXISTS cdocs_obj_update ON storage.objects;
CREATE POLICY cdocs_obj_update ON storage.objects FOR UPDATE TO authenticated
    USING (
        bucket_id = 'client-documents'
        AND (
            app_is_nutritionist()
            OR (storage.foldername(name))[1] = app_current_client_id()::text
        )
    )
    WITH CHECK (
        bucket_id = 'client-documents'
        AND (
            app_is_nutritionist()
            OR (storage.foldername(name))[1] = app_current_client_id()::text
        )
    );

-- DELETE
DROP POLICY IF EXISTS cdocs_obj_delete ON storage.objects;
CREATE POLICY cdocs_obj_delete ON storage.objects FOR DELETE TO authenticated
    USING (
        bucket_id = 'client-documents'
        AND (
            app_is_nutritionist()
            OR (storage.foldername(name))[1] = app_current_client_id()::text
        )
    );

-- =============================================
-- ПРОВЕРКА
-- =============================================
-- SELECT id, public FROM storage.buckets WHERE id = 'client-documents';
-- SELECT policyname, cmd FROM pg_policies
--   WHERE schemaname='storage' AND tablename='objects' AND policyname LIKE 'cdocs_obj%';

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ Приватный бакет 'client-documents'
-- ✅ Клиент грузит/читает только свою папку '{client_id}/...'
-- ✅ Нутрициолог — полный доступ; observer — чтение; service_role обходит RLS
-- =============================================
