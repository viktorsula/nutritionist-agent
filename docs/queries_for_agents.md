# Функции queries.py для agents

## ✅ Добавлено 14 функций:

### БЛОК: CONVERSATIONS (диалоги)

#### 1. `save_conversation(client_id, role, message_text, channel, conversation_type, thread_id, metadata)`
**Для:** router.py, orchestrator.py, все агенты  
**Назначение:** Сохранить сообщение в базу  
**Пример:**
```python
save_conversation(
    client_id="...",
    role="client",
    message_text="Как мне питаться сегодня?",
    channel="telegram",
    conversation_type="client_dialog",
    thread_id="session_123",
    metadata={"model": "groq", "tokens": 50}
)
```

#### 2. `get_conversations(client_id, limit=50, conversation_type=None)`
**Для:** orchestrator.py (загрузка контекста)  
**Назначение:** Получить последние N сообщений  
**Пример:**
```python
# Последние 10 сообщений диалога
history = get_conversations(client_id, limit=10, conversation_type="client_dialog")
```

#### 3. `get_conversation_thread(thread_id)`
**Для:** orchestrator.py (восстановление контекста сессии)  
**Назначение:** Все сообщения из одной сессии  

---

### БЛОК: NUTRITION_PLANS (планы питания)

#### 4. `create_nutrition_plan(client_id, title, created_by, effective_from, plan_json, supplements_json, effective_to)`
**Для:** management_agent.py (нутрициолог создаёт план)  
**Назначение:** Создать новый план (триггеры автоматически установят version и деактивируют старый)  
**Пример:**
```python
create_nutrition_plan(
    client_id="...",
    title="Базовый план без глютена",
    created_by="nutritionist",
    effective_from="2026-06-08",
    plan_json={
        "breakfast": "Овсянка на воде",
        "lunch": "Куриная грудка с овощами",
        "restrictions": ["глютен", "молочка"]
    },
    supplements_json={
        "vitamin_d": "2000 IU daily",
        "omega_3": "1000 mg twice daily"
    }
)
```

#### 5. `get_plan_history(client_id)`
**Для:** analytics_agent.py  
**Назначение:** Все версии планов питания клиента (для анализа изменений)  

---

### БЛОК: TASKS (задачи)

#### 6. `create_task(client_id, title, created_by, description, due_date, plan_id)`
**Для:** management_agent.py  
**Назначение:** Создать задачу клиенту  
**Пример:**
```python
create_task(
    client_id="...",
    title="Взвеситься в пятницу утром",
    created_by="nutritionist",
    description="Натощак, после туалета",
    due_date="2026-06-12T08:00:00"
)
```

#### 7. `complete_task(task_id, confirmation_payload)`
**Для:** diary_agent.py (клиент отмечает выполнение)  
**Назначение:** Отметить задачу + записать подтверждение в client_events  
**Пример:**
```python
complete_task(
    task_id="...",
    confirmation_payload={"weight_kg": 68.5, "photo_url": "https://..."}
)
```

#### 8. `get_pending_tasks(client_id)`
**Для:** dialog_agent.py (напоминание о задачах)  
**Назначение:** Активные задачи клиента  

#### 9. `get_overdue_tasks(client_id=None)`
**Для:** analytics_agent.py, n8n (алерты о просроченных задачах)  
**Назначение:** Просроченные задачи (все или по клиенту)  

---

### БЛОК: WELLNESS_PLANS (планы ЗОЖ)

#### 10. `create_wellness_plan(client_id, sleep_target, activity_target, recovery, stress_management, notes)`
**Для:** management_agent.py  
**Назначение:** Создать план ЗОЖ  
**Пример:**
```python
create_wellness_plan(
    client_id="...",
    sleep_target="7-8 часов, ложиться до 23:00",
    activity_target="10000 шагов в день, 3 тренировки в неделю",
    recovery="Массаж 1 раз в неделю, баня по субботам",
    stress_management="Медитация 10 мин утром, прогулки"
)
```

#### 11. `get_wellness_plan(client_id)`
**Для:** dialog_agent.py (показать клиенту его план)  
**Назначение:** Получить активный план ЗОЖ  

#### 12. `update_wellness_plan(client_id, updates)`
**Для:** management_agent.py  
**Назначение:** Обновить существующий план  
**Пример:**
```python
update_wellness_plan(
    client_id="...",
    updates={"sleep_target": "8-9 часов, ложиться до 22:30"}
)
```

---

### БЛОК: CLIENTS & AUDIT

#### 13. `get_all_clients(status=None)`
**Для:** analytics_agent.py (реестр клиентов)  
**Назначение:** Список всех клиентов, опционально фильтр по client_status  
**Пример:**
```python
# Все активные клиенты
active_clients = get_all_clients(status="active")

# Клиенты на онбординге
onboarding = get_all_clients(status="onboarding")
```

#### 14. `write_audit_log(actor_type, action, entity_type, entity_id, actor_id, old_value, new_value)`
**Для:** Все агенты (логирование критичных действий)  
**Назначение:** Записать действие в audit_log  
**Пример:**
```python
write_audit_log(
    actor_type="nutritionist",
    actor_id=nutritionist_id,
    action="change_plan",
    entity_type="plan",
    entity_id=plan_id,
    old_value={"restrictions": ["глютен"]},
    new_value={"restrictions": ["глютен", "молочка"]}
)
```

---

## 📊 ИТОГО в queries.py:

**Было:** 20 функций (~290 строк)  
**Стало:** 34 функции (~550 строк)  

**Готово для разработки:**
- ✅ agents/router.py
- ✅ agents/client/orchestrator.py
- ✅ agents/client/dialog_agent.py
- ✅ agents/client/nutrition_agent.py
- ✅ agents/client/diary_agent.py
- ✅ agents/nutritionist/orchestrator.py
- ✅ agents/nutritionist/analytics_agent.py
- ✅ agents/nutritionist/management_agent.py

---

## 🎯 Следующий шаг:
Начать создание business_rules/ или agents/
