# Миграции базы данных

Этот каталог содержит SQL миграции для обновления схемы БД в Supabase.

---

## 📋 СПИСОК МИГРАЦИЙ

> Детальные карточки ниже описывают только 001–006 (исторически). **Полный реестр всех
> миграций и их статус на проде — в таблице «Отслеживание статуса» ниже** + verify-SQL.

### **001_add_observer_role.sql**
- **Дата:** 10 июня 2026
- **Описание:** Добавление роли `observer` для продакшн-версии
- **Статус:** ✅ Применена (19 июня 2026)
- **Что делает:**
  - Удаляет старый constraint `users_role_check`
  - Добавляет новый с ролями: `nutritionist`, `client`, `observer`

### **002_add_vector_search.sql**
- **Дата:** 14 июня 2026
- **Описание:** RPC-функции семантического поиска по pgvector (Этап 6)
- **Статус:** ✅ Применена (19 июня 2026)
- **Что делает:**
  - `match_knowledge_base(query_embedding, match_count, similarity_threshold)` — cosine-поиск по базе знаний
  - `match_client_documents(query_embedding, p_client_id, match_count, similarity_threshold)` — поиск по документам клиента (с изоляцией по client_id)
  - Использует ivfflat-индексы (`<=>`, cosine), SECURITY INVOKER + search_path
- **Зависимость:** эмбеддинги OpenAI `text-embedding-ada-002` (1536), считаются в `utils/knowledge.py`

### **003_questionnaire_and_measurements.sql**
- **Дата:** 19 июня 2026
- **Описание:** Опросник онбординга + замеры тела + анализы (Фронт Фаза 1)
- **Статус:** ✅ Применена (19 июня 2026)
- **Что делает:**
  - `client_profiles.questionnaire_json` (JSONB) — полный опросник (33 вопроса)
  - таблица `measurements` — вес/шея/талия/бёдра во времени (графики динамики)
  - таблица `lab_results` — числовые показатели анализов (графики динамики)
  - `system_settings.lab_indicators_top` — до 10 показателей для дашборда (нутрициолог)
- **Порядок:** применять ДО 004 (RLS ссылается на новые таблицы)

### **004_rls_policies.sql**
- **Дата:** 19 июня 2026
- **Описание:** Row Level Security для веб-доступа клиентов (Фронт Фаза 1)
- **Статус:** ✅ Применена (19 июня 2026)
- **Что делает:**
  - функции-хелперы `app_user_role()` / `app_current_client_id()` / `app_is_nutritionist()` / `app_can_read_client()`
  - включает RLS на всех клиентских таблицах + политики
  - client видит/правит только свои данные; статус/оплату/роль менять НЕ может
  - nutritionist — полный доступ; observer — чтение; service_role RLS обходит
- **Зависимость:** требует 003 (таблицы measurements/lab_results); идемпотентна
- **После применения проверить:** клиент не видит чужие строки; смена своего статуса из браузера отклоняется

### **005_storage_client_documents.sql**
- **Дата:** 20 июня 2026
- **Описание:** Storage-бакет `client-documents` + RLS на `storage.objects` (загрузка анализов/документов из кабинета клиента и анкеты)
- **Статус:** ⏳ Требует выполнения
- **Что делает:**
  - создаёт приватный бакет `client-documents`
  - политики: клиент пишет/читает только свою папку `{client_id}/...`; нутрициолог — всё; observer — чтение; service_role обходит RLS
- **Зависимость:** требует хелперы из 004 (`app_is_nutritionist()`, `app_current_client_id()`, `app_user_role()`); идемпотентна
- **Зачем:** без бакета фронт падает с `Bucket not found` при загрузке анализов

### **006_tracked_lab_indicators.sql**
- **Дата:** 20 июня 2026
- **Описание:** per-client список показателей анализов для графика динамики (выбирает нутрициолог)
- **Статус:** ⏳ Требует выполнения
- **Что делает:**
  - `client_profiles.tracked_lab_indicators` (JSONB) — `[{key,label_ru,label_en,unit,ref_min,ref_max,order}]`
  - график клиента рисует только выбранные показатели (в порядке, с полосой нормы)
- **Зависимость:** 003 (lab_results), 004 (RLS — нутрициолог пишет в client_profiles); идемпотентна

---

## 🚀 КАК ПРИМЕНИТЬ МИГРАЦИЮ

### **Шаг 1:** Открой Supabase
1. Перейди на https://supabase.com
2. Войди в проект `nutritionist-agent`

### **Шаг 2:** Открой SQL Editor
1. В левом меню → **SQL Editor**
2. Нажми кнопку **"+ New query"** (или "+")

### **Шаг 3:** Выполни миграцию
1. Открой файл `001_add_observer_role.sql` в редакторе
2. Скопируй весь SQL код
3. Вставь в SQL Editor
4. Нажми **Run** (или Ctrl+Enter)

### **Шаг 4:** Проверь результат
Должен появиться результат проверки:
```
conname          | pg_get_constraintdef
-----------------+--------------------------------------------
users_role_check | CHECK (role IN ('nutritionist', 'client', 'observer'))
```

✅ Если видишь `observer` в списке — миграция успешна!

---

## ⚠️ В СЛУЧАЕ ОШИБКИ

### Ошибка: "constraint does not exist"
**Решение:** Это нормально, старого constraint может не быть.  
Выполни только второй шаг:
```sql
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('nutritionist', 'client', 'observer'));
```

### Ошибка: "constraint already exists"
**Решение:** Constraint уже существует.  
Сначала удали:
```sql
ALTER TABLE users DROP CONSTRAINT users_role_check;
```
Потом добавь новый.

---

## 📊 ОТСЛЕЖИВАНИЕ СТАТУСА МИГРАЦИЙ

После выполнения миграции отметь статус. **Эта таблица — единственный источник правды
по тому, что накатано на прод.** Держи её в актуальном состоянии: инцидент с миграцией 016
(7 июля 2026 — сохранение «Настройки уведомлений» падало с `PGRST204: followup_after_hours`)
случился именно потому, что реестр обрывался на 006 и 016 молча сочли применённой.

| Миграция | Дата выполнения | Статус | Примечания |
|----------|-----------------|--------|------------|
| 001_add_observer_role.sql | 19 июня 2026 | ✅ | Роль observer |
| 002_add_vector_search.sql | 19 июня 2026 | ✅ | RPC match_* (подтв. интроспекцией 25 июня) |
| 003_questionnaire_and_measurements.sql | 19 июня 2026 | ✅ | Анкета + measurements + lab_results |
| 004_rls_policies.sql | 19 июня 2026 | ✅ | RLS-политики |
| 005_storage_client_documents.sql | 7 июля 2026 | ✅ | Бакет client-documents + storage RLS (подтв. verify-SQL) |
| 006_tracked_lab_indicators.sql | — | ✅ | Per-client показатели анализов (фича живая) |
| 007_client_paid_until.sql | — | ✅ | clients.paid_until (гейт доступа по оплате живой) |
| 008_client_reports.sql | — | ✅ | Таблица client_reports (отчёты) |
| 009_conversation_summary.sql | — | ✅ | rolling-summary (подтв. интроспекцией 25 июня) |
| 010_telegram_link_token.sql | — | ✅ | Самопривязка Telegram (E2E пройден) |
| 011_seed_llm_config.sql | 30 июня 2026 | ✅ | Сидинг llm_config |
| 012_add_orchestrator_llm_config.sql | 7 июля 2026 | ✅ | orchestrator/nutritionist_orchestrator в llm_config (подтв. verify-SQL) |
| 013_reminders.sql | 3 июля 2026 | ✅ | Напоминания (Фаза 1) |
| 014_controlled_metrics.sql | 3 июля 2026 | ✅ | Контролируемые показатели |
| 015_reminder_response_control.sql | 3 июля 2026 | ✅ | Контроль ответа на напоминания |
| 016_reminder_deadlines_meals.sql | **7 июля 2026** | ✅ | Дедлайны еды + per-item кадэнс + measurements.chest (см. инцидент выше) |
| 017_questionnaire_summary_and_history.sql | 24 июля 2026 | ✅ | `client_profiles.questionnaire_summary` + таблица `client_questionnaire_history` (RLS) — саммари анкеты для LLM-контекста + история изменений при редактировании анкеты клиентом (владелец подтвердил накатку) |
| 018_client_consents.sql | 24 июля 2026 | ✅ | Таблица `client_consents` (LEGAL-1/LEGAL-5) — гранулярное согласие на обработку данных (здоровье/Telegram), блокирующий шаг перед анкетой онбординга; `consent` добавлен в `audit_logs_entity_type_check` (владелец подтвердил накатку — устранён прод-инцидент PGRST205) |
| 019_client_delete_restrict.sql | 24 июля 2026 | ✅ | LEGAL-3 — все FK `client_id → clients(id) ON DELETE CASCADE` переведены в `ON DELETE RESTRICT` (динамически, через `pg_constraint`); физическое удаление клиента с данными теперь невозможно на уровне БД, «удаление» в интерфейсе остаётся архивированием (`client_status='archived'`) (владелец подтвердил накатку) |
| 020_client_audit_findings.sql | 25 июля 2026 | ✅ | NEW-1 — таблица `client_audit_findings` (RLS: только нутрициолог) для находок проактивного аудита клиента (2×/нед, только при находке, severity ≤ medium, не в Telegram) |
| 021_reminder_topic_dedup.sql | — | ⏳ | P1-7 — `reminder_occurrences.last_notified_date` (DATE, бэкофилл из `due_date`) — основа кросс-джобового дедупа «одно сообщение по теме (`expected_response`) в день», чтобы `run_reminders`/`run_reminder_followups` не слали независимо по 2-3 сообщения об одном и том же (напр. вода) |
| 022_intolerances.sql | — | ⏳ | P1-13 (шаг 1) — `client_profiles.intolerances TEXT[]`: аллергия и непереносимость разделены. Медицински это разные состояния (абсолютное vs дозозависимое), и пока они в одном поле, проверка продуктов не может дать верный ответ. Данные существующих клиентов НЕ переносятся автоматически — остаются в `allergies` (более строгая категория, это безопасно), нутрициолог переносит вручную |
| 023_audit_knowledge_base.sql | — | ⏳ | P2-8 — найден при подготовке просмотра `audit_logs`: `entity_type='knowledge_base'` (используется загрузкой/удалением документов базы знаний) не входил в CHECK-констрейнт. На проде это давало 500 на успешно выполненной операции — сам документ сохранялся/удалялся, но `write_audit_log` падал необработанным исключением. **Срочная** (блокирует загрузку базы знаний, запланированную владельцем на эту неделю) |

Миграции 001–022 подтверждены применёнными на проде (владелец подтвердил накатку каждой).
023 создана 27 июля 2026, ⏳ ожидает накатки владельцем — после накатки отметить ✅ и дописать дату. **Накатить перед следующей загрузкой документа в базу знаний.**
При добавлении новой миграции — сразу дописать строку и после накатки прогнать verify-SQL.

---

## 🔎 ПРОВЕРКА ДРЕЙФА (verify-SQL)

Один запрос в Supabase → SQL Editor показывает, какие объекты миграций реально есть на проде.
Любая строка `ok = false` = непринятая миграция.

```sql
SELECT '005 bucket client-documents' AS migration,
       EXISTS(SELECT 1 FROM storage.buckets WHERE id='client-documents') AS ok
UNION ALL SELECT '006 client_profiles.tracked_lab_indicators',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='client_profiles' AND column_name='tracked_lab_indicators')
UNION ALL SELECT '007 clients.paid_until',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='clients' AND column_name='paid_until')
UNION ALL SELECT '008 client_reports table',
       to_regclass('public.client_reports') IS NOT NULL
UNION ALL SELECT '009 clients.conversation_summary',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='clients' AND column_name='conversation_summary')
UNION ALL SELECT '010 clients.telegram_link_token',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='clients' AND column_name='telegram_link_token')
UNION ALL SELECT '012 llm_config.orchestrator',
       EXISTS(SELECT 1 FROM system_settings WHERE key='llm_config' AND value ? 'orchestrator')
UNION ALL SELECT '013 reminders table',
       to_regclass('public.reminders') IS NOT NULL
UNION ALL SELECT '013 reminder_occurrences table',
       to_regclass('public.reminder_occurrences') IS NOT NULL
UNION ALL SELECT '014 client_metrics table',
       to_regclass('public.client_metrics') IS NOT NULL
UNION ALL SELECT '014 client_profiles.controlled_metrics',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='client_profiles' AND column_name='controlled_metrics')
UNION ALL SELECT '015 reminders.expected_response',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='reminders' AND column_name='expected_response')
UNION ALL SELECT '015 reminder_occurrences.status',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='reminder_occurrences' AND column_name='status')
UNION ALL SELECT '016 reminders.followup_after_hours',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='reminders' AND column_name='followup_after_hours')
UNION ALL SELECT '016 measurements.chest',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='measurements' AND column_name='chest')
UNION ALL SELECT '017 client_profiles.questionnaire_summary',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='client_profiles' AND column_name='questionnaire_summary')
UNION ALL SELECT '017 client_questionnaire_history table',
       to_regclass('public.client_questionnaire_history') IS NOT NULL
UNION ALL SELECT '018 client_consents table',
       to_regclass('public.client_consents') IS NOT NULL
UNION ALL SELECT '018 audit_logs entity_type allows consent',
       EXISTS(SELECT 1 FROM pg_constraint WHERE conname='audit_logs_entity_type_check'
              AND pg_get_constraintdef(oid) LIKE '%''consent''%')
UNION ALL SELECT '019 no CASCADE left on clients(id) FKs',
       NOT EXISTS(
           SELECT 1 FROM pg_constraint
           WHERE confrelid = 'clients'::regclass AND contype = 'f' AND confdeltype = 'c'
       )
UNION ALL SELECT '020 client_audit_findings table',
       to_regclass('public.client_audit_findings') IS NOT NULL
UNION ALL SELECT '021 reminder_occurrences.last_notified_date',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='reminder_occurrences' AND column_name='last_notified_date')
UNION ALL SELECT '022 client_profiles.intolerances',
       EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='client_profiles' AND column_name='intolerances')
UNION ALL SELECT '023 audit_logs allows knowledge_base',
       EXISTS(SELECT 1 FROM pg_constraint WHERE conname='audit_logs_entity_type_check'
              AND pg_get_constraintdef(oid) LIKE '%''knowledge_base''%')
ORDER BY migration;
```

---

## 🔄 ОТКАТ МИГРАЦИИ

Если нужно откатить `001_add_observer_role.sql`:

```sql
-- Вернуть старый constraint (без observer)
ALTER TABLE users DROP CONSTRAINT users_role_check;

ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('nutritionist', 'client'));
```

⚠️ **Внимание:** Откат возможен только если в БД нет пользователей с ролью `observer`!

---

## 📝 СОЗДАНИЕ НОВОЙ МИГРАЦИИ

При создании новой миграции:

1. Создай файл: `00X_название_миграции.sql`
2. Укажи в начале:
   - Дату
   - Описание
   - Что делает
3. Добавь комментарий с ожидаемым результатом
4. Обнови этот README.md

---

**Последнее обновление:** 7 июля 2026  
**Версия схемы:** v1.5 (напоминания + контролируемые показатели + дедлайны еды + measurements.chest)
