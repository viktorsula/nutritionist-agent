# Миграции базы данных

Этот каталог содержит SQL миграции для обновления схемы БД в Supabase.

---

## 📋 СПИСОК МИГРАЦИЙ

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

После выполнения миграции отметь статус:

| Миграция | Дата выполнения | Статус | Примечания |
|----------|-----------------|--------|------------|
| 001_add_observer_role.sql | 19 июня 2026 | ✅ | Применена |
| 002_add_vector_search.sql | 19 июня 2026 | ✅ | Применена |
| 003_questionnaire_and_measurements.sql | 19 июня 2026 | ✅ | Применена |
| 004_rls_policies.sql | 19 июня 2026 | ✅ | Применена |
| 005_storage_client_documents.sql | ___ | ⏳ | Бакет client-documents + storage RLS (требует 004) |

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

**Последнее обновление:** 19 июня 2026  
**Версия схемы:** v1.4 (опросник + замеры + анализы + RLS для веб-доступа)
