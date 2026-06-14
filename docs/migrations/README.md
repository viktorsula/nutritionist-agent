# Миграции базы данных

Этот каталог содержит SQL миграции для обновления схемы БД в Supabase.

---

## 📋 СПИСОК МИГРАЦИЙ

### **001_add_observer_role.sql**
- **Дата:** 10 июня 2026
- **Описание:** Добавление роли `observer` для продакшн-версии
- **Статус:** ⏳ Требует выполнения
- **Что делает:**
  - Удаляет старый constraint `users_role_check`
  - Добавляет новый с ролями: `nutritionist`, `client`, `observer`

### **002_add_vector_search.sql**
- **Дата:** 14 июня 2026
- **Описание:** RPC-функции семантического поиска по pgvector (Этап 6)
- **Статус:** ⏳ Требует выполнения
- **Что делает:**
  - `match_knowledge_base(query_embedding, match_count, similarity_threshold)` — cosine-поиск по базе знаний
  - `match_client_documents(query_embedding, p_client_id, match_count, similarity_threshold)` — поиск по документам клиента (с изоляцией по client_id)
  - Использует ivfflat-индексы (`<=>`, cosine), SECURITY INVOKER + search_path
- **Зависимость:** эмбеддинги OpenAI `text-embedding-ada-002` (1536), считаются в `utils/knowledge.py`

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
| 001_add_observer_role.sql | ___ | ⏳ | Ожидает выполнения |
| 002_add_vector_search.sql | ___ | ⏳ | Ожидает выполнения |

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

**Последнее обновление:** 10 июня 2026  
**Версия схемы:** v1.3.1 (добавлена роль observer)
