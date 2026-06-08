# Функции queries.py для business_rules

## ✅ Добавлено 8 функций:

### 1. `get_client_profile(client_id: str)`
**Для:** medical_rules.py  
**Назначение:** Получить медицинский профиль (аллергии, chronic_conditions, custom_alert_thresholds)  
**Возвращает:** Dict с полями client_profiles или None

---

### 2. `update_client(client_id: str, updates: Dict[str, Any])`
**Для:** access_rules.py, payment_rules.py  
**Назначение:** Универсальная функция обновления любых полей clients  
**Пример:**
```python
update_client(client_id, {"payment_status": "active", "nutritionist_notes": "Оплата продлена"})
```

---

### 3. `update_client_status(client_id, client_status=None, payment_status=None, access_status=None)`
**Для:** access_rules.py, payment_rules.py  
**Назначение:** Удобная обёртка для обновления статусов  
**Пример:**
```python
update_client_status(client_id, payment_status="inactive", access_status="frozen")
```

---

### 4. `log_client_event(client_id, event_type, severity=None, payload=None)`
**Для:** medical_rules.py, access_rules.py  
**Назначение:** Записать событие в client_events (алерты, действия)  
**Пример:**
```python
log_client_event(
    client_id="...",
    event_type="alert_triggered",
    severity="critical",
    payload={"alert_type": "food_forbidden", "product": "глютен"}
)
```

---

### 5. `get_client_events(client_id, severity=None, limit=100)`
**Для:** medical_rules.py, analytics  
**Назначение:** Получить историю событий, опционально фильтр по severity  
**Пример:**
```python
# Все критичные события
critical_events = get_client_events(client_id, severity="critical")
```

---

### 6. `get_notification_schedule(client_id: str)`
**Для:** notification_rules.py  
**Назначение:** Получить расписание уведомлений клиента  
**Возвращает:** List[Dict] со всеми типами уведомлений (morning, evening, reminder)

---

### 7. `update_notification_schedule(client_id, notification_type, is_active=None, scheduled_time=None)`
**Для:** notification_rules.py  
**Назначение:** Вкл/откл уведомления или изменить время  
**Пример:**
```python
# Отключить утренние уведомления
update_notification_schedule(client_id, "morning", is_active=False)

# Изменить время вечерних уведомлений
update_notification_schedule(client_id, "evening", scheduled_time="21:30")
```

---

### 8. `update_system_setting(key, value, updated_by=None)`
**Для:** medical_rules.py (изменение порогов алертов)  
**Назначение:** Обновить глобальную настройку  
**Пример:**
```python
update_system_setting(
    key="alert_thresholds",
    value={"glucose_critical": 13, "weight_increase_kg": 2.5},
    updated_by=nutritionist_user_id
)
```

---

## 📊 ИТОГО в queries.py:

**Было:** 12 функций (163 строки)  
**Стало:** 20 функций (~290 строк)  

**Готово для разработки:**
- ✅ business_rules/access_rules.py
- ✅ business_rules/medical_rules.py
- ✅ business_rules/payment_rules.py
- ✅ business_rules/notification_rules.py

---

## 🎯 Следующий шаг:
Начать создание business_rules/ модулей
