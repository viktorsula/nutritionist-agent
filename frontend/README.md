# Frontend — React SPA (кабинеты клиента и нутрициолога)

Стек: Vite + React + TypeScript, Tailwind CSS, supabase-js (Auth + данные под RLS),
react-router, react-i18next (ru/en), TanStack Query, Recharts.

## Запуск (dev)
```bash
cd frontend
cp .env.example .env        # заполнить VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY / VITE_API_URL
npm install
npm run dev                 # http://localhost:5173
```
Параллельно должен работать Python API (FastAPI):
```bash
uvicorn api.main:app --reload --port 8000
```

## Архитектура
- **Auth + данные** — напрямую в Supabase (`src/lib/supabase.ts`) под JWT пользователя; RLS ограничивает доступ.
- **Агент (чат/аналитика)** — через Python API (`src/lib/api.ts`), токен в заголовке Authorization.
- **Роли/доступ** — резолв через `GET /me`; маршрутизация в `src/routes/ProtectedRoute.tsx` (+ gate доступа клиента).

## Структура
- `src/auth/` — AuthProvider (сессия, логин по паролю/OTP, logout).
- `src/pages/` — Login, AccessRestricted, client/ClientShell (3 колонки), nutritionist/NutritionistShell (табы).
- `src/i18n.ts` — переводы ru/en.

## Статус
Фаза 1 (каркас): вход, маршрутизация по роли, gate доступа, пустые оболочки.
Наполнение кабинетов — Фазы 2–3.
