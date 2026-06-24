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
from tg_bot.commands import start_command, help_command, status_command
from tg_bot.handlers import handle_text_message, handle_photo_message, handle_voice_message


class TestTelegramCommands(unittest.IsolatedAsyncioTestCase):
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

    @patch('tg_bot.commands.get_client_by_telegram_id')
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

    @patch('tg_bot.commands.get_client_by_telegram_id')
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

    @patch('tg_bot.commands.get_client_by_telegram_id')
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

    @patch('tg_bot.commands.get_client_by_telegram_id')
    async def test_help_command_unregistered_user(self, mock_get_client):
        """Тест /help для незарегистрированного пользователя"""
        mock_get_client.return_value = None

        await help_command(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("не зарегистрированы", message_text)


class TestTelegramHandlers(unittest.IsolatedAsyncioTestCase):
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

    @patch('tg_bot.handlers.get_client_by_telegram_id')
    async def test_handle_text_unregistered_user(self, mock_get_client):
        """Тест обработки текста от незарегистрированного пользователя"""
        mock_get_client.return_value = None

        await handle_text_message(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("не зарегистрированы", message_text)

    @patch('tg_bot.handlers.route_message')
    @patch('tg_bot.handlers.get_client_by_telegram_id')
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

        # Проверяем что вызвали route_message.
        # Для Telegram роутеру передаётся telegram_id (он сам резолвит client_id
        # через get_user_by_telegram_id), а НЕ users.id.
        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]
        self.assertEqual(call_kwargs["user_id"], "123456789")
        self.assertEqual(call_kwargs["channel"], "telegram")

        # Проверяем отправку ответа
        self.message.reply_text.assert_called_once()

    # --- Фото (vision) ---

    def _attach_photo(self, image_bytes: bytes = b"\xff\xd8\xff\xee_fake_jpeg", caption=None):
        """Добавляет к message мок фото с скачиваемыми байтами."""
        tg_file = Mock()
        tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(image_bytes))

        photo_size = Mock()
        photo_size.get_file = AsyncMock(return_value=tg_file)

        # В Telegram message.photo — список размеров; берём последний (наибольший)
        self.message.photo = [photo_size]
        self.message.caption = caption

    @patch('tg_bot.handlers.route_message')
    @patch('tg_bot.handlers.get_client_by_telegram_id')
    async def test_handle_photo_success(self, mock_get_client, mock_route):
        """Фото: скачивается и передаётся в роутер как message_type='photo' с image_bytes."""
        mock_client = Mock()
        mock_client.user_id = "user-uuid-123"
        mock_get_client.return_value = mock_client

        mock_route.return_value = {"success": True, "message": "Вижу тарелку!"}

        self._attach_photo(caption="мой обед")

        await handle_photo_message(self.update, self.context)

        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]
        self.assertEqual(call_kwargs["message_type"], "photo")
        self.assertEqual(call_kwargs["message"], "мой обед")  # caption → message
        self.assertIn("image_bytes", call_kwargs["metadata"])
        self.assertIsInstance(call_kwargs["metadata"]["image_bytes"], bytes)
        self.assertEqual(call_kwargs["metadata"]["mime_type"], "image/jpeg")

        self.message.reply_text.assert_called_once()

    @patch('tg_bot.handlers.get_client_by_telegram_id')
    async def test_handle_photo_unregistered_user(self, mock_get_client):
        """Фото от незарегистрированного — не качаем и не вызываем роутер."""
        mock_get_client.return_value = None
        self._attach_photo()

        await handle_photo_message(self.update, self.context)

        self.message.reply_text.assert_called_once()
        self.assertIn("не зарегистрированы", self.message.reply_text.call_args[0][0])

    # --- Голос (Whisper в оркестраторе) ---

    def _attach_voice(self, audio_bytes: bytes = b"OggS_fake_voice", file_name=None):
        """Добавляет к message мок голосового с скачиваемыми байтами."""
        tg_file = Mock()
        tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(audio_bytes))

        voice = Mock(spec=["get_file"])  # у voice нет file_name → handler подставит voice.ogg
        voice.get_file = AsyncMock(return_value=tg_file)

        self.message.voice = voice
        self.message.audio = None

    @patch('tg_bot.handlers.route_message')
    @patch('tg_bot.handlers.get_client_by_telegram_id')
    async def test_handle_voice_success(self, mock_get_client, mock_route):
        """Голос: скачивается и передаётся как message_type='voice' с audio_bytes (текст пустой)."""
        mock_client = Mock()
        mock_client.user_id = "user-uuid-123"
        mock_get_client.return_value = mock_client

        mock_route.return_value = {"success": True, "message": "Записал!"}

        self._attach_voice()

        await handle_voice_message(self.update, self.context)

        mock_route.assert_called_once()
        call_kwargs = mock_route.call_args[1]
        self.assertEqual(call_kwargs["message_type"], "voice")
        self.assertEqual(call_kwargs["message"], "")  # транскрипцию делает оркестратор
        self.assertIn("audio_bytes", call_kwargs["metadata"])
        self.assertIsInstance(call_kwargs["metadata"]["audio_bytes"], bytes)
        self.assertEqual(call_kwargs["metadata"]["audio_name"], "voice.ogg")

        self.message.reply_text.assert_called_once()

    @patch('tg_bot.handlers.route_message')
    @patch('tg_bot.handlers.get_client_by_telegram_id')
    async def test_handle_voice_access_denied(self, mock_get_client, mock_route):
        """Голос: при access_denied клиент получает сообщение об ограничении доступа."""
        mock_client = Mock()
        mock_client.user_id = "user-uuid-123"
        mock_get_client.return_value = mock_client

        mock_route.return_value = {
            "success": False,
            "error": "access_denied",
            "message": "Подписка неактивна.",
        }

        self._attach_voice()

        await handle_voice_message(self.update, self.context)

        self.message.reply_text.assert_called_once()
        self.assertIn("Доступ ограничен", self.message.reply_text.call_args[0][0])


def run_tests():
    """Запуск всех тестов через стандартный раннер (поддерживает async-тесты)."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestTelegramCommands))
    suite.addTests(loader.loadTestsFromTestCase(TestTelegramHandlers))

    runner = unittest.TextTestRunner(verbosity=2)
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
