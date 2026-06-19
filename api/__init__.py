"""
api/ — HTTP API (FastAPI) для веб-фронта (React SPA).

Тонкий слой ТОЛЬКО для агента/LLM (чат, аналитика, vision, voice) с проверкой
Supabase JWT. CRUD/Auth/Storage фронт делает напрямую в Supabase под RLS.
Telegram-бот и n8n работают мимо этого API (как и раньше).
"""
