-- =============================================
-- МИГРАЦИЯ 011: Сидинг system_settings.llm_config (Фаза 2 централизации моделей)
-- Дата: 30 июня 2026
-- Описание: записывает стартовый llm_config (основная модель + вложенный резерв
--           fallbacks по каждому task_type) в system_settings. После этого БД
--           начинает управлять выбором моделей и резерва (resolve_fallback_chain /
--           resolve_vision_model / get_model_config), а нутрициолог правит их через
--           редактор «Настройки» — БЕЗ кода и деплоя. Код-константы остаются дефолтом.
--           Значение сгенерировано из utils.llm.build_default_llm_config() (1:1 с кодом).
-- Применить: Supabase → SQL Editor. ИДЕМПОТЕНТНА.
--   ON CONFLICT (key) DO NOTHING — НЕ перезатирает уже существующую (возможно,
--   отредактированную нутрициологом) строку llm_config.
-- Зависит от: фикс get_setting (читает колонку value), Фаза 1 (резолверы).
-- =============================================

INSERT INTO system_settings (key, value, description) VALUES
('llm_config', '{
  "dialog": {
    "provider": "groq", "model": "llama-3.3-70b-versatile",
    "temperature": 0.7, "max_tokens": 2000,
    "fallbacks": [{"provider": "gemini", "model": "gemini-2.5-flash"}]
  },
  "analytics": {
    "provider": "claude", "model": "claude-sonnet-4-6",
    "temperature": 0.3, "max_tokens": 4000,
    "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"},
                  {"provider": "gemini", "model": "gemini-2.5-flash"}]
  },
  "vision": {
    "provider": "gemini", "model": "gemini-2.5-flash",
    "temperature": 0.5, "max_tokens": 1500,
    "fallbacks": [{"provider": "claude", "model": "claude-sonnet-4-6"}]
  },
  "nutrition_analysis": {
    "provider": "claude", "model": "claude-sonnet-4-6",
    "temperature": 0.4, "max_tokens": 3000,
    "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"},
                  {"provider": "gemini", "model": "gemini-2.5-flash"}]
  },
  "summary": {
    "provider": "groq", "model": "llama-3.3-70b-versatile",
    "temperature": 0.5, "max_tokens": 2000,
    "fallbacks": [{"provider": "gemini", "model": "gemini-2.5-flash"}]
  },
  "planning": {
    "provider": "claude", "model": "claude-sonnet-4-6",
    "temperature": 0.4, "max_tokens": 3000,
    "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"},
                  {"provider": "gemini", "model": "gemini-2.5-flash"}]
  }
}'::jsonb, 'Конфигурация LLM по task_type: основная модель + резерв (fallbacks). Правится нутрициологом в Настройках.')
ON CONFLICT (key) DO NOTHING;
