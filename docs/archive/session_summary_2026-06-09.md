# 📊 СВОДКА СЕССИИ — 9 ИЮНЯ 2026

## ✅ ЧТО СДЕЛАНО:

### **ЭТАП 3: business_rules/ — ЗАВЕРШЁН**

Создан детерминированный слой бизнес-логики для обработки критических ситуаций ДО вызова LLM.

---

## 📂 СТРУКТУРА business_rules/

```
business_rules/
├── __init__.py              # Экспорт всех функций
├── access_rules.py          # Проверка доступа (179 строк)
├── medical_rules.py         # Медицинские алерты + маршрутизация (529 строк)
├── notification_rules.py    # Проверка расписания (217 строк)
└── test_imports.py          # Тестовый файл (проверка работоспособности)
```

**Всего:** ~925 строк кода + документация

---

## 🎯 РЕАЛИЗОВАННЫЕ МОДУЛИ:

### 1. **access_rules.py**

**Функция:** `check_access(client_id)`

**Проверяет:**
- [1] Клиент не архивирован
- [2] Анкета заполнена (`onboarding_completed_at IS NOT NULL`)
- [3] Оплата активна (`payment_status IN ('trial', 'active')`)
- [4] Программа не на паузе

**Определяет режим работы:**
- `full_program` — client_status='active' (работа с нутрициологом)
- `ai_support` — client_status='completed' + payment='active' (поддержка без нутрициолога)
- `blocked` — доступ запрещён

**Возвращает:**
```python
{
    "allowed": bool,
    "mode": str,
    "reason": str,
    "message_for_client": str
}
```

---

### 2. **medical_rules.py**

**3 основные функции:**

#### `check_allergies(client_id, ingredients)`
Проверяет ингредиенты на аллергены клиента (severity='critical')

#### `check_medical_alerts(client_id, food_items, mode)`
Проверяет 5 типов медицинских алертов:

| Тип | Триггер | Severity |
|-----|---------|----------|
| `weight_increase` | Вес > порог за 24ч | medium/high |
| `food_forbidden` | Запрещённый продукт из плана | high |
| `food_incompatible` | Несочетаемые продукты (pgvector) | medium |
| `no_response` | Нет ответа > N часов | medium/high |
| `bad_wellbeing` | Плохое самочувствие на чек-ине | high/critical |

#### `determine_routing(alerts, mode)`
**Ключевая функция маршрутизации** — решает куда направить сообщение:

**Логика:**

| mode | severity | route_to | notify_nutritionist | Что происходит |
|------|----------|----------|---------------------|----------------|
| ai_support | any | llm | ❌ | LLM всегда сам обрабатывает |
| full_program | low/medium | llm | ❌ | LLM обрабатывает + упоминает алерт |
| full_program | high/critical | **both** | ✅ | 1) Уведомление нутрициологу<br>2) LLM отвечает с формулировкой о том, что нутрициолог уведомлён |

**Возвращает:**
```python
{
    "route_to": "llm" | "both",
    "notify_nutritionist": bool,
    "block_llm": bool,
    "alerts": List[Alert],
    "priority": str,
    "nutritionist_message": str,
    "llm_context": {
        "nutritionist_notified": bool,  # ← ФЛАГ для LLM
        "instruction": str
    }
}
```

**Важно:** При `nutritionist_notified=True` LLM получает инструкцию включить в ответ:
> "Нутрициолог уже уведомлён о ситуации и свяжется с вами в ближайшее время. Вы можете воспользоваться информацией ассистента..."

---

### 3. **notification_rules.py**

**Функции:**

#### `check_notification_allowed(client_id, notification_type)`
Проверяет можно ли отправить уведомление:
- is_enabled == True?
- В разрешённом времени?

#### `is_within_allowed_hours(client_id, timezone_str, schedule)`
**Timezone-aware проверка** текущего времени:
- Конвертирует UTC → timezone клиента
- Проверяет диапазон allowed_start_time — allowed_end_time
- Обрабатывает диапазоны через полночь (22:00-08:00)
- Вычисляет next_allowed_time если сейчас нельзя

#### `get_client_timezone(client_id)`
Получает timezone клиента (по умолчанию 'UTC')

**Используется:** n8n, системные триггеры, автоматические уведомления

---

## 🔧 ТЕХНИЧЕСКИЕ ДЕТАЛИ:

### Зависимости:
- `database/queries.py` — все функции используют готовые запросы
- `pytz` — для timezone-aware обработки (добавлен в requirements.txt)

### Исправления:
- `get_client()` → `get_client_by_id()` (фактическое имя в queries.py)
- `get_nutrition_plan()` → `get_active_nutrition_plan()`

### Тестирование:
- ✅ Все импорты работают
- ✅ Структура модулей корректна
- ✅ test_imports.py прошёл успешно

---

## 📊 КЛЮЧЕВЫЕ РЕШЕНИЯ:

1. **Два режима работы:**
   - `full_program` → критичные алерты идут нутрициологу + LLM отвечает
   - `ai_support` → всё обрабатывает только LLM

2. **Маршрутизация через determine_routing():**
   - Решение принимается на основе severity + mode
   - Возвращает чёткую инструкцию для router.py

3. **Флаг nutritionist_notified в llm_context:**
   - Передаётся агенту для формирования правильного ответа клиенту
   - Клиент получает информацию о том, что нутрициолог уведомлён

4. **Независимость модулей:**
   - access_rules → только про доступ
   - medical_rules → только про алерты + маршрутизация
   - notification_rules → только про исходящие уведомления

5. **payment_rules.py не создавали:**
   - Логика простая: trial/active → доступ, inactive → блок
   - Всё реализовано в access_rules.py

---

## 🎯 СЛЕДУЮЩИЙ ЭТАП:

**Этап 4:** Создание utils/

Модули:
- `llm.py` — мультипровайдерный клиент (Groq, Claude, Gemini)
- `vision.py` — обработка фото еды через Gemini Flash
- `voice.py` — транскрипция голосовых через Whisper
- `helpers.py` — вспомогательные функции

---

## 📝 ОБНОВЛЁННЫЕ ФАЙЛЫ:

### Созданы:
- business_rules/__init__.py
- business_rules/access_rules.py
- business_rules/medical_rules.py
- business_rules/notification_rules.py
- business_rules/test_imports.py
- docs/session_summary_2026-06-09.md

### Модифицированы:
- CLAUDE.md (обновлён статус, следующий шаг)
- docs/progress.md (Этап 3 завершён)
- requirements.txt (добавлен pytz==2024.1)

---

**Сессия завершена:** 9 июня 2026  
**Результат:** business_rules/ полностью готов для интеграции с agents/ и router.py  
**Следующий шаг:** Создание utils/ (llm.py, vision.py, voice.py, helpers.py)
