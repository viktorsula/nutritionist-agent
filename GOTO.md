# GOTO — НАЧАЛО СЛЕДУЮЩЕЙ СЕССИИ

**Обновлено:** 8 июня 2026, после завершения миграции БД v1.3 и реализации queries.py

---

## 🎯 ЦЕЛЬ СЛЕДУЮЩЕЙ СЕССИИ:

**Начать разработку `business_rules/` — детерминированный слой между входом и LLM**

---

## ✅ ТЕКУЩЕЕ СОСТОЯНИЕ (8 июня 2026):

### **База данных Supabase v1.3 — ПОЛНОСТЬЮ ГОТОВА:**
- ✅ **14 таблиц** созданы и проверены:
  - **Блок 1:** users, clients, client_profiles, wellness_plans
  - **Блок 2:** conversations, client_events
  - **Блок 3:** nutrition_plans, tasks
  - **Блок 4:** notification_schedule, audit_logs, system_settings
  - **Блок 5:** document_metadata, knowledge_base, client_documents
- ✅ **VIEW:** client_registry_view (с SECURITY INVOKER)
- ✅ **Триггеры:** trg_plan_version, trg_deactivate_old_plans
- ✅ **Индексы:** включая ivfflat для pgvector (cosine distance)
- ✅ **Security Advisor:** 0 errors, 0 warnings
- ✅ **pgvector extension:** включён и работает

### **Код Python — ГОТОВ:**
- ✅ `database/client.py` — подключение к Supabase (service role + anon)
- ✅ `database/models.py` — 14 dataclass моделей для всех таблиц
- ✅ `database/queries.py` — **42 функции** готовы:
  - 8 для business_rules
  - 14 для agents
  - 8 для n8n
  - 12 базовых

### **Документация — АКТУАЛЬНА:**
- ✅ `docs/schema.sql` — схема v1.3
- ✅ `CLAUDE.md` — обновлён под v1.3
- ✅ `docs/progress.md` — миграция завершена
- ✅ Справочники по queries.py созданы

---

## 📋 ПЛАН НА СЛЕДУЮЩУЮ СЕССИЮ:

### **ШАГ 1: Создать business_rules/ (приоритет)**

**Структура:**
```
business_rules/
├── __init__.py
├── access_rules.py      — check_access(), check_payment()
├── medical_rules.py     — check_medical_alerts(), check_allergies()
├── payment_rules.py     — проверка статуса подписки
└── notification_rules.py — расписание, timezone, on/off
```

**Что реализовать:**
1. **access_rules.py:**
   - `check_access(client_id)` → allow | (block, reason)
   - `check_payment(client_id)` → active | (restricted, reason)
   - Использует: `get_client_by_id()`, `update_client_status()`

2. **medical_rules.py:**
   - `check_medical_alerts(data, client_id)` → safe | (severity, message)
   - `check_allergies(ingredients, client_id)` → safe | warning
   - Использует: `get_client_profile()`, `log_client_event()`, `get_system_setting()`

3. **payment_rules.py:**
   - `check_subscription_status(client_id)` → active | expired
   - Использует: `get_client_by_id()`, `update_client()`

4. **notification_rules.py:**
   - `should_send_notification(client_id, notification_type)` → bool
   - Использует: `get_notification_schedule()`

---

### **ШАГ 2: Создать utils/llm.py (после business_rules)**

**Функция:**
```python
def call_llm(
    provider: str,
    model: str,
    messages: List[Dict],
    task_type: str
) -> str:
    """
    Мультипровайдерный LLM клиент.
    provider: 'groq' | 'anthropic' | 'google'
    model: 'llama-3.3-70b' | 'claude-sonnet-4-6' | 'gemini-1.5-flash'
    task_type: 'dialog' | 'analysis' | 'vision'
    """
```

---

### **ШАГ 3: Начать agents/router.py**

**Входная точка:**
- Определение роли по токену (nutritionist / client)
- Вызов business_rules ПЕРВЫМ
- Маршрутизация в нужный оркестратор

---

## 📊 ГОТОВЫЕ ФУНКЦИИ queries.py ДЛЯ BUSINESS_RULES:

```python
# Уже реализованы и готовы к использованию:
get_client_by_id(client_id)
get_client_profile(client_id)
update_client(client_id, updates)
update_client_status(client_id, client_status, payment_status, access_status)
log_client_event(client_id, event_type, severity, payload)
get_client_events(client_id, severity, limit)
get_notification_schedule(client_id)
update_notification_schedule(client_id, notification_type, is_active, scheduled_time)
get_system_setting(key)
update_system_setting(key, value, updated_by)
```

---

## 🔧 ЧТО УЖЕ НЕ НУЖНО ДЕЛАТЬ:

- ❌ Миграция БД — завершена
- ❌ Создание таблиц — все 14 готовы
- ❌ models.py — все 14 моделей готовы
- ❌ queries.py — 42 функции реализованы
- ❌ Документация — обновлена

---

## 📝 ВАЖНЫЕ ФАЙЛЫ ДЛЯ СПРАВКИ:

- `docs/schema.sql` — актуальная схема БД v1.3
- `docs/queries_for_business_rules.md` — описание 8 функций
- `docs/queries_for_agents.md` — описание 14 функций
- `docs/queries_for_n8n.md` — описание 8 функций
- `docs/session_summary_2026-06-08.md` — полная сводка сессии

---

## 🎯 НАЧАТЬ С:

```bash
# 1. Создать структуру
mkdir -p business_rules
touch business_rules/__init__.py
touch business_rules/access_rules.py
touch business_rules/medical_rules.py
touch business_rules/payment_rules.py
touch business_rules/notification_rules.py

# 2. Начать с access_rules.py
# Реализовать check_access() и check_payment()
```

---

**Статус:** База данных и queries.py полностью готовы. Можно начинать бизнес-логику.

**Следующий файл для работы:** `business_rules/access_rules.py`
