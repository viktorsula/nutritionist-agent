# Деплой (продакшен)

Архитектура прода — **2 независимых сервиса** + Supabase:

| Часть | Что | Где |
|-------|-----|-----|
| Бэкенд | FastAPI (`api/main.py`, uvicorn, Docker) | Render **Web Service** |
| Фронт | React SPA (`frontend/`, статика) | Render **Static Site** |
| БД/Auth/Storage | Supabase (RLS) | Supabase проект |

Канал клиента (Telegram-бот) — отдельный процесс, в этот деплой не входит.

---

## 1. Бэкенд (Render Web Service) — ГОТОВО
- Деплоится из `main` (Dockerfile → `uvicorn api.main:app --port $PORT`).
- URL: `https://nutritionist-agent-gvxp.onrender.com` — проверка: `/health` → `{"status":"ok"}`.
  Корень `/` отдаёт `{"detail":"Not Found"}` — это норма (у API нет маршрута `/`).
- **Env-переменные сервиса:**
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`,
  `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` (⚠️ не `GEMINI_*`), `OPENAI_API_KEY`,
  `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`,
  **`CORS_ORIGINS`** = URL фронта (см. шаг 3).

## 2. Фронт (Render Static Site)
Render dashboard → **New → Static Site** → подключить репозиторий `viktorsula/nutritionist-agent`:
- **Branch:** `main`
- **Root Directory:** `frontend`
- **Build Command:** `npm install && npm run build`
- **Publish Directory:** `dist`
- **Environment Variables:**
  - `VITE_SUPABASE_URL` = `https://<твой-проект>.supabase.co`
  - `VITE_SUPABASE_ANON_KEY` = anon-ключ (публичный, безопасен при RLS)
  - `VITE_API_URL` = `https://nutritionist-agent-gvxp.onrender.com`
- SPA-роутинг: файл `frontend/public/_redirects` (`/* /index.html 200`) уже в репо — Render его применит (deep-link refresh не будет давать 404).

После деплоя зафиксируй URL фронта, напр. `https://nutritionist-agent-frontend.onrender.com`.

## 3. Связать CORS (иначе браузер заблокирует вызовы API)
В **бэкенд-сервисе** Render задай `CORS_ORIGINS` = URL фронта из шага 2 (можно несколько через запятую). Сохранение env → бэкенд перезапустится.

## 4. Supabase Auth (вход и приглашения клиентов)
Supabase dashboard → **Authentication → URL Configuration**:
- **Site URL** = URL фронта.
- **Redirect URLs** — добавить URL фронта (и `…/login` при необходимости).
Иначе ссылки из email-приглашений клиентов будут вести не туда.
Email из коробки лимитирован (~3–4/час) — для многих тестеров подключить SMTP.

## 4b. Custom SMTP (Resend) — чтобы письма реально доходили
Встроенная почта Supabase жёстко лимитирована (≈2 письма/час, только для тестов) →
ошибка `over_email_send_rate_limit` ломает сброс пароля, вход по коду и **приглашения
клиентов**. Лечится подключением своего SMTP.

**Шаг 1 — аккаунт Resend.** Регистрация на resend.com (free, 3000 писем/мес), подтвердить
свой email.

**Шаг 2 — отправитель (sender):**
- *Без домена (тест):* отправитель `onboarding@resend.dev` — письма уходят ТОЛЬКО на email
  владельца аккаунта Resend (годится для входа нутрициолога, не для клиентов).
- *Прод (нужен для приглашений клиентам):* Resend → Domains → Add Domain → прописать в DNS
  записи SPF/DKIM → дождаться `Verified`. Отправитель = `noreply@<домен>`.

**Шаг 3 — ключ.** Resend → API Keys → Create. Это пароль для SMTP.

**Шаг 4 — Supabase → Authentication → Emails → SMTP Settings → Enable Custom SMTP:**
- Host: `smtp.resend.com`
- Port: `465` (SSL) или `587` (TLS)
- Username: `resend`
- Password: `<Resend API key>`
- Sender email: `onboarding@resend.dev` (тест) или `noreply@<домен>` (прод)
- Sender name: напр. «Кабинет нутрициолога»

**Шаг 5 — поднять лимит.** Supabase → Authentication → Rate Limits → увеличить «emails per
hour» (со встроенных ≈2 до, напр., 100).

**Шаг 6 — проверка.** На форме входа «Забыли пароль?» → письмо приходит; или серверно
`POST {SUPABASE_URL}/auth/v1/recover` (apikey) → 200 вместо 429.

## 5. Smoke-тест прода
1. Открыть URL фронта → страница входа.
2. Войти нутрициологом → кабинет (3 панели).
3. Создать клиента (оплата/режим/дата) → проверить, что пришло приглашение.
4. Чат-аналитика по клиенту → панель «Аналитика» (с живыми OpenAI+Claude — полноценно).
5. Отчёт по клиенту → генерация → правка → PDF/TXT.

## Примечания
- Бандл фронта ~1 МБ (311 КБ gzip). При желании — код-сплит (dynamic import / manualChunks).
- Миграции Supabase 001–008 применены (проверено интроспекцией).
