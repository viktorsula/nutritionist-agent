# Журнал прогресса проекта

## Статус: В разработке → ПРОД на Render (PR #44 влит; поворот на LLM-оркестратор — ветка feat/llm-orchestrator)
Последнее обновление: 1 июля 2026
Сессия: архитектурный поворот — уход от жёсткого графа рёбер к LLM-оркестратору с tool-calling (Фазы 0–1)

### Сессия 1 июля 2026 (часть 2) — поворот на LLM-оркестратор (Фазы 0–1, ветка feat/llm-orchestrator)

**Корневая мысль.** Граф из детерминированных рёбер (ingest→determine→load_context→dispatch→…)
даёт цепочку последовательных LLM-вызовов (determine→extract→present→summary); каждое звено —
точка отказа, по теории вероятности это МНОЖИТ ошибку (~0.9⁴≈66%) и рассинхронизирует шаги
(кейс «веганская лазанья», PR #44). Изначальная философия проекта: сам LLM-оркестратор понимает
тему, выбирает инструменты и объём контекста. Плюс определитель/clarify крутились на слабой для
маршрутизации модели (`dialog`=Groq llama-3.3-70b). Решение: перейти на LLM-оркестратор с
tool-calling; модель оркестратора — **Claude Sonnet**. Миграция strangler-паттерном за фиче-флагом,
безопасность (алерты/доступ) остаётся ДЕТЕРМИНИРОВАННОЙ. План — `docs/architecture_llm_orchestrator.md`.

**Фаза 0 — фундамент tool-calling в `utils/llm.py` (commit `c6813c1`).** `call_llm` был текст-в-текст
(`tools` = только серверный web_search у Claude); добавлен цикл КЛИЕНТСКИХ инструментов
`tool_use → tool_result` в `_call_claude` (`tool_handlers`/`max_tool_iterations`); ошибка/неизвестный
инструмент → `tool_result` is_error=True (ход не падает, модель восстанавливается); usage
накапливается по итерациям; в ответ добавляется `tool_calls`. `call_llm` вырезает наши параметры для
не-Claude провайдеров. Обратно совместимо. Тесты `utils/test_llm_tools.py` (7). 248→255 passed.

**Фаза 1 — LLM-оркестратор рядом с графом (commit `4606313`).** `agents/client/agent_orchestrator.py`:
- `should_use(client_id, message_type)` — ENV `CLIENT_ORCHESTRATOR_ENABLED` + белый список
  `CLIENT_ORCHESTRATOR_CLIENT_IDS`; фото → граф (граница Фазы 1: текст+голос через оркестратор,
  мультимодальность — следующий шаг).
- `process(...)` — ход: ingest(голос→текст) → лёгкий базовый контекст → цикл агента → безопасность+
  формат → save_to_db; per-`client_id` `threading.Lock` (изоляция параллельных диалогов).
- 7 инструментов — обёртки над существующим (ничего не дублируем): `log_meal/water/weight/wellbeing/
  labs` → `intake_store.persist_record` (запись + medical-алерты), `get_client_data(scope)`,
  `search_knowledge(query)` (pgvector). Уточнение — текстом. Тёплый ответ пишет сама модель.
- Развилка в `process_client_message`: флаг включён + текст/голос → оркестратор; `LLMUnavailableError`/
  ошибка → молчаливый откат на граф. `task_type='orchestrator'` (Claude, без LLM-резерва — резерв = граф).
  Промпт `prompts/client/orchestrator_system.md` (первое лицо «я»). Тесты `test_agent_orchestrator.py`
  (13). 255→**268 passed**.

**⏳ Дальше:** Фаза 2 — обкатка на проде на 1 клиенте (Екатерина): выставить ENV на Render, E2E в
Telegram текстом/голосом (еда/вода/вес/самочувствие/анализы/вопрос о данных/совет), остальные — на графе.
Затем Фаза 3 (async + per-id + чистка мёртвых узлов) и мультимодальный оркестратор (фото напрямую в Claude).

### Сессия 1 июля 2026 — ветка клиента: краш intake, мёртвые update-пути, память, латентность (PR #44)

Старт: E2E владельца в Telegram (фото «веганская лазанья» + текст) вскрыл на проде связку
дефектов — противоречивые ответы, двойное «Здравствуйте», «мы» вместо «я», задержки. Разбор
по коду и логам Render — чинили по корню.

**Диагностика (что происходило).** Один канал, одна модель (Groq `dialog`), но **два независимых
прохода графа**: фото → `vision` (записал приём пищи), отдельно текст → `intake`/`diary` → **упал** →
`clarify` (противоречит первому ответу). Определитель — сам LLM-вызов; за ход идёт цепочка
последовательных вызовов LLM (determine→extract→present/clarify→summary) — отсюда латентность
(текст ≈ 7с, фото ≈ 24с из-за Gemini дважды: classify_image + analyze_food_plate).

**1. Баг — краш intake на «грязном» KBJU.** LLM иногда отдаёт `meal.items[].kbju` строкой/числом →
`intake_schema.kbju_from_legacy` падал `'str' object has no attribute 'get'` → весь приём в `clarify`.
Защита от не-`dict` входа (КБЖУ = «неизвестно»).

**2. Баг — 6 мёртвых update-путей (`.single()` на проде).** `.single()` на `.update().eq()` падает
на прод `supabase==2.10.0` (`'SyncFilterRequestBuilder' object has no attribute 'single'`; локальная
2.31 маскировала). PR #33 чинил `.select("*")`, но `.single()` пропустил. Молча не сохранялись:
`update_client`, `update_notification_schedule`, `update_system_setting`, `update_conversation_summary`,
`complete_task`, `update_wellness_plan`. В т.ч. **скользящая сводка (долговременная память) была мертва
во всём проекте**. Helper `_execute_one()` + снятие `.single()` со всех 6 (SELECT-пути не тронуты).

**3. Память в ветке intake.** `load_context` грузил историю/сводку только для `profile`/`advice`, а
`present()` не передавал историю в LLM → тёплый ответ шёл «вслепую», здоровался повторно / противоречил.
Теперь `intake` тоже получает историю(10)+сводку; `present()` инжектит сводку в system и последние 6
реплик перед фактами хода.

**4. Латентность.** `update_rolling_summary` делал отдельный LLM-вызов синхронно в `save_to_db_node` →
клиент ждал лишнее. Вынесено в daemon-поток (снапшот полей, не живой state).

**Аудит памяти по графам.** Краткосрочная история (10) РАБОТАЕТ в profile/advice/аналитике, отсутствовала
в intake (п.3). Долгосрочная сводка была мертва везде (п.2). ТЗ (`docs/docs/technical_specification.docx`)
требует: «История разговоров ← динамически» + `load_episode_memory(last_n=10)` + `summarize_conversation`.

**Тесты: 242 → 248 passed** (+6 регресс: non-dict/string kbju, `_execute_one` на прод-билдере,
инъекция истории/сводки в present). PR #44 (ветка `fix/intake-crash-and-rolling-summary`).

**Не входит (согласовано отдельно):** промпты (множественное «мы» → первое лицо; приветствие-нонсеквитур —
правит владелец); `meal_type` по таймзоне клиента vs «не проставлять молча» (обсуждается); задвоение
фото+текст (turn-буфер / `TELEGRAM_TURN_DEBOUNCE_SEC`) — отдельная задача. ⏳ E2E владельца на ветке.

### Сессия 30 июня 2026 — починка LLM, опыт фото, централизация моделей (PR #32–#37; влиты)

Сессия началась с разбора петли clarify на проде (клиент слал фото еды — агент переспрашивал
по кругу). Диагностика по логам Render вскрыла цепочку дефектов; чинили по корню.

**1. Прод-LLM лежал (PR #32, #33).**
- `gemini-1.5-flash` снята Google (404 на v1beta) → падали vision и Gemini-резерв; Groq отдавал
  401 (ключ протух на Render). Оба провайдера `dialog` мертвы → определитель уходил в фолбэк
  `clarify`. Фикс: `gemini-1.5-flash` → `gemini-2.5-flash` (выбор по ListModels); Groq-ключ обновил
  владелец. (PR #32)
- `get_setting` читал `setting_value` вместо колонки `value` — **разобрано глубже на шаге 4**.
- `.update().eq().select("*")` падал на прод-supabase 2.10.0 (`SyncFilterRequestBuilder` без
  `.select()`) — PR #21 чинил insert/upsert, но **6 update-путей пропустил**: rolling-summary,
  update_client/wellness_plan/task/notification/system_setting молча не сохранялись. Долговременная
  память не писалась. Фикс: убран `.select("*")` в 6 цепочках. (PR #33)

**2. Опыт фото (PR #34).** На «фото + Посмотри обед» агент отвечал ДВАЖДЫ (vision-ack + diary-clarify)
и врал «я текстовый ИИ, не вижу фото». Причины: turn-буфер не склеивал одиночное фото + текст
(`_merge_single_photo_with_text` — теперь один ход, текст = подпись; тему делит определитель);
vision молчал при ack (`ack_only` глушил `present()`) — теперь всегда тёплый ответ с распознанным
составом; `dialog_system.md` отрицал зрение — правило «у системы есть разбор фото». +3 теста склейки.

**3. Централизация моделей в llm_config (PR #35–#37) — модели больше не захардкожены.**
Снятие модели требовало правок в 6 местах кода; «как у промптов» (БД-переопределение) было только
для основной модели. Сделано «как у промптов» для резерва и vision:
- Фаза 1 (#35): `resolve_fallback_chain` + `resolve_vision_model` (БД `llm_config` → код-дефолт);
  `get_model_config` срезает `fallbacks`; жёсткая деградация в код при битом JSON. 10 тестов.
- Фаза 2 (#36): `build_default_llm_config()` + миграция `011_seed_llm_config.sql` (ON CONFLICT DO
  NOTHING) + **корневой фикс `get_setting` → колонка `value`**. Это чинит не только модели, но и
  **переопределение ПРОМПТОВ из БД** (веб-редактор сохранял, а система читала файлы) и
  `trusted_sources` — весь слой «БД-приоритет» был мёртв из-за опечатки в ключе.
- Фаза 3 (#37): редактор `LlmConfigEditor` — полная структура + структурная валидация (provider ∈
  groq/claude/gemini, model, fallbacks) + подсказки; 8 vitest-тестов.
Итог: смена снятой модели = правка в «Настройках», без кода и деплоя.

**4. Окно «LLM-модели» как порт смены инструмента (PR #39–#42) — продолжение централизации.**
Цель владельца: модели быстро меняются → менять инструмент без кода, удобно из кабинета.
- Фаза A (#39): бэкенд — `list_provider_models` (живой ListModels groq/claude/gemini, фильтр,
  кэш 5 мин), `test_model` (пинг), эндпоинты `/nutritionist/llm/{providers,models,test,defaults}`.
- Фаза B (#40): структурное окно — карточки по 6 задачам (основная модель из живого списка +
  ручной ввод, резерв с переставлением, «Проверить», advanced, «Сбросить на дефолт»,
  экспертный JSON-режим). Логика конфига — чистый `llmConfigOps.ts` (+7 vitest).
- Правка (#41): выбор задачи по названию (одна карточка вместо всех 6) — по просьбе владельца.
- Фаза C (#42): generic OpenAI-совместимый адаптер — новый провайдер (OpenAI/Mistral/DeepSeek/…)
  добавляется КОНФИГОМ через `llm_config._providers` (`{base_url, api_key_env}`), без кода;
  `_call_openai_compatible`, обогащение кандидатов, discovery для кастом-провайдеров.
Граница «без кода»: новая модель у нативных или новый OpenAI-совместимый провайдер — конфиг;
экзотический провайдер со своим SDK — отдельный адаптер (редко). Сценарий C2 (форма управления
`_providers` в обычном режиме) — опционально, пока через экспертный JSON.

**Бэкенд-набор: 242 passed. Фронт: tsc чисто, vitest 19 passed.**
**⏳ Шаги владельца:** применить миграцию 011 (сделано); E2E — фото еды одним ходом (мягкий ответ),
редактор моделей, перепроверить редактор промптов (теперь БД-приоритет реально работает).

### Сессия 29 июня 2026 — привязка Telegram, сброс пароля, UX, Фаза 2 (PR #21–#23, #25; влиты + задеплоены)

**1. Блокер «Создать ссылку привязки → Failed to fetch» — ЗАКРЫТ (PR #21, merge `5339965`).**
Оказался НЕ про CORS. Роут `POST /clients/{id}/telegram-link` падал с **500** от
`.insert(...).select("*")` в `database/queries.py`: на проде стоит `supabase==2.10.0`, где
`.insert()` возвращает `SyncQueryRequestBuilder` без `.select()` → `AttributeError`. Локально
`2.31.0` это маскировало. 500 рождается в `ServerErrorMiddleware` (снаружи `CORSMiddleware`) →
ответ без `Access-Control-Allow-Origin` → браузер показывал «CORS / Failed to fetch».
Диагностика по traceback из логов Render. Фикс: убран лишний `.select("*")` в 13 вызовах
(12 insert + 1 upsert); легитимный SELECT не тронут. Чинит и другие молча-падавшие записи
(conversations, client_events, measurements, lab_results, планы/задачи, расписания, аудит).
E2E привязки пройден: `clients.telegram_id` записан, токен погашен. 155 passed.

**2. Сброс пароля клиента нутрициологом (PR #22, merge `f72484d`).** Обход мёртвой почты
(Supabase/Brevo без домена не шлют). Кнопка «Сбросить пароль клиента» в карточке →
`POST /clients/{id}/reset-password` (require_role nutritionist): временный пароль через
**GoTrue admin REST** (`PUT /auth/v1/admin/users/{id}`, прямой HTTP, не SDK — чтобы не
зависеть от версии gotrue на проде) + `email_confirm`; пароль показывается в кабинете
(копирование) и best-effort дублируется письмом нутрициологу через **Gmail SMTP**
(`utils/mailer.py`, креды `GMAIL_USER`/`GMAIL_APP_PASSWORD`). Пароль в аудит не пишется.
Новое: `database/auth.py::set_user_password`, `database/queries.py::get_user_auth_id`,
фронт `ClientCard` карточка «Пароль клиента». Проверено вживую (set → вход HTTP 200).
ENV Gmail заданы на Render — письмо-дубль приходит. 160 passed.

**3. UX кабинетов + редактор промптов (PR #23, merge `d759c8d`).**
- Кабинет клиента: чат теперь скрывается/раздвигается (перетаскивание границы) — как у
  нутрициолога. `ClientShell` переведён на flex с `chatVisible`/`chatWidth` в localStorage.
- Подтверждение на «Создать ссылку привязки» (перевыпуск гасит старую); сброс пароля и
  отвязка Telegram подтверждались и раньше.
- Редактор промптов: **две вкладки** (Коммуникационные/Системные); системные промпты
  СТАЛИ редактируемыми (`registry.is_editable` → любой ключ реестра) с жёлтым
  предупреждением о хрупких форматах. 160 passed, tsc чист.

**Почта (self-service сброс по письму)** — упирается в СВОЙ ДОМЕН: free-домен-отправитель
блокируется Gmail/Yahoo/Outlook, Brevo-аккаунт не активирован (502). Шаг владельца, кода не
требует. Сброс пароля без домена закрыт обходом (п.2).

**4. Фаза 2 приёма входящих — turn-буфер + альбомы (PR #25, merge `e5b0442`).**
`tg_bot/turn_buffer.py`: буфер по chat_id с debounce (env `TELEGRAM_TURN_DEBOUNCE_SEC`,
дефолт 7с, `≤0` — выключен). Серия текстов → один ход (склейка `\n`, определитель режет на
сегменты); альбом (`media_group_id`) → один ход по первому фото + «получено N фото»
(Вариант 1, без переделки vision); голос/документ/одиночное фото — отдельным ходом. «Печатает…»
перенесён в буфер; webhook отвечает быстрее (enqueue→фон). Веб `/chat` не буферизуется. Тесты
`TestTurnBuffer`, набор 164 passed.

**5. Протокол `IntakeRecord` — ЗАВЕРШЁН (Слайсы 1–4, PR #27→#30, все влиты; HEAD `d14ba95`).**
Единый внутренний формат извлечённых данных приёма (extract→domain→present), источник правды —
структура, проза в логику не возвращается.
- Слайс 1 (PR #27): `agents/client/intake_schema.py` — схема v1 (kind/meal{items,total}/water/
  weight/wellbeing/labs + confidence + uncertainties; КБЖУ вкл. sugar_g/fiber_g) + `normalize` +
  `validate` (needs_clarify) + `parse_amount` + адаптеры. 27 тестов.
- Слайс 2 (PR #28): `intake_store.persist_record` — единая запись фактов в БД + алерты по kind;
  diary/vision делегируют. Поведение эквивалентно.
- Слайс 3 (PR #29): `intake_present.present` — общий тёплый ответ ИЗ записи (свой промпт на путь).
- Слайс 4 (PR #30): промпты `diary_extraction`/`vision_food_plate` выдают `IntakeRecord` напрямую;
  `coerce_to_record` (новый+legacy, де-риск); `validate`-гейт перед записью (low → не пишем);
  `clarify_from_uncertainties` — ОДИН вопрос на все неясности. 211 passed.
- ⚠️ Слайс 4 меняет контракт вывода LLM на проде → нужен E2E (еда текст/фото с сахаром, вода, вес,
  самочувствие, анализы, мутный кейс → один уточняющий вопрос). Адаптеры-фолбэк страхуют.

**Дальше (согласовано, поверх протокола):** (1) **агрегация суточных тоталов + графики питания**
(ккал/БЖУ/сахар/вода) в кабинете клиента (выбор нутрициологом, как `tracked_lab_indicators`) — пока
НЕТ; (2) Фаза 3 (цель воды + алерты воды/сахара/еды + end-of-day + окна приёмов + оживить
no_response). E2E Фазы 2 и Слайса 4 в Telegram — гоняет Виктор.

### Сессия 27 июня 2026 — Приём входящих, ШАГ 1 (влит, задеплоен)

Переделка приёма входящих сообщений клиента: исправлены две структурные ошибки —
маршрутизация «модальность вперёд темы» и отсутствие понятия «ход». Реализован Шаг 1
(под-шаги 0–1.6); PR #18 влит в `main` (merge `0ea30a9`, код `87e8a46`), задеплоен на
Render (Live). Бэкенд-набор **152 passed**.

**Таксономия 8→3** (`agents/client/branches.py`): верхний уровень `intake`(ack) /
`profile`(answer, fallback) / `advice`(answer); нижний — под-типы хранения intake
(meal/water/weight/wellbeing/labs/document). Определитель `intake_determiner.md` переписан
(3 ветки + якоря + few-shot).

**Граф пересобран линейно** (`orchestrator.py`):
ingest → determine → load_context(по веткам) → dispatch(сегменты) → format_response → save_to_db.
Удалены `route_node`/`_classify_text`.
- ingest: `classify_image` поднят в нормализацию (food|lab_document|fridge|other) → `state['image_kind']`.
- load_context: контекст ПО ВЕТКАМ (intake — лёгкий+алерты; profile — +история/сводка/задачи/ЗОЖ/анализы; advice — +сводка).
- dispatch: дедуп по ветке; intake → persist без тёплого ответа (`ack_only`), захват → квитанция, неудача → clarify; profile/advice → полный ответ.
- format_response: предупреждения → clarify → answer → квитанция «✓ Записал: …».

**Уточнение клиента (`clarify`)** — третий исход: определитель шлёт при «не разобрать»,
intake-неудача захвата тоже → clarify (промпт `client/clarify_request.md`). Данные «наугад» не пишем.

**Данные клиента:** вода → `client_events: water_logged` (`diary._handle_water`); тип приёма пищи
(`food_analysis.resolve_meal_type`) в `calories_logged` (diary + vision).

**Совет (advice):** фото холодильника → `utils.vision.analyze_fridge` (UC-3, промпт `system/vision_fridge.md`)
→ продукты + meal_type в промпт `nutrition_agent` («советуй только из имеющегося, в рамках плана»).

**Тесты:** `test_intake` / `test_orchestrator` / `test_orchestrator_integration` (end-to-end на моках) /
`test_diary` / `test_nutrition`.

**⏳ E2E на проде** — гоняет Виктор через Telegram (чеклист 10 кейсов в `РАБОЧИЙ.md`).
**Дальше:** Фаза 2 (turn-буфер debounce 6–10с + media_group/альбомы), Фаза 3 (цель воды в плане +
алерты воды/еды + end-of-day напоминания + окна приёмов + оживить no_response).

### Сессия 25 июня 2026 (часть 2) — Telegram-канал нутрициолога + анализ промптов

- **Telegram-канал нутрициолога** (PR #15, влит): двусторонний — нутрициолог общается с агентом
  как в вебе (router распознаёт по `NUTRITIONIST_TELEGRAM_ID` → оркестратор нутрициолога) +
  планировщик пушит критичные алерты (high/critical/bad_wellbeing) в личку. 100 passed.
  Live-проверка: работает. Грабли: путают `TELEGRAM_BOT_TOKEN` (секрет бота) и
  `NUTRITIONIST_TELEGRAM_ID` (numeric ID аккаунта). Деталь — память [[project_nutritionist_telegram_channel]].
- **PR #16** (открыт): `.gitignore` для локального `РАБОЧИЙ.md` + этот журнал.
- **Анализ промпт-архитектуры** (Виктор обдумывает): карта 17 промптов (7 файловых редактируемых
  нутрициологом + 10 инлайн в коде). Цель — вынести все инлайн в файлы (`prompts/system/` для
  разработчика), разделить доступ по ролям. Карта — память [[project_prompt_architecture]] + `РАБОЧИЙ.md`.
- **Найденные пробелы:** (1) алерт `no_response` фактически мёртв — `_check_no_response` не на
  расписании (только при сообщении клиента); (2) нет guardrail релевантности ответа;
  (3) task_type рассинхрон (summary/analytics-plan шлют `dialog`).
- **Веб «не открывается» у Виктора:** прод исправен (фронт/бэкенд 200, бандл с верным supabase URL,
  SPA-фоллбэк ок) → причина клиентская (кэш/браузер); ждём DevTools Console.

### Сессия 25 июня 2026 — спасение оборванной работы + синхронизация документации

Вчера (24 июня) работу остановили резко. Аудит состояния git вскрыл, что **многое не было
сохранено/задеплоено**:
- **9 коммитов от 24 июня висели только локально** (`origin/stage6-utils` отставал; память/GOTO
  ошибочно говорили про «7 коммитов» — на деле 9, включая APScheduler и док-коммит).
- **4 файла с незакоммиченными правками** — целостная, законченная фича «аудит правок настроек
  с фронта» (разрыв №6), не закоммичена.
- **ТЗ v1.4 (`technical_specification_V1.4.docx`)** — был untracked.

Сделано:
- **Аудит настроек №6 закоммичен** (`b372dd3`): `POST /nutritionist/setting` (require_role
  nutritionist) → `get_setting` (old) → `upsert_system_setting` → `write_audit_log`; фронт
  `saveSetting()` теперь через бэкенд, а не прямой write в Supabase мимо аудита.
- **ТЗ v1.4 добавлен в git** (`beec0ed`).
- **Вся ветка запушена** в `origin/stage6-utils` (`daca5b1..beec0ed`).
- **Миграции 002 (RPC `match_*`) и 009 (rolling-summary) — ПРОВЕРЕНЫ как применённые** в
  Supabase (интроспекция: колонки `clients.conversation_summary/...` существуют; обе RPC
  вызываются). Блокер миграций снят — 001–009 применены.
- **Документация синхронизирована** с фактом: ТЗ v1.4 / GOTO / память — APScheduler помечен
  реализованным (был TODO), миграции 002/009 — применёнными, задача №6 — закрытой.

**Тесты:** `api/test_scheduler.py` 8/8 ✅. ⚠️ Найдены **2 предсуществующих падения**
`api/test_api.py` (`test_create_client_ok`, `test_create_client_invalid_email` → `/clients` 422);
воспроизводятся на чистом HEAD, к работе 24 июня не относятся — отдельная задача.

**⏳ Осталось перед merge в main:** ENV Telegram (`TELEGRAM_BOT_TOKEN`/`WEBHOOK_URL`/
`WEBHOOK_SECRET`) + set_webhook; E2E-прогон каналов; влить `stage6-utils → main`.

### Сессия 24 июня 2026 — память, анализы клиента, Telegram-webhook

Сессия началась с аудита движения информации («карта памяти») — он вскрыл разрывы,
которые и закрывали по плану (ранжированному по значимости). Все правки на `stage6-utils`.

**Блок 1 — быстрые победы** (коммит `e76274e`):
- Telegram-резолв роли восстановлен: `queries.get_user_by_telegram_id` + `get_user`
  (router.get_user_info звал несуществующие функции → всегда user_not_found).
- `wellness_plan` грузится в `load_context` и доходит до `nutrition_agent` (был мёртв).

**Блок 2 — ingestion (keystone RAG)**: путь записи эмбеддингов раньше НИКТО не вызывал →
`knowledge_base`/`client_documents` были пусты.
- `utils/ingestion.py` (коммит `fed0fa2`): extract_text (PDF/текст) → chunk_text →
  get_embedding (ada-002) → insert_*_chunk; тесты (13).
- Документы клиента: `POST /documents/{id}/ingest` (скачивает из Storage, векторизует);
  фронт зовёт ингест после загрузки.
- База знаний нутрициолога (коммит `9997d87`): `POST/GET/DELETE /nutritionist/knowledge`
  (multipart, оригинал не храним) + UI «Настройки → База знаний».

**Вес → measurements** (коммит `3ed7546`): вес из диалога теперь точка временного ряда
в `measurements` (а не событие `weight_logged`); алерт `weight_increase` сравнивает два
последних замера (+ guard `_within_days`). Расщепление хранилища устранено, график ожил.

**Приём анализов клиента** (коммит `0202e38`):
- текст «холестерин 5.2» → diary тема `lab` → `lab_results` (source='client');
- фото бланка → `vision.classify_image` + `analyze_lab_document` → `lab_results`;
- PDF (веб) → `utils/labs.extract_labs_from_text` в ingest-эндпоинте (source='client_pdf').

**Rolling-summary** (коммит `6d745c3`): долговременная память диалога вместо жёстких 10 реплик.
- migration `009`: `clients.conversation_summary`/`summary_message_count`/`summary_updated_at`;
- `agents/client/summary.py` (summary-буфер, обновление раз в 10 сообщений);
- сводка инжектится в промпты dialog/nutrition поверх краткосрочного окна.

**Блок Telegram** (коммит `eb0e5eb`):
- T1: fix диспетчера (telegram_id вместо client.user_id) + общий `build_application()`;
- T2: webhook в FastAPI (`api/telegram_webhook.py` + lifespan + `POST /telegram/webhook`),
  ИНЕРТНО без `TELEGRAM_BOT_TOKEN` (прод не затронут);
- C2: `document_agent` — PDF из Telegram → векторизация + анализы.

**⏳ Осталось перед/при деплоем:**
- применить миграции в Supabase: `002` (RPC vector search) и `009` (summary);
- ENV бэкенда для Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`;
- E2E-прогон (анализы/фото/PDF/голос; webhook) — на проде;
- открытые: аудит правок настроек с фронта (№6); маппинг client-indicator → каноничные
  ключи нутрициолога (v1.1); актуализация ТЗ под React/FastAPI (v1.3 → v1.4).

### Деплой 23 июня 2026 — белый экран фронта УСТРАНЁН ✅
- **Реальная причина** (не «пустой env», как предполагалось 22 июня): `VITE_SUPABASE_URL` на
  Render Static Site был задан как **голый реф проекта** `ggorlbhrrlqocnqvbxqr` вместо полного
  `https://ggorlbhrrlqocnqvbxqr.supabase.co`. `createClient("<ref>", anon)` → `supabase-js`
  делает `new URL(...)` → `Invalid URL` → React не монтируется. Anon-ключ и `VITE_API_URL`
  были вшиты корректно.
- **Фикс:** значение `VITE_SUPABASE_URL` → полный https-URL + Manual Deploy с Clear build cache.
- **Headless-верификация прода (вся зелёная):** бэкенд `/health` ок; фронт `index.html` 200 +
  свежий бандл (старый хэш был залипшим CDN-кэшем); в бандле строка `https://<ref>.supabase.co`;
  anon-ключ — валидный JWT (3 части); `VITE_API_URL` корректен; Supabase `auth/v1/settings`
  с anon → 200; CORS бэкенда `Access-Control-Allow-Origin` = URL фронта; CSS/JS-ассеты 200.
- **Подтверждено Виктором:** форма входа рендерится в браузере.
- **На будущее:** `VITE_SUPABASE_URL` = ПОЛНЫЙ `https://<ref>.supabase.co` (с протоколом), не голый реф.
- **⏳ Осталось:** интерактивный smoke в браузере (вход нутрициолога → создать клиента →
  чат-аналитика → отчёт PDF/TXT).

### Деплой 22 июня 2026 (продакшен)
- **Бэкенд** (FastAPI/Docker→uvicorn) на Render: https://nutritionist-agent-gvxp.onrender.com — `/health` ок.
- **Фронт** (React Static Site) на Render: https://nutritionist-agent-1-ljzi.onrender.com.
- Чинили деплой: requirements ResolutionImpossible (ptb 20.7 httpx ↔ supabase → ptb>=21; убран
  streamlit/protobuf-конфликт); Dockerfile→uvicorn; SPA deep-link → `404.html`=index.html на сборке.
- CORS_ORIGINS бэкенда = URL фронта (ок); Supabase Auth Site URL/Redirect = URL фронта (ок).
- OpenAI + Anthropic **оплачены** → ИИ полноценный. Миграции 001–008 применены (проверено интроспекцией).

### Сессия 22 июня 2026 — кабинет нутрициолога: 3 панели, аналитика-RAG, отчёты, настройки
- **Раскладка в 3 панели** (`NutritionistShell`): слева инструменты, центр — рабочая
  область, справа — постоянный чат; ресайз границы центр↔чат и скрытие чата (localStorage).
- **Создание клиента со статусами** (миграция `007_client_paid_until.sql`): оплата
  (active/inactive), режим базовый/полный → client_status (тариф из статуса), `paid_until`.
  Гейт входа уже работал (`check_web_access`). API `/clients` + `invite_client_account` расширены.
- **Фильтры реестра** по столбцам (имя/статус/оплата/цель) + столбец «Оплачено до»;
  локализация значений статусов/оплаты (`registry.status_value`/`payment_value`/`access_value`).
- **Индикатор истечения тарифа** (`expiry.ts`): в реестре (цвет + «ещё N дн./истёк»),
  в «Алертах» секция «Истекает тариф» (paid_until ≤ сегодня+2). Telegram-уведомление за 2 дня — n8n (позже).
- **Блок 2: агент наполняет центр** — директива вида в ответе агента
  (`orchestrator._build_view_directive`, `state.view`): клиент→карточка, аналитика→панель.
  `ClientCard` переведён на самозагрузку по `clientId`. Мини-дашборд `AnalyticsPanel` (воронка+счётчики).
- **Аналитика — RAG-конвейер** (`analytics_agent`, v1: клиент+vector, web позже): план(Groq) →
  контекст беседы → данные клиента(SQL/JSON) → vector (client_documents+knowledge_base) →
  синтез(analytics LLM) → `state.analysis` {title, markdown, charts}. Панель «Аналитика» рисует
  markdown (`react-markdown`) + графики из реальных данных БД.
- **Карточка клиента**: лента «События» прокручиваемая (до 50), алерты подсвечены, галка «Только алерты».
- **Отчёты** (миграция `008_client_reports.sql`): `agents/nutritionist/reports.py` (LLM по шаблону),
  эндпоинты `/nutritionist/report(-types)`; `ReportsCard` — генерация→правка→сохранение→выгрузка
  PDF (печать браузера, кириллица) + TXT + список. Шаблон формы Екатерины Юровой в
  `prompts/nutritionist/reports/recommendations_for_clients.md`.
- **Настройки (перенос со Streamlit)**: каталог показателей + пороги алертов + доверенные
  источники + llm_config (system_settings под RLS) + редактор промптов (эндпоинты
  `/nutritionist/prompt(s)`). Компоненты в `features/nutritionist/settings/`.
- **Применены миграции** Supabase: 007, 008.
- **Коммит + PR:** ветка `stage6-utils` → `main`, PR #1.
- **Пост-PR фиксы (22 июня):**
  - **pgvector-формат:** `query_embedding`/`embedding` в RPC `match_*` и в INSERT чанков
    передаются как pgvector-литерал `'[...]'` (`queries._vector_literal`) — PostgREST не
    кастует JSON-массив → vector. Конфликт сервис↔БД устранён (проверить нельзя, пока OpenAI 429).
  - **Dockerfile:** точка входа `uvicorn api.main:app` на `$PORT` (вместо Streamlit/8501);
    requirements актуализированы (Streamlit → legacy).
  - **analytics_system.md → тема-адаптивный:** анализ строится вокруг вопроса; при отсутствии
    данных по теме — честно «данных нет: …» + что собрать, без generic-«весовой» простыни.
- **Среда (блокеры качества):** OpenAI ключ — 429 insufficient_quota (эмбеддинги/vector не
  работают); Claude — без кредитов (синтез на резерве Groq/Gemini). Векторный фикс не проверен.
- **Не сделано (по плану позже):** web-шаг аналитики и анализ группы клиентов (ждут Claude);
  аудит правок настроек из фронта; PDF одним кликом (jsPDF+кириллический шрифт).

### Сессия 20 июня 2026 — кабинет клиента (React) + отказоустойчивость LLM
- **Запуск локально:** FastAPI (`api/`) :8000 + Vite (`frontend/`) :5173 в Codespaces;
  порт 8000 — public (кросс-доменный fetch фронта к API); окружение API из `.env` без load_dotenv.
- **Загрузка анализов:** миграция `005_storage_client_documents.sql` (бакет `client-documents`
  + storage-RLS); санитизация ключей Storage (кириллица/скобки ломали «Invalid key»).
- **Ассистент видит данные клиента:** `queries.get_latest_measurement/get_recent_lab_results`,
  загрузка в контекст (`orchestrator.load_context_node`), общий `build_health_lines`
  (вес + анализы с динамикой) в dialog/nutrition; промпты разрешают озвучивать СВОИ данные
  (факты + лёгкая трактовка, без диагнозов). Вопросы о своих данных → роутинг на Groq.
- **Взаиморезервирование LLM** (`utils/llm.py`): `TASK_FALLBACK_CHAINS` + перебор кандидатов;
  при сбое модели автопереключение (Claude→Groq→Gemini; vision→Claude), иначе
  `LLMUnavailableError` + «подождите и повторите». Claude без кредитов → работает резерв.
- **UX чата:** авто-ресайз поля ввода; панель чата фиксирована на экране (внутренний скролл)
  и шире на 30% за счёт центральной панели (`ClientShell` 300/1fr/468).
- **Per-client показатели анализов (реализовано):** миграция `006_tracked_lab_indicators.sql`
  (колонка `client_profiles.tracked_lab_indicators` JSONB); редактор нутрициолога
  `LabIndicatorsManager` (вкладка «Показатели анализов»: клиент → key/label/unit/нормы/порядок,
  каталог из `lab_indicators_top`); клиентский график рисует только выбранное (с полосой нормы
  ReferenceArea + плейсхолдер); ассистент использует нормы для лёгкой трактовки.
  Ввод значений анализов — форма `LabValuesForm` в той же вкладке (insert в `lab_results`,
  source='nutritionist', + список последних значений).
- **Панель алертов нутрициолога (реализовано):** вкладка «Алерты» (первая) — `AlertsPanel`
  читает `client_events` (severity ∈ medium/high/critical) под RLS + join clients(name);
  фильтры окно/severity, цвет по уровню. Добавлен персист `weight_increase` как severity-события
  в `diary_agent` (раньше в панель не попадал).
- **Реестр + карточка клиента (реализовано):** вкладка «Реестр клиентов» — `Registry` (список из
  clients + профиль, создание клиента) → клик открывает `ClientCard`: профиль (цель/пол/возраст/
  вес/аллергии/хронические/ограничения), план питания + ЗОЖ, задачи, график веса и анализов
  (с нормами), последние события, редактируемые заметки нутрициолога (update clients под RLS).
  Переиспользует хуки client/queries; новые — features/nutritionist/queries.ts.
- **Чат нутрициолога с агентом (реализовано):** вкладка «Ассистент-агент» — `NutritionistChat`
  шлёт запросы в `/nutritionist/query` (analytics + management с двухшаговым подтверждением;
  pending_action хранится на бэке по nutritionist_id). Исправлен баг: analytics_agent и
  management_agent звали `call_llm(task_type='analysis')` — нет такого типа → теперь 'analytics'
  (с взаимозаменой Claude→Groq/Gemini). Проверено: сводка и создание задачи отвечают на Groq.
- **Редактор планов/задач (реализовано):** в карточке клиента — `TaskEditor` (список + создание
  задач + смена статуса done/cancel) и `PlanEditor` (история версий + создание нового плана:
  деактивируем старый активный ДО вставки нового — EXCLUDE «один активный план», триггер
  деактивации AFTER INSERT; version проставляет триггер). plan_json: description/target_calories/
  restrictions, supplements_json.items. Всё под RLS (nutritionist); логика проверена на БД.
- **Редактор ЗОЖ-плана (реализовано):** `WellnessEditor` в карточке клиента — редактирует
  последнюю запись `wellness_plans` (update по id) либо создаёт первую (insert): сон/активность/
  восстановление/стресс/заметки. Под RLS; проверено на БД.

## Выполнено

### Инфраструктура
- [x] Репозиторий GitHub: viktorsula/nutritionist-agent
- [x] Среда разработки: GitHub Codespaces → Claude Code
- [x] Деплой на Render: nutritionist-agent-gvxp.onrender.com
- [x] Базовый app.py на Streamlit задеплоен
- [x] .env.example — шаблон всех ключей
- [x] .gitignore — защита секретов
- [x] Supabase проект создан: nutritionist-agent (FREE tier)

### База данных Supabase — ✅ ПОЛНОСТЬЮ ГОТОВА (v1.3)
- [x] **Блок 1:** users, clients, client_profiles, wellness_plans
- [x] **Блок 2:** conversations, client_events
- [x] **Блок 3:** nutrition_plans (версионирование + триггеры), tasks
- [x] **Блок 4:** notification_schedule, audit_logs, system_settings
- [x] **Блок 5:** document_metadata, knowledge_base, client_documents (pgvector)
- [x] **VIEW:** client_registry_view (SECURITY INVOKER)
- [x] **Триггеры:** trg_plan_version, trg_deactivate_old_plans
- [x] **Индексы:** включая ivfflat для pgvector
- [x] **Security Advisor:** 0 errors, 0 warnings ✅
- [x] **docs/schema.sql** — актуализирован до v1.3
- [x] **Миграция v1.2 → v1.3** — успешно выполнена (8 июня 2026)

### Код Python
- [x] **database/client.py** — подключение к Supabase готово
- [x] **database/models.py** — все 14 моделей готовы, синхронизированы с БД v1.3
- [x] **database/queries.py** — 43 функции реализованы (добавлена get_setting() для llm_config)
- [x] **business_rules/** — детерминированный слой готов ✅
  - [x] access_rules.py — проверка доступа, 2 режима (full_program, ai_support)
  - [x] medical_rules.py — 5 типов алертов + маршрутизация к нутрициологу
  - [x] notification_rules.py — timezone-aware проверки расписания
- [x] **utils/** — базовые модули готовы ✅
  - [x] llm.py — мультипровайдерный LLM клиент (Groq, Claude, Gemini), 6 task_type, Вариант 3 (гибридный)
  - [x] helpers.py — вспомогательные функции (структура готова, большинство — TODO для Этапа 6)
- [x] **prompts/** — система управления промптами готова ✅
  - [x] __init__.py — загрузка из БД (приоритет) → файлы (fallback)
  - [x] client/dialog_system.md — промпт для диалога с клиентом
  - [x] nutritionist/analytics_system.md — промпт для аналитики
- [x] **agents/** — базовая инфраструктура готова ✅
  - [x] router.py — входной маршрутизатор (роль → ветка агентов) + обработка observer
  - [x] client/state.py — ClientState TypedDict для LangGraph
  - [x] client/orchestrator.py — LangGraph граф (5 узлов: load_context → check_alerts → dialog_agent → format_response → save_to_db)
  - [x] client/dialog_agent.py — работающий агент диалога (использует Groq llama-3.3-70b)
  - [x] nutritionist/orchestrator.py — заглушка (направление к
   веб-интерфейсу)
- [x] **app.py** — веб-интерфейс обновлён ✅
  - [x] Интеграция с agents/router.py (вместо прямого ChatGroq)
  - [x] Поддержка 3 ролей: client ✅, nutritionist ✅, observer (зарезервирован)
  - [x] Ветка клиента: чат работает через dialog_agent
  - [x] Ветка нутрициолога: заглушка с табами (Реестр, Аналитика, Настройки)
- [x] **Миграции БД** — создана система миграций ✅
  - [x] docs/migrations/001_add_observer_role.sql — добавить observer в users.role
  - [x] docs/migrations/README.md — инструкции по применению
  - [x] docs/schema.sql обновлён (v1.3.1 — observer включён)
- [x] **telegram/** — Telegram бот готов ✅
  - [x] bot.py — основной бот (python-telegram-bot)
  - [x] commands.py — /start, /help, /status (работают)
  - [x] handlers.py — текст через route_message(), фото/голос (заглушки для Этапа 6)
  - [x] test_bot.py — тесты команд и обработчиков
  - [x] README.md — документация

### Этап 6 — Часть A (ветка клиента) — ✅ КОД ГОТОВ (на ветке stage6-utils)
- [x] **requirements.txt** — +openai (ada-002 + Whisper); убраны chromadb/sentence-transformers;
      модернизирован LangGraph (langgraph>=1.0, langchain-core>=0.3, сняты langchain*/langsmith-пины)
- [x] **docs/migrations/002_add_vector_search.sql** — RPC match_knowledge_base / match_client_documents (cosine, pgvector)
- [x] **database/queries.py** — обёртки search_knowledge_base / search_client_documents (supabase.rpc)
- [x] **utils/knowledge.py** — get_embedding (OpenAI ada-002, 1536) + семантический поиск + сборка контекста
- [x] **utils/vision.py** — analyze_image + analyze_food_plate (приоритет: состав/ингредиенты/форма; КБЖУ вторично) + extract_ingredient_names
- [x] **utils/voice.py** — transcribe_voice (OpenAI Whisper)
- [x] **utils/web_access.py** — build_web_search_tool() (серверный инструмент Claude web_search) + allowed_domains из trusted_sources [обновлено 19 июня: Tavily убран]
- [x] **agents/client/food_analysis.py** — общий анализ состава против рациона (DRY): analyze_against_plan / determine_food_routing / highest_severity
- [x] **agents/client/vision_agent.py** — фото еды: 3 исхода, анализ против рациона, событие calories_logged, уведомление нутрициолога при отклонениях
- [x] **agents/client/diary_agent.py** — дневник текстом: ветки meal/weight/wellbeing/other; события weight_logged/bad_wellbeing/calories_logged
- [x] **agents/client/nutrition_agent.py** — вопросы о рационе (Claude); знания: knowledge_base + client_documents (pgvector) + веб через серверный инструмент Claude web_search с allowed_domains из system_settings.trusted_sources
- [x] **prompts/client/** — vision_system.md, diary_system.md, nutrition_system.md
- [x] **agents/client/orchestrator.py** — роутинг: ingest(голос→текст) → load_context → route → [vision|diary|nutrition|dialog] → format_response → save_to_db; удалён check_alerts_node
- [x] **Фиксы:** save_to_db (insert_conversation→save_conversation + _sanitize_metadata); поля state route/food_items

### Этап 6 — Часть A — Шаги 3–4 — ✅ ЗАВЕРШЕНО (18 июня 2026)
- [x] **Шаг 3:** tg_bot/handlers.py — фото и голос подключены к графу
  - фото: скачивание наибольшего размера → `metadata['image_bytes']` + `mime_type='image/jpeg'`, caption → message, `message_type='photo'` → vision
  - голос: скачивание .ogg → `metadata['audio_bytes']` + `audio_name`, `message_type='voice'`, транскрипция в узле ingest оркестратора (Whisper)
  - вынесена общая логика `_ensure_registered()` + `_dispatch_to_router()` (DRY для text/photo/voice)
- [x] **Шаг 4:** тесты + прогон
  - tg_bot/test_bot.py: переведён на `IsolatedAsyncioTestCase` (раньше async-тесты не исполнялись), +4 теста фото/голоса → 10/10 ✅
  - agents/test_agents.py: 7/7 ✅
- [x] **Фикс коллизии имён:** пакет `telegram/` → `tg_bot/` (затенял библиотеку python-telegram-bot; `from telegram.ext` ломался). Обновлены импорты в test_bot.py + README. `bot.py`/`commands.py`/`handlers.py` используют относительные импорты — не тронуты.
- [x] **Фикс:** убран мёртвый импорт `get_user_by_id` в tg_bot/commands.py (ломал загрузку пакета)

## В процессе

### Код (Этапы по ТЗ v1.3)
- [x] **Этап 2:** database/ — ЗАВЕРШЁН ✅
- [x] **Этап 3:** business_rules/ — ЗАВЕРШЁН ✅
- [x] **Этап 4:** utils/ — ЗАВЕРШЁН (базовые модули) ✅
- [x] **Этап 5:** agents/ + prompts/ — ЗАВЕРШЁН (базовая инфраструктура) ✅
- [x] **Этап 7 (часть 1):** app.py — ЗАВЕРШЁН (веб-интерфейс интегрирован с agents/) ✅
- [x] **Этап 7 (часть 2):** telegram/bot.py — ЗАВЕРШЁН (базовый функционал) ✅
- [x] **Этап 6 Часть A (клиент):** vision/diary/nutrition агенты + utils + роутинг + Telegram фото/голос + тесты — ЗАВЕРШЕНО ✅
- [x] **Этап 6 Часть B (нутрициолог):** analytics_agent + management_agent — ЗАВЕРШЕНО ✅
  - state.py — NutritionistState + helpers (thread нутрициолога, pending_action)
  - orchestrator.py — реальный LangGraph граф: parse_request → [analytics|management|help] → format_response → save_to_db (заменил заглушку; общий для Telegram и web)
  - parse_request — классификатор intent (Groq) + резолв клиента по имени + детект подтверждения/отмены
  - analytics_agent.py — read-only анализ клиента/базы (Claude), промпт analytics_system.md
  - management_agent.py — запись через ДВУХШАГОВОЕ ПОДТВЕРЖДЕНИЕ (pending_action в conversations.metadata_json); действия: create_task / create_nutrition_plan / update_client_status / add_trusted_source; всё с created_by='nutritionist' + write_audit_log
  - prompts/nutritionist/management_system.md — разбор команды в строгий JSON
  - тесты: agents/nutritionist/test_nutritionist.py — 13/13 ✅
- [x] **Этап 8:** app.py (полный интерфейс нутрициолога) — ЗАВЕРШЕНО ✅
  - [x] Шаг 1: Реестр + Аналитика — web/nutritionist.py (render_registry / render_analytics);
        queries.get_client_registry() (из client_registry_view); AI-анализ через analytics_node
  - [x] Шаг 2: Настройки — render_settings(): пороги алертов (JSON), trusted_sources (список +
        добавление/удаление), редактор промптов (list/load/save_prompt), llm_config (JSON);
        запись через update_system_setting + write_audit_log
  - [x] тесты web/test_nutritionist_views.py — 10/10 ✅
- [x] **Этап 9:** monitoring/langfuse.py — ЗАВЕРШЕНО ✅
  - monitoring/langfuse.py — обёртка LangFuse: trace_llm_call / is_enabled / flush; graceful no-op без SDK/ключей, трейсинг никогда не роняет вызов LLM
  - utils/llm.py — call_llm трейсит каждый вызов (тайминг + успех/ошибка) через _trace(); удалена старая закомментированная заготовка
  - единая точка: все агенты (клиент + нутрициолог) трейсятся автоматически
  - тесты monitoring/test_monitoring.py — 7/7 ✅

## Ключевые решения принятые в ходе разработки
- **wellness_plans** — отдельная таблица "как жить" vs "что есть" (зафиксировано в ТЗ v1.3)
- **supplements_json** — отдельное поле в nutrition_plans (не внутри plan_json)
- **Индивидуальные пороги алертов** — в client_profiles (переопределяют system_settings)
- **created_by = 'nutritionist' only** — агент не назначает задачи и планы, только советует
- **5 типов алертов:** weight_increase, food_incompatible, food_forbidden, no_response, bad_wellbeing
- **Триггеры:** SECURITY INVOKER + SET search_path (прошли Security Advisor)
- **VIEW:** SECURITY INVOKER (безопасность, RLS работает корректно)
- **timestamp → message_timestamp/action_timestamp** — избежание конфликта с зарезервированным словом PostgreSQL
- **queries.py:** 43 функции охватывают все сценарии из ТЗ v1.3 (раздел 12)
- **llm.py Вариант 3 (гибридный):** task_type (из БД) ИЛИ provider+model (эксперименты) — максимальная гибкость
- **llm_config в system_settings:** нутрициолог сможет менять модели через веб-интерфейс (v1.1)
- **Система промптов (3 уровня):** файлы .md (MVP) → БД (v1.1) → веб-редактор (v1.1+) — приоритет БД над файлами
- **LangGraph для оркестрации:** стандарт мультиагентных систем, граф: load_context → check_alerts → agent → format → save
- **ClientState TypedDict:** полное состояние агента (входные данные, контекст, алерты, результаты, метаданные)

## TODO (вне текущего фронта)
- **Telegram-резолв роли:** `agents/router.py:get_user_info()` зовёт несуществующие
  `queries.get_user()`/`queries.get_user_by_telegram_id()` → Telegram-путь возвращает
  «user_not_found». Веб обходит через `database/auth.py`. Починить: добавить
  `get_user_by_telegram_id`/`get_user_by_auth_id` в `queries.py`.

## Следующий шаг
**Дорожная карта ТЗ v1.3 (Этапы 1–9) — ПОЛНОСТЬЮ ЗАВЕРШЕНА.** ✅
Остаётся подготовка к продакшену перед слиянием `stage6-utils` → `main`:
1. Применить миграции в Supabase (001 observer, 002 vector search)
2. Прописать ключи в Render (OPENAI / GOOGLE / TELEGRAM_BOT_TOKEN / LANGFUSE_*); включить web search в Claude Console
3. Живой smoke-тест (сообщение клиента + запрос нутрициолога + фото/голос)
4. PR `stage6-utils` → `main` (автодеплой выкатит рабочую версию)

## Важно перед запуском
⚠️ **Установить зависимости:** `pip install -r requirements.txt` (новое: openai; tavily удалён)
⚠️ **Выполнить миграции в Supabase (SQL Editor):**
- `docs/migrations/001_add_observer_role.sql` — роль observer — ⏳ ожидает
- `docs/migrations/002_add_vector_search.sql` — RPC векторного поиска — ⏳ ожидает
⚠️ **Ключи окружения:** OPENAI_API_KEY (эмбеддинги+Whisper), GOOGLE_API_KEY (vision); веб-поиск — серверный инструмент Claude web_search (ключ не нужен, включить в Console)
⚠️ **Пред­существующий конфликт:** streamlit 1.32.0 ↔ protobuf 5.29.6 — разобрать перед запуском веба

## Ключевые решения Этапа 6 (14 июня 2026)
- **Эмбеддинги:** OpenAI text-embedding-ada-002 (1536 = схема, миграция БД не нужна)
- **Голос:** перенесён в Часть A (делаем сразу), Whisper через openai
- **Vision приоритет:** состав/ингредиенты/форма приготовления первичны, КБЖУ вторично (для контроля рациона)
- **DRY:** общий food_analysis.py для vision и diary
- **Знания nutrition_agent:** knowledge_base + client_documents (pgvector) + веб через серверный инструмент Claude web_search с allowed_domains из system_settings.trusted_sources (редактирует нутрициолог/агент по его команде)
- **[19 июня] Веб-поиск: Tavily → Claude web_search.** ТЗ механизм не задавало; Tavily был выбором Этапа 6. Переведено на встроенный серверный инструмент Claude (web_search_20250305): минус зависимость и ключ, контроль источников сохранён через allowed_domains. Требует включения web search в Claude Console.
- **Роутинг:** photo→vision (без LLM), текст→Groq-классификатор (diary|nutrition|dialog); check_alerts_node убран (алерты формируют агенты)
- **LangGraph модернизирован:** код использует только StateGraph/END → апгрейд до langgraph 1.x безопасен