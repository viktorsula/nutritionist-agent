# Функции queries.py для n8n (автоматизация)

## ✅ Добавлено 8 функций:

### 1. `get_notifications_due_now(notification_type=None)`
**n8n workflow:** Персональные уведомления (каждые 5 минут)  
**Назначение:** Получить клиентов, которым пора отправить уведомление  
**Фильтры:**
- `is_active=true` — уведомления включены
- `access_status='active'` — доступ не заморожен
- `payment_status in ['trial', 'active']` — оплата активна

**Возвращает:** List с данными клиента + расписание (включая timezone)

**Пример использования в n8n:**
```javascript
// n8n Code Node
const schedules = $input.all(); // результат из get_notifications_due_now()

for (const schedule of schedules) {
  const client = schedule.clients;
  const clientTime = luxon.DateTime.now().setZone(client.timezone);
  const scheduledTime = schedule.scheduled_time; // "08:00"
  
  if (clientTime.toFormat('HH:mm') === scheduledTime) {
    // Отправить уведомление через Telegram Bot
  }
}
```

---

### 2. `create_notification_schedule(client_id, notification_type, scheduled_time, timezone, is_active)`
**Для:** Управление расписаниями (agents/management или веб-интерфейс)  
**Назначение:** Создать новое расписание уведомлений  
**Пример:**
```python
create_notification_schedule(
    client_id="...",
    notification_type="morning",
    scheduled_time="08:00",
    timezone="Asia/Dubai",
    is_active=True
)
```

---

### 3. `get_clients_for_weekly_report()`
**n8n workflow:** Еженедельный отчёт (каждый понедельник 09:00)  
**Назначение:** Список active клиентов для сводки нутрициологу  
**Возвращает:** List клиентов со статусом `active`

**Пример использования в n8n:**
```javascript
// n8n: получить список → для каждого вызвать get_client_summary() → собрать в отчёт
const clients = $input.all();
const summaries = [];

for (const client of clients) {
  const summary = await getClientSummary(client.id, 7); // 7 дней
  summaries.push(summary);
}

// Отправить отчёт нутрициологу в Telegram
```

---

### 4. `get_clients_with_inactive_payment()`
**n8n workflow:** Напоминание об оплате (ежедневно 10:00)  
**Назначение:** Клиенты с `payment_status='inactive'` и статусом `active/paused`  
**Возвращает:** List клиентов, которым нужно напомнить об оплате

---

### 5. `get_critical_alerts(hours=24)`
**n8n workflow:** Проверка алертов (каждый час)  
**Назначение:** Все критичные события за последние N часов  
**Пример:**
```python
# Последние критичные алерты за 24 часа
alerts = get_critical_alerts(hours=24)

for alert in alerts:
    client = alert['clients']
    # Отправить уведомление нутрициологу
```

---

### 6. `trigger_alert_webhook(client_id, severity, alert_type, message, payload)`
**Для:** business_rules (немедленные алерты)  
**Назначение:** Записать алерт + вернуть данные для отправки в n8n webhook  
**Пример:**
```python
# business_rules/medical_rules.py
if glucose > critical_threshold:
    alert_data = trigger_alert_webhook(
        client_id=client_id,
        severity="critical",
        alert_type="glucose_critical",
        message=f"Критический уровень глюкозы: {glucose} ммоль/л",
        payload={"glucose": glucose, "threshold": critical_threshold}
    )
    
    # Отправить в n8n webhook
    requests.post(n8n_webhook_url, json=alert_data)
```

**n8n webhook:** Получает данные → отправляет Telegram нутрициологу

---

### 7. `get_client_summary(client_id, days=7)`
**Для:** n8n + analytics_agent  
**Назначение:** Полная сводка по клиенту за период  
**Возвращает:**
```python
{
    "client": {...},
    "period_days": 7,
    "message_count": 25,
    "total_events": 12,
    "critical_alerts": 0,
    "high_alerts": 2,
    "pending_tasks": 3,
    "completed_tasks": 5,
    "recent_events": [...]  # последние 5
}
```

**Пример использования:**
```python
# Еженедельный отчёт
summary = get_client_summary(client_id, days=7)
report = f"""
📊 Сводка по {summary['client']['name']} за неделю:
• Сообщений: {summary['message_count']}
• Критичных алертов: {summary['critical_alerts']}
• Задач выполнено: {summary['completed_tasks']}/{summary['pending_tasks']}
"""
```

---

### 8. `get_overdue_tasks(client_id=None)`
**n8n workflow:** Просроченные задачи (ежедневно 10:00)  
**Назначение:** Список просроченных задач (все или по клиенту)  
*Уже была добавлена в блоке agents*

---

## 📊 n8n WORKFLOWS (архитектура):

### Workflow 1: Персональные уведомления
**Триггер:** Каждые 5 минут  
**Логика:**
1. `get_notifications_due_now()` → список расписаний
2. Для каждого: конвертировать UTC → timezone клиента
3. Если время совпало → отправить уведомление (Telegram Bot)
4. Типы: `morning`, `evening`, `reminder`, `custom`

### Workflow 2: Еженедельный отчёт
**Триггер:** Понедельник 09:00 (timezone нутрициолога)  
**Логика:**
1. `get_clients_for_weekly_report()` → список active клиентов
2. Для каждого: `get_client_summary(client_id, 7)`
3. Собрать в единый отчёт
4. Отправить нутрициологу в Telegram

### Workflow 3: Критичные алерты
**Триггер:** Webhook от business_rules  
**Логика:**
1. business_rules вызывает `trigger_alert_webhook()`
2. Данные отправляются в n8n webhook
3. n8n немедленно отправляет в Telegram нутрициологу

### Workflow 4: Просроченные задачи
**Триггер:** Ежедневно 10:00  
**Логика:**
1. `get_overdue_tasks()` → список просроченных
2. Группировать по клиентам
3. Отправить список нутрициологу

### Workflow 5: Напоминание об оплате
**Триггер:** Ежедневно 10:00  
**Логика:**
1. `get_clients_with_inactive_payment()`
2. Отправить список нутрициологу
3. Опционально: автосообщение клиенту

---

## 📊 ИТОГО в queries.py:

**Было:** 34 функции (~550 строк)  
**Стало:** 42 функции (~750 строк)  

**Полностью готово для:**
- ✅ business_rules/
- ✅ agents/
- ✅ n8n workflows

---

## 🎯 queries.py ЗАВЕРШЁН НА 100%!

Все функции из ТЗ v1.3 (раздел 12) реализованы.
