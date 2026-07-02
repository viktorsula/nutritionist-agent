-- =============================================
-- МИГРАЦИЯ 012: Добавить orchestrator + nutritionist_orchestrator в system_settings.llm_config
-- Дата: 2 июля 2026
-- Описание: миграция 011 засеяла llm_config ДО появления LLM-оркестраторов, поэтому в БД
--           нет task_type 'orchestrator' (ветка клиента) и 'nutritionist_orchestrator'
--           (ветка нутрициолога). Из-за этого окно «Настройки → LLM-модели» их не показывает,
--           и нутрициолог не может настроить модель оркестраторов из кабинета (функционально
--           они работают — резолвер падает в код-дефолт DEFAULT_TASK_MODEL_MAPPING).
--           Эта миграция добавляет обе задачи в существующий llm_config.
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
--   Порядок операндов `новые_дефолты || value` => при конфликте ключа ПОБЕЖДАЕТ value
--   (существующая, возможно отредактированная нутрициологом, запись НЕ затирается; новые
--   ключи добавляются только если их ещё нет).
--   Резерв (fallbacks) у оркестраторов пустой: при недоступности Claude оркестратор
--   откатывается на детерминированный граф, а не на другую LLM (см. TASK_FALLBACK_CHAINS).
-- Зависит от: 011 (строка llm_config существует). Значения 1:1 с utils.llm.DEFAULT_TASK_MODEL_MAPPING.
-- =============================================

UPDATE system_settings
SET value = '{
  "orchestrator": {
    "provider": "claude", "model": "claude-sonnet-4-6",
    "temperature": 0.4, "max_tokens": 2000, "fallbacks": []
  },
  "nutritionist_orchestrator": {
    "provider": "claude", "model": "claude-sonnet-4-6",
    "temperature": 0.3, "max_tokens": 3000, "fallbacks": []
  }
}'::jsonb || value
WHERE key = 'llm_config';
