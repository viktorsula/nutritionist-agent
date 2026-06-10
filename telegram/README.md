# Telegram Bot — Агент Нутрициолога

Telegram бот для общения клиентов с агентом-ассистентом.

## 📁 Структура

```
telegram/
├── __init__.py       — экспорт start_bot()
├── bot.py            — основной модуль бота
├── commands.py       — /start, /help, /status
├── handlers.py       — обработчики сообщений (текст, фото, голос)
├── test_bot.py       — тесты
└── README.md         — этот файл
```

## 🚀 Запуск

### Локально (для разработки):

```bash
python -m telegram.bot
```

### В продакшене (через основной app.py):

```python
from telegram import start_bot
start_bot()
```

## 🔧 Переменные окружения

Обязательные:
- `TELEGRAM_BOT_TOKEN` — токен от @BotFather
- `SUPABASE_URL` — URL Supabase проекта
- `SUPABASE_ANON_KEY` — ключ Supabase

Опциональные:
- `NUTRITIONIST_TELEGRAM_ID` — ID нутрициолога для алертов

## 📋 Команды бота

### `/start`
- Приветствие
- Для новых пользователей: инструкция по регистрации
- Для существующих: краткая справка

### `/help`
- Список команд
- Описание возможностей

### `/status`
- Текущий статус клиента
- Активный план питания
- Количество активных задач
- Вес и цель

## 🔄 Архитектура

```
Telegram User
    ↓
bot.py (получает сообщение)
    ↓
handlers.py (проверка регистрации)
    ↓
agents.route_message(user_id, message, channel="telegram")
    ↓
agents/router.py (маршрутизация по роли)
    ↓
client/orchestrator.py (LangGraph)
    ↓
dialog_agent → utils/llm.py → Groq llama-3.3-70b
    ↓
ответ пользователю
```

## ✅ Что работает (v1.0)

- ✅ Команды: /start, /help, /status
- ✅ Обработка текстовых сообщений
- ✅ Проверка регистрации клиента
- ✅ Интеграция с agents/router.py
- ✅ Индикатор "печатает..."
- ✅ Разбивка длинных сообщений (> 4000 символов)
- ✅ Обработка ошибок

## ⏳ TODO (будущие этапы)

- [ ] **Фото еды** (vision_agent + Gemini Flash) — Этап 6
- [ ] **Голосовые** (utils/voice.py + Whisper) — Этап 6
- [ ] **Документы** (PDF анализ) — Этап 6
- [ ] **Inline кнопки** (быстрые ответы)
- [ ] **Напоминания** (через n8n + notification_schedule)

## 🧪 Тесты

Запуск тестов:

```bash
python telegram/test_bot.py
```

Тесты покрывают:
- Команды для новых и существующих пользователей
- Обработчики текстовых сообщений
- Проверку регистрации
- Интеграцию с route_message()

## 🔐 Безопасность

- ✅ Токен бота только через `os.environ.get()`
- ✅ Проверка регистрации перед обработкой
- ✅ Логирование всех действий
- ✅ Глобальный error_handler

## 📝 Как добавить нового клиента

1. Клиент отправляет `/start` боту
2. Бот показывает его `telegram_id`
3. Нутрициолог добавляет клиента через веб-интерфейс:
   - Имя, email, телефон
   - `telegram_id` из шага 2
   - Роль: `client`
4. Клиент снова `/start` — теперь может общаться

## 🐛 Отладка

Логи бота:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

Проверка токена:
```bash
echo $TELEGRAM_BOT_TOKEN
```

Проверка подключения к Supabase:
```python
from database.client import supabase
print(supabase.table('users').select('*').limit(1).execute())
```

---

**Версия:** 1.0  
**Дата:** 10 июня 2026  
**Статус:** ✅ Базовый функционал готов
