"""
Тесты для Telegram бота
Проверка команд и обработчиков
"""

import sys
import os
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import unittest
from unittest.mock import Mock, patch, AsyncMock
from telegram import Update, User, Chat, Message
from telegram.ext import ContextTypes

# Импортируем наши модули
from telegram.commands import start_command, help_command, status_command
from telegram.handlers import handle_text_message


class TestTelegramCommands(unittest.TestCase):
    """Тесты команд бота"""

    def setUp(self):
        """Подготовка моков"""
        self.user = Mock(spec=User)
        self.user.id = 123456789
        self.user.username = "test_user"
        self.user.first_name = "Test"

        self.chat = Mock(spec=Chat)
        self.chat.id = 123456789

        self.message = Mock(spec=Message)
        self.message.reply_text = AsyncMock()
        self.message.chat = self.chat

        self.update = Mock(spec=Update)
        self.update.effective_user = self.user
        self.update.message = self.message

        self.context = Mock(spec=ContextTypes.DEFAULT_TYPE)

    @patch('telegram.commands.get_client_by_telegram_id')
    async def test_start_command_new_user(self, mock_get_client):
        """Тест /start для нового пользователя"""
        mock_get_client.return_value = None

        await start_command(self.update, self.context)

        # Проверяем что был вызван reply_text
        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        # Проверяем содержание сообщения
        self.assertIn("Привет", message_text)
        self.assertIn("Telegram ID", message_text)
        self.assertIn("зарегистрироваться", message_text.lower())

    @patch('telegram.commands.get_client_by_telegram_id')
    async def test_start_command_existing_user(self, mock_get_client):
        """Тест /start для существующего пользователя"""
        mock_client = Mock()
        mock_client.name = "Иван Петров"
        mock_get_client.return_value = mock_client

        await start_command(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("возвращением", message_text)
        self.assertIn("Иван Петров", message_text)

    @patch('telegram.commands.get_client_by_telegram_id')
    async def test_help_command_registered_user(self, mock_get_client):
        """Тест /help для зарегистрированного пользователя"""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        await help_command(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("команды", message_text.lower())
        self.assertIn("/start", message_text)
        self.assertIn("/status", message_text)

    @patch('telegram.commands.get_client_by_telegram_id')
    async def test_help_command_unregistered_user(self, mock_get_client):
        """Тест /help для незарегистрированного пользователя"""
        mock_get_client.return_value = None

        await help_command(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("не зарегистрированы", message_text)


class TestTelegramHandlers(unittest.TestCase):
    """Тесты обработчиков сообщений"""

    def setUp(self):
        """Подготовка моков"""
        self.user = Mock(spec=User)
        self.user.id = 123456789
        self.user.username = "test_user"

        self.chat = Mock(spec=Chat)
        self.chat.id = 123456789
        self.chat.send_action = AsyncMock()

        self.message = Mock(spec=Message)
        self.message.text = "Привет, как дела?"
        self.message.message_id = 1
        self.message.reply_text = AsyncMock()
        self.message.chat = self.chat

        self.update = Mock(spec=Update)
        self.update.effective_user = self.user
        self.update.message = self.message

        self.context = Mock(spec=ContextTypes.DEFAULT_TYPE)

    @patch('telegram.handlers.get_client_by_telegram_id')
    async def test_handle_text_unregistered_user(self, mock_get_client):
        """Тест обработки текста от незарегистрированного пользователя"""
        mock_get_client.return_value = None

        await handle_text_message(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("не зарегистрированы", message_text)

    @patch('telegram.handlers.route_message')
    @patch('telegram.handlers.get_client_by_telegram_id')
    async def test_handle_text_success(self, mock_get_client, mock_route):
        """Тест успешной обработки текста"""
        mock_client = Mock()
        mock_client.user_id = "user-uuid-123"
        mock_get_client.return_value = mock_client

        mock_route.return_value = {
            "success": True,
            "message": "Отлично! Записал."
        }

        await handle_text_message(self.update, self.context)

        # Проверяем что показали "typing"
        self.chat.send_action.assert_called_once_with("typing")

        # Проверяем что вызвали route_message
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]
        self.assertEqual(call_kwargs["user_id"], "user-uuid-123")
        self.assertEqual(call_kwargs["channel"], "telegram")

        # Проверяем отправку ответа
        self.message.reply_text.assert_called_once()


def run_tests():
    """Запуск всех тестов"""
    import asyncio

    # Создаём test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestTelegramCommands))
    suite.addTests(loader.loadTestsFromTestCase(TestTelegramHandlers))

    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)

    # Для async тестов используем asyncio
    async def run_async_tests():
        for test in suite:
            try:
                if hasattr(test, '_testMethodName'):
                    method = getattr(test, test._testMethodName)
                    if asyncio.iscoroutinefunction(method):
                        await method()
            except Exception as e:
                print(f"Ошибка в тесте: {e}")

    # Запускаем
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТЫ TELEGRAM БОТА")
    print("=" * 60)

    success = run_tests()

    print("\n" + "=" * 60)
    if success:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
    print("=" * 60)

    sys.exit(0 if success else 1)
