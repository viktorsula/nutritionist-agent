-- =============================================
-- МИГРАЦИЯ 008: Отчёты по клиенту (генерация агентом + правка нутрициологом)
-- Дата: 22 июня 2026
-- Описание: сформированные отчёты по клиенту (напр. «Рекомендации для подопечного»).
--           Агент заполняет шаблон данными клиента, нутрициолог правит и выгружает
--           в PDF/TXT. Хранится сформированный экземпляр (с правками).
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
-- Зависит от: clients, users; RLS-хелпер app_is_nutritionist() (миграция 004).
-- =============================================

CREATE TABLE IF NOT EXISTS client_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,                 -- тип/форма отчёта (напр. 'recommendations')
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',           -- текст отчёта (с правками нутрициолога)
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final')),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_reports_client
    ON client_reports(client_id, created_at DESC);

COMMENT ON TABLE client_reports IS
    'Сформированные отчёты по клиенту: агент заполняет шаблон, нутрициолог правит, '
    'выгрузка в PDF/TXT. report_type — тип формы.';

-- ---------------------------------------------
-- RLS: полный доступ только нутрициологу (как у system_settings).
-- service_role (серверный API/агент) RLS обходит — генерация идёт через бэкенд.
-- ---------------------------------------------
ALTER TABLE client_reports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS reports_nutri ON client_reports;
CREATE POLICY reports_nutri ON client_reports FOR ALL TO authenticated
    USING (app_is_nutritionist()) WITH CHECK (app_is_nutritionist());

-- =============================================
-- ПРОВЕРКА
-- =============================================
-- SELECT to_regclass('public.client_reports');
-- SELECT polname FROM pg_policy WHERE polrelid = 'client_reports'::regclass;

-- =============================================
-- РЕЗУЛЬТАТ:
-- ✅ client_reports — отчёты по клиенту (RLS: нутрициолог)
-- =============================================
