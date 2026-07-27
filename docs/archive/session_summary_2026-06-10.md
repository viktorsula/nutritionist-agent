# 📊 СВОДКА СЕССИИ — 10 ИЮНЯ 2026

## ✅ ЧТО СДЕЛАНО:

### **ЭТАП 4: utils/ — ЗАВЕРШЁН (Часть 1: Базовые модули)**

Созданы базовые утилиты для работы агентов с LLM провайдерами.

---

## 📂 СТРУКТУРА utils/

```
utils/
├── __init__.py              # Экспорт всех функций
├── llm.py                   # Мультипровайдерный LLM клиент (563 строки)
├── helpers.py               # Вспомогательные функции (356 строк)
├── llm_examples.py          # Примеры использования (339 строк)
└── test_llm.py              # Тесты (334 строки)
```

**Всего:** ~1592 строк кода + документация

---

## 🎯 РЕАЛИЗОВАННЫЕ МОДУЛИ:

### 1. **llm.py — Мультипровайдерный LLM клиент**

**Ключевая функция:** `call_llm()`

**Архитектура (Вариант 3 — гибридный):**

```python
# 99% случаев — через task_type (из БД)
response = call_llm(
    task_type='dialog',
    messages=[...]
)

# 1% случаев — явное указание модели (эксперименты, A/B тесты)
response = call_llm(
    provider='claude',
    model='claude-opus-4-8',
    messages=[...]
)
```

**Поддерживаемые провайдеры:**
- ✅ **Groq** (llama-3.3-70b) — диалог, бесплатно
- ✅ **Claude** (Sonnet 4.6) — аналитика, ~$3/M токенов
- ✅ **Gemini** (1.5 Flash) — vision, бесплатно

**Task types (6 типов):**
1. `dialog` → Groq llama-3.3-70b (ежедневный диалог)
2. `analytics` → Claude Sonnet (глубокий анализ)
3. `vision` → Gemini Flash (фото еды)
4. `nutrition_analysis` → Claude Sonnet (анализ рациона)
5. `summary` → Groq llama-3.3-70b (сводки)
6. `planning` → Claude Sonnet (планы питания)

**Конфигурация:**

| Приоритет | Источник | Как поменять модель |
|-----------|----------|---------------------|
| 1. База данных | `system_settings → llm_config` | Через веб-интерфейс нутрициолога (v1.1) |
| 2. Fallback | `DEFAULT_TASK_MODEL_MAPPING` | Изменить 1 строку в llm.py → редеплой |

**Возвращает:**
```python
{
    "content": str,              # Сгенерированный текст
    "model": str,                # Использованная модель
    "provider": str,             # Провайдер (groq/claude/gemini)
    "usage": {
        "input_tokens": int,
        "output_tokens": int,
        "total_tokens": int
    },
    "finish_reason": str,        # Причина остановки
    "task_type": str             # Тип задачи (если указан)
}
```

**Дополнительные функции:**
- `get_model_config(task_type)` — получение конфига из БД или fallback
- `list_available_providers()` — проверка доступных провайдеров
- `list_task_types()` — список всех task_type с описаниями

**Приватные функции для провайдеров:**
- `_call_groq()` — вызов Groq API
- `_call_claude()` — вызов Claude API (конвертация формата для system message)
- `_call_gemini()` — вызов Gemini API (конвертация формата для role)

**TODO v1.1:**
- Интеграция LangFuse для трейсинга
- Retry logic для rate limits
- Streaming support

---

### 2. **helpers.py — Вспомогательные функции**

**Группы функций:**

#### **Форматирование сообщений:**
- `format_client_message()` — форматирует ответ с алертами и уведомлением нутрициолога

#### **Работа с датами/временем:**
- `parse_datetime()` — парсит "сегодня", "завтра", "через N дней" (timezone-aware)
- `format_date_for_client()` — форматирует дату для клиента (ru/en/ar)

#### **Валидация:**
- `validate_ingredients()` — проверка на аллергены и запрещённые продукты

#### **Расчёты КБЖУ:**
- `calculate_nutrition()` — суммирование КБЖУ списка продуктов
- `estimate_calories()` — оценка калорий по описанию (TODO: интеграция LLM)

#### **Генерация сводок:**
- `generate_summary()` — сводка по клиенту за период (TODO: интеграция queries + LLM)
- `format_analytics_report()` — форматирование отчётов для нутрициолога

#### **Работа с языками:**
- `detect_language()` — определение языка (ru/en/ar)
- `translate_if_needed()` — перевод текста (TODO: integration API)

**Статус:** Базовая структура готова, большинство функций — заглушки с TODO для Этапа 6+

---

### 3. **llm_examples.py — Примеры использования**

**6 примеров:**
1. **Диалог с клиентом** — обычное использование через `task_type='dialog'`
2. **Аналитика клиента** — использование Claude для глубокого анализа
3. **A/B тестирование** — сравнение моделей (default vs experimental)
4. **Premium клиенты** — разные модели для разных уровней подписки
5. **Переопределение параметров** — изменение temperature и max_tokens
6. **Использование в агенте** — полный пример для dialog_agent

**Использование:**
```bash
# Раскомментируйте функции в __main__ после добавления API ключей
python3 utils/llm_examples.py
```

---

### 4. **test_llm.py — Тестирование**

**6 тестов:**
1. ✅ Проверка импортов
2. ✅ Проверка DEFAULT_TASK_MODEL_MAPPING (6 task_type)
3. ✅ Проверка get_model_config() (корректный + ошибка)
4. ✅ Проверка доступных провайдеров (API ключи)
5. ✅ Проверка list_task_types()
6. ✅ Проверка валидации call_llm()

**Результат тестирования:**
```
Пройдено: 6/6
✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ
```

**Запуск:**
```bash
PYTHONPATH=/workspaces/nutritionist-agent python3 utils/test_llm.py
```

---

## 🔧 ТЕХНИЧЕСКИЕ ДЕТАЛИ:

### **Зависимости (обновлены в requirements.txt):**

```txt
# LLM провайдеры
groq>=0.4.0
anthropic>=0.18.0
google-generativeai>=0.3.0
langgraph>=0.0.26

# Мониторинг
langfuse>=2.0.0

# Утилиты
pytz==2024.1
```

### **Переменные окружения (обновлены в .env.example):**

```bash
# LLM Провайдеры
GROQ_API_KEY=your-groq-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
GOOGLE_API_KEY=your-google-api-key

# Мониторинг (TODO v1.1)
LANGFUSE_PUBLIC_KEY=your-langfuse-public-key
LANGFUSE_SECRET_KEY=your-langfuse-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com
```

### **Интеграция с database/queries.py:**

Добавлена функция `get_setting(key)` для получения значений из `system_settings`:

```python
# database/queries.py
def get_setting(key: str) -> Optional[Any]:
    """Получает значение setting_value из system_settings"""
    setting = get_system_setting(key)
    if setting and isinstance(setting, dict):
        return setting.get('setting_value')
    return None
```

**Использование в llm.py:**
```python
from database import queries

llm_config = queries.get_setting('llm_config')
if llm_config and 'dialog' in llm_config:
    config = llm_config['dialog']  # Конфиг из БД
```

---

## 📊 КЛЮЧЕВЫЕ РЕШЕНИЯ:

### 1. **Вариант 3 (гибридный) — ПРИНЯТ**

**Обоснование:**
- 99% вызовов → через `task_type` (централизованное управление)
- 1% вызовов → явное указание `provider+model` (эксперименты, A/B тесты, premium)
- Максимальная гибкость без усложнения кода агентов

**Примеры использования:**
```python
# Обычный случай
call_llm(task_type='dialog', messages=[...])

# Эксперимент с новой моделью
call_llm(provider='openai', model='gpt-4o', messages=[...])

# Premium клиент
if client.tier == 'premium':
    call_llm(provider='claude', model='claude-opus-4-8', messages=[...])
else:
    call_llm(task_type='dialog', messages=[...])
```

### 2. **Конфигурация в system_settings (Вариант Б) — ПРИНЯТ**

**Приоритет источников:**
1. `system_settings.llm_config` (БД) — если настроено
2. `DEFAULT_TASK_MODEL_MAPPING` (hardcoded) — fallback

**Преимущества:**
- Нутрициолог сможет менять модели через веб-интерфейс (v1.1)
- Не нужен редеплой для смены модели
- История изменений через `audit_logs`
- Безопасный fallback если БД недоступна

### 3. **6 типов задач — ЗАФИКСИРОВАНО**

| Task Type | Provider | Model | Использование |
|-----------|----------|-------|---------------|
| `dialog` | Groq | llama-3.3-70b | Ежедневный диалог (99% запросов) |
| `analytics` | Claude | Sonnet 4.6 | Глубокий анализ клиентов |
| `vision` | Gemini | Flash 1.5 | Анализ фото еды |
| `nutrition_analysis` | Claude | Sonnet 4.6 | Анализ рациона, КБЖУ |
| `summary` | Groq | llama-3.3-70b | Генерация сводок |
| `planning` | Claude | Sonnet 4.6 | Планы питания, задачи |

### 4. **Безопасность ключей — СОБЛЮДЕНО**

✅ Все API ключи через `os.environ.get()` (НЕ через load_dotenv!)  
✅ Понятные ошибки если ключ не найден  
✅ .env.example обновлён с комментариями  
✅ Никаких хардкод ключей в коде

---

## 🎯 СЛЕДУЮЩИЙ ЭТАП:

**Этап 5:** Создание agents/ (router.py + оркестраторы LangGraph)

**План:**
1. `agents/router.py` — входной маршрутизатор (роль → ветка)
2. `agents/client/orchestrator.py` — LangGraph оркестратор клиента
3. `agents/client/dialog_agent.py` — первый агент (диалог)

**После Этапа 5:**
- Этап 6: Остальные агенты + расширение utils/ (vision.py, voice.py, web_access.py, knowledge.py)
- Этап 7: Telegram Bot
- Этап 8: Мониторинг LangFuse

---

## 📝 ОБНОВЛЁННЫЕ ФАЙЛЫ:

### **Созданы:**
- utils/__init__.py
- utils/llm.py (563 строки)
- utils/helpers.py (356 строк)
- utils/llm_examples.py (339 строк)
- utils/test_llm.py (334 строки)
- docs/session_summary_2026-06-10.md

### **Модифицированы:**
- requirements.txt (добавлены groq, anthropic, google-generativeai, langgraph, langfuse)
- .env.example (обновлён GOOGLE_API_KEY вместо GEMINI_API_KEY)
- database/queries.py (добавлена функция get_setting())

---

## 🧪 ТЕСТИРОВАНИЕ:

### **Запуск тестов:**
```bash
# Все тесты
PYTHONPATH=/workspaces/nutritionist-agent python3 utils/test_llm.py

# Результат: 6/6 PASSED ✅
```

### **Статус без API ключей:**
⚠️ Провайдеры недоступны (нужны ключи для реальных вызовов)  
✅ Структура, импорты, валидация работают корректно

---

## 💡 ДЛЯ НУТРИЦИОЛОГА (v1.1):

### **Как поменять модель через БД:**

```sql
-- Вставить/обновить конфигурацию LLM
INSERT INTO system_settings (setting_key, setting_value, category, description)
VALUES (
  'llm_config',
  '{
    "dialog": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "analytics": {
      "provider": "claude",
      "model": "claude-sonnet-4-6",
      "temperature": 0.3,
      "max_tokens": 4000
    }
  }'::jsonb,
  'ai_models',
  'Конфигурация LLM провайдеров'
)
ON CONFLICT (setting_key) DO UPDATE
SET setting_value = EXCLUDED.setting_value,
    updated_at = NOW();
```

**Интерфейс (TODO Этап 7+):**
- Streamlit UI для редактирования llm_config
- Выбор модели из dropdown
- Тестирование перед сохранением
- История изменений

---

**Сессия завершена:** 10 июня 2026  
**Результат:** utils/ (базовые модули) готовы для использования агентами  
**Следующий шаг:** Этап 5 — Создание agents/ (router.py + LangGraph оркестраторы)
