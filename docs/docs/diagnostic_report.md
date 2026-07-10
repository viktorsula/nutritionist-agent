# Диагностика агента-нутрициолога — отчёт (в работе)

> **СТАТУС: ЧАСТИЧНО ГОТОВ, аудит идёт последовательно по разделам.**
> Первый прогон (мультиагентный) был прерван на балансе API — успел только Раздел 2.
> Второй прогон идёт последовательно, субагентами на **Claude Sonnet**, раздел за разделом
> с подтверждением владельца после каждого. Находки помечены уровнем уверенности:
> **ПОДТВЕРЖДЕНО** (проверено grep'ом по всему репо) / **ВЕРОЯТНО** (код-путь подтверждён,
> живой прогон не делался).
>
> Прогресс разделов:
> - Раздел 1 (потоки данных) — ✅ готов (2026-07-10)
> - Раздел 2 (бизнес-логика) — ✅ закрыт (по первому прогону, ниже)
> - Раздел 3 (совместимость) — ✅ готов (2026-07-10)
> - Раздел 4 (производительность) — ⏳ в очереди
> - Раздел 5 (безопасность) — ⏳ в очереди
> - Раздел 6 (мониторинг) — ⏳ в очереди
> - Итоговая оценка готовности в % — после всех разделов
>
> Дата обновления: 2026-07-10.

---

# РАЗДЕЛ 1 — Анализ потоков данных ✅

## 🔴 Критические проблемы

### 1.1 Ключ `deviations` vs `alerts` — текст алерта по еде теряется (веб и Telegram)
- Пишется: `agents/client/intake_store.py:107` — `payload={..., "deviations": [{type,severity,message}...]}` внутри события `calories_logged`.
- Читается (не совпадает): `frontend/src/features/nutritionist/AlertsPanel.tsx:99` ищет `alerts`; `utils/notify.py:56` ищет `message/reason/answer`.
- `grep deviations` — единственное вхождение — само место записи; ключ нигде не читается.
- **Последствие:** при найденном `food_forbidden`/аллергене (вплоть до critical) событие уходит нутрициологу с верной severity, но **без текста деталей** — панель и пуш показывают «🔴 calories_logged» без «что нашли».
- **ПОДТВЕРЖДЕНО.**

### 1.2 `_check_food_forbidden` читает несуществующее верхнеуровневое поле
- `business_rules/medical_rules.py:243` — `plan.get('restrictions')`, но ограничения лежат только в `plan_json.restrictions` (schema.sql, `nutrition_plans` без колонки `restrictions`).
- Тот же класс бага уже чинили в `agents/client/agent_orchestrator.py:357` (`_plan_view` с фолбэком на `plan_json`), но в medical_rules не пофикшено.
- **Последствие:** алерт `food_forbidden` (один из 5 в CLAUDE.md) **не может сработать никогда**.
- **ПОДТВЕРЖДЕНО.**

### 1.3 `_check_bad_wellbeing` вызывает `get_client_events(event_type=...)` — TypeError на каждом вызове
- `business_rules/medical_rules.py:345` передаёт `event_type=`, которого нет в сигнатуре `get_client_events(client_id, severity=None, limit=100)` (`database/queries.py:732`). Исключение гасится общим `except` в `check_medical_alerts`.
- Даже с фиксом: ищет `wellbeing_checkin`, а реально пишется `bad_wellbeing`/`wellbeing_logged` (`intake_store.py:198`). `wellbeing_checkin` не пишется нигде.
- Реальный алерт живёт независимым путём в `intake_store.py:196`, минуя medical_rules — поэтому баг скрыт.
- **ПОДТВЕРЖДЕНО.**

### 1.4 `_check_food_incompatible` — заглушка, всегда `None`
- `business_rules/medical_rules.py:277` — TODO/`return None`. `food_incompatible` (5-й задокументированный алерт) не создаётся никогда.
- **ПОДТВЕРЖДЕНО.**

### 1.5 Пороги алертов из «Настроек» нутрициолога никогда не применяются
- UI пишет в `system_settings.alert_thresholds`, код читает несуществующие ключи `weight_increase_threshold_kg` (`medical_rules.py:197`) и `no_response_threshold_hours` (`:293`, `api/scheduler.py:591`).
- Индивидуальные `client_profiles.custom_alert_thresholds` (`medical_rules.py:195`) **нигде не пишутся** (grep — ноль write).
- **Последствие:** всегда хардкод 1.0 кг / 48 ч, настройки нутрициолога молча игнорируются.
- **ПОДТВЕРЖДЕНО.**

### 1.6 `notification_schedule` — таблица без единого write-пути (пустой запрос)
- Читается: `api/scheduler.py:100` (`run_due_notifications` в `run_scheduler_pass`) через `get_notifications_due_now()`.
- Пишется: нигде (`create/update_notification_schedule` не вызываются; во фронте таблицы нет).
- **Последствие:** джоб всегда работает по пустой выборке; фича подменена таблицей `reminders` (миграции 013–016), старый код не убран.
- **ПОДТВЕРЖДЕНО.**

### 1.7 `business_rules/notification_rules.py` — мёртвый модуль + рассинхрон схемы
- Экспортируется в `__init__.py`, но нигде не вызывается. Читает несуществующие поля: `is_enabled` (реально `is_active`), `allowed_start_time`/`allowed_end_time` (в `notification_schedule` таких колонок нет).
- **ПОДТВЕРЖДЕНО.**

## 🟡 Логические дыры

1. **`complete_task()` не вызывается нигде** (`database/queries.py:1046`) → задачи невозможно закрыть, растут бесконечно (`get_pending_tasks`, `client_registry_view.open_tasks`). **ПОДТВЕРЖДЕНО.**
2. **`get_overdue_tasks()` не используется** (`:1090`) → статус `overdue` никто не проставляет. **ПОДТВЕРЖДЕНО.**
3. **`client_metrics` пишутся, но ряд значений не читается**: `insert_client_metric` (`intake_store.py:261,286`) пишет; `get_client_metrics()` (`:439`) не вызывается, во фронте нет; `has_client_metric_since` — только булев гейт. → клиент логирует показатель, его никто не видит. **ПОДТВЕРЖДЕНО.**
4. **Telegram-пуш**: `_EVENT_LABEL` (`utils/notify.py:23`) без `calories_logged/meal_not_reported/reminder_unanswered/water_logged` → сырой event_type; их payload без `message/reason` → «Детали» пустые. **ПОДТВЕРЖДЕНО.**
5. **i18n-метки `food_forbidden`/`food_incompatible`** (`frontend/src/i18n.ts:263`) декоративны — эти строки как отдельные события не создаются. **ПОДТВЕРЖДЕНО.**

## 🔵 Мёртвые блоки

| Функция / поле | Файл:строка | Комментарий |
|---|---|---|
| `audit_logs` — только запись, нет чтения | пишется в `api/main.py` (7+), `management_agent.py`, `database/auth.py:229` | читается нигде — ПОДТВЕРЖДЕНО |
| `trigger_alert_webhook()` | `database/queries.py:1599` | n8n-вебхук, не вызывается |
| `get_clients_with_inactive_payment()` | `:1561` | не вызывается |
| `create/update_wellness_plan` | `:1378,1408` | фронт пишет напрямую (WellnessEditor) — мёртвый Python |
| `create/update_notification_schedule` | `:824,1524` | см. 1.6 |
| `get_plan_history()` | `:1009` | фронт читает напрямую |
| `get_knowledge_base_chunks`/`get_client_document_chunks` | `:559` | не вызываются |
| `get_all_system_settings()` | `:523` | настройки читаются по ключу |
| `get_client_metrics()` | `:439` | см. дыру №3 |

## ✅ Что работает хорошо (потоки данных)
- `calories_logged`/`water_logged` → `get_nutrition_daily` → `/nutrition/daily`: ключи payload побайтово совпадают.
- `weight_increase`: пишется/читается согласованно (веб + Telegram, ключ `message`).
- `bad_wellbeing`: рабочий путь через `intake_store.py` согласован (несмотря на сломанный дубль в medical_rules).
- `reminders`/`reminder_occurrences`: полный CRUD + контроль ответа.
- `measurements`/`lab_results`: имена колонок согласованы, запись/чтение сходятся.

**Ключевой вывод:** большая часть `business_rules/medical_rules.py` мертва/сломана (1.2–1.5), реальные алерты идут в обход через `intake_store.py`; даже рабочие алерты теряют текст из-за `deviations`/`alerts` (1.1).

---

# РАЗДЕЛ 2 — Анализ бизнес-логики ✅ (закрыт по первому прогону)

> Находки первого (мультиагентного) прогона; не проходили адверсариальную верификацию.
> По решению владельца раздел считается закрытым. Часть находок пересекается и уточнена
> в Разделе 1 (bad_wellbeing, food_incompatible, food_forbidden).

### 🔴 2.1 Оркестратор не предупреждает клиента об аллергене/запрещённом продукте в съеденной еде
`agents/client/agent_orchestrator.py:589` — `_persist`/`log_meal` возвращает модели только «записано: meal»; про найденный аллерген (severity=critical) модель не узнаёт, `_finalize` не префиксирует критические алерты (в отличие от графа с `format_client_message`). Асимметрия: `log_wellbeing` (`:625`) дописывает «нутрициолог уведомлён», `log_meal` — нет.
- **Последствие:** клиент сообщает, что съел аллерген → «Записал ✅» без предупреждения; предупреждение доходит только до нутрициолога с задержкой. Прямой риск здоровью.
- **Решение:** вернуть модели алерты из `state['alerts']` или детерминированно префиксировать критические алерты в `_finalize`.

### 🟡 2.2 Safety-алерты в оркестраторе срабатывают только если модель сама вызвала `log_*`
`agents/client/agent_orchestrator.py:285` — детект (bad_wellbeing/weight/аллерген) висит на решении Claude вызвать `log_*`. Нет независимого детерминированного скана. Сценарий: «мне плохо, кружится голова» без вызова `log_wellbeing` → событие не создаётся, пуша нет.

### 🟡 2.3 Проверка аллергий на стороне ПРЕДЛОЖЕНИЙ еды — только через промпт
`agents/client/agent_orchestrator.py:258` — при генерации меню/рецепта/совета по фото холодильника нет детерминированного гейта против аллергенов (только системный промпт). Риск: модель предлагает блюдо с аллергеном.

### 🟡 2.4 `_load_base_context` глушит ошибку БД и продолжает без профиля/аллергий
`agents/client/agent_orchestrator.py:186` — один `try/except` на всю загрузку; при сбое ход продолжается на пустом профиле («аллергий нет»). Тихая деградация безопасности. Решение: safe-fail вместо советов.

### 🟡 2.5 / 🔵 2.6 `food_incompatible` заглушка + `_check_bad_wellbeing` рассинхрон
См. уточнённые формулировки в Разделе 1 (1.4, 1.3).

### ✅ Контроль доступа/оплаты выполнен ДО LLM
`agents/router.py:189` — `route_to_client` зовёт `check_access` до `process_client_message`; порядок корректный.

---

# РАЗДЕЛ 3 — Анализ совместимости ✅

## 🔴 Критические проблемы

### 3.1 Резерв, назначенный нутрициологом через UI, молча ломает tool-calling оркестратора
- `call_llm()` безусловно вырезает `tools`/`tool_handlers`/`max_tool_iterations` для `provider != 'claude'` (`utils/llm.py:320`).
- Код-дефолт держит резерв оркестратора пустым намеренно (откат на граф выше — `agents/router.py:249`), но `resolve_fallback_chain()` (`utils/llm.py:463`) читает `system_settings.llm_config[task_type]['fallbacks']` из БД **с приоритетом над кодом**. Ни `save_setting` (`api/main.py:229`, upsert без валидации), ни фронт-валидация не запрещают добавить groq/gemini в резерв `orchestrator`/`nutritionist_orchestrator`.
- При таком резерве и одном сбое Claude → `call_llm` отработает через groq **без tools**: модель ответит текстом, не вызвав ни один инструмент (log_diary/log_weight/записи нутрициолога), при этом `success=True`. `fallback_used` (`:344`) нигде не читается; адаптеры используют `tool_calls` лишь для логов (`agent_orchestrator.py:305`, `agent_adapter.py:197`).
- **Последствие:** тихая потеря записи данных при внешне успешном ответе.
- **Решение:** whitelist только claude для task_type с tools, либо проверять `fallback_used` и откатываться на граф, либо валидировать резерв на фронте/бэке.
- **ПОДТВЕРЖДЕНО.**

## 🟡 Логические дыры

### 3.2 Формат сообщений для Gemini нарушает чередование ролей
`utils/llm.py:1062` — `role = 'user' if msg['role'] in ['user','system'] else 'model'`. При истории `[system, user, assistant, ...]` system-как-user + первый user дают два `user`-хода подряд без `model` → Gemini `generateContent` может вернуть 400. Бьёт по резервным цепочкам `dialog/summary/analytics/nutrition_analysis/planning`. Решение: схлопывать system в первое user-сообщение / мержить смежные роли. **ВЕРОЯТНО.**

### 3.3 Неизвестные типы Telegram молча игнорируются
`tg_bot/bot.py:51` — зарегистрированы только text/photo/voice+audio/document. Стикер/видео/video_note/геолокация/контакт → нет маршрута, бот не отвечает. Решение: catch-all `filters.ALL` в конец. **ПОДТВЕРЖДЕНО.**

### 3.4 `similarity_threshold` для pgvector везде дефолтный 0.0 — фильтра релевантности нет
`utils/knowledge.py:110` (дефолт 0.0); вызывающие не переопределяют (`nutrition_agent.py:119`, `analytics_agent.py:222`, `agent_adapter.py:369`, `agent_orchestrator.py:678`). → в контекст LLM попадают ближайшие чанки при любой близости, подписанные «Из базы знаний». Решение: код-дефолт 0.75–0.8. **ПОДТВЕРЖДЕНО.**

## 🟠 Совместимость/конфиг

### 3.5 Резервная цепочка `vision` — мёртвый код
`utils/llm.py:154`; `call_llm(task_type='vision')` не вызывается нигде — реальный vision идёт напрямую через `google.generativeai` в `utils/vision.py`, минуя резерв. Заявленный «резерв vision → Claude» не работает (не критично — есть локальные try/except). **ПОДТВЕРЖДЕНО.**

### 3.6 `finish_reason` не унифицирован
`utils/llm.py:769/1022/1097` — `stop`/`length` vs `end_turn`/`max_tokens`/`tool_use` vs `STOP`. Риск низкий (программно не ветвится). **ПОДТВЕРЖДЕНО.**

### 3.7 `get_client_by_telegram_id` через `.single()`
`database/queries.py:149` — защищено `telegram_id UNIQUE` (schema.sql:27), дубликат невозможен. Не баг, но при снятии constraint `.single()` с >1 строкой тихо вернёт `None`. **ПОДТВЕРЖДЕНО.**

## ✅ Что работает хорошо
- Унифицированный контракт ответа LLM (все 4 провайдера → `{content,model,provider,usage,finish_reason}`).
- Единая точка входа `route_message` (обходных вызовов нет; webhook и polling через один `build_application`).
- pgvector размерности согласованы сквозно (1536, строковый литерал `'[...]'` обходит баг PostgREST, ivfflat-индексы на месте).
- RLS согласован: бэкенд весь через `_service_client` (service_role), фронт под anon+RLS; поздние таблицы (`reminders`/`client_metrics`) deny-all, фронт ходит в них через бэкенд-эндпоинты. Утечек между клиентами не найдено.
- Ошибки провайдеров обрабатываются единообразно (`LLMUnavailableError`).
- Мультимодальность оркестратора не пересекается с багами 3.2/3.5.

---

## План исправлений (промежуточный, по разделам 1–3)

**СЕГОДНЯ (критично):**
1. 1.1 — привести чтение алертов еды к ключу `deviations` (или писать в `alerts`) — иначе алерты по еде без текста.
2. 3.1 — запретить нестандартный резерв для orchestrator/nutritionist_orchestrator (whitelist claude) или откат на граф при `fallback_used` с tools — иначе тихая потеря записи.
3. 2.1 / 2.4 — аллерген в съеденной еде доходит до клиента; safe-fail при сбое БД.

**НА ЭТОЙ НЕДЕЛЕ (важно):**
1. 1.5 — пороги алертов из настроек реально применять (ключи `alert_thresholds`, писать `custom_alert_thresholds`).
2. 1.2 / 1.3 / 1.4 — починить или убрать `_check_food_forbidden` / `_check_bad_wellbeing` / `_check_food_incompatible`.
3. 2.2 / 2.3 — детерминированный слой безопасности в оркестраторе.
4. 3.4 — порог similarity для pgvector.
5. 3.3 — catch-all для неизвестных типов Telegram.

**ПОТОМ (улучшения / тех-долг):**
1. 1.6 / 1.7 — убрать мёртвый `notification_schedule`-путь и `notification_rules.py`.
2. Дыры задач (complete_task/overdue), показ `client_metrics`, метки Telegram-пуша, декоративные i18n.
3. 3.2 (Gemini роли), 3.5 (мёртвый резерв vision), 3.6 (finish_reason).
4. Разобраться с `audit_logs` без чтения (нужен просмотр или убрать запись).

---

## Осталось проверить
- Раздел 4 — производительность (N+1, размер контекста LLM, синхронные блокировки)
- Раздел 5 — безопасность (секреты, изоляция клиентов, валидация входных данных)
- Раздел 6 — мониторинг (Langfuse, логирование except, audit_logs)
- Итоговая оценка готовности к реальным клиентам (%) — после всех разделов.
