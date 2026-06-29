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
        # /start без deep-link payload — иначе срабатывает ветка привязки по токену.
        self.context.args = []

    @patch('tg_bot.commands.get_user_by_telegram_id', return_value=None)
    @patch('tg_bot.commands.get_client_by_telegram_id')
    async def test_start_command_new_user(self, mock_get_client, _mock_get_user):
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

    @patch('tg_bot.commands.get_user_by_telegram_id', return_value=None)
    @patch('tg_bot.commands.get_client_by_telegram_id')
    async def test_start_command_existing_user(self, mock_get_client, _mock_get_user):
        """Тест /start для существующего пользователя (queries возвращает dict)"""
        mock_get_client.return_value = {"id": "cli-1", "name": "Иван Петров"}

        await start_command(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("возвращением", message_text)
        self.assertIn("Иван Петров", message_text)

    @patch('tg_bot.commands.link_client_telegram')
    @patch('tg_bot.commands.get_client_by_telegram_id', return_value=None)
    @patch('tg_bot.commands.get_client_by_link_token')
    @patch('tg_bot.commands.get_user_by_telegram_id', return_value=None)
    async def test_start_link_token_success(
        self, _mock_user, mock_by_token, _mock_by_tg, mock_link
    ):
        """/start <token> с валидным токеном → привязка + приветствие."""
        self.context.args = ["validtoken"]
        mock_by_token.return_value = {
            "id": "cli-1",
            "name": "Kate",
            "telegram_link_token_expires_at": None,
        }

        await start_command(self.update, self.context)

        mock_link.assert_called_once_with("cli-1", self.user.id)
        message_text = self.message.reply_text.call_args[0][0]
        self.assertIn("привязан", message_text.lower())
        self.assertIn("Kate", message_text)

    @patch('tg_bot.commands.link_client_telegram')
    @patch('tg_bot.commands.get_client_by_link_token', return_value=None)
    @patch('tg_bot.commands.get_user_by_telegram_id', return_value=None)
    async def test_start_link_token_invalid(self, _mock_user, _mock_by_token, mock_link):
        """/start <token> с неизвестным токеном → отказ, привязки нет."""
        self.context.args = ["badtoken"]

        await start_command(self.update, self.context)

        mock_link.assert_not_called()
        message_text = self.message.reply_text.call_args[0][0]
        self.assertIn("недействительна", message_text.lower())

    @patch('tg_bot.commands.link_client_telegram')
    @patch('tg_bot.commands.get_client_by_link_token')
    @patch('tg_bot.commands.get_user_by_telegram_id', return_value=None)
    async def test_start_link_token_expired(self, _mock_user, mock_by_token, mock_link):
        """/start <token> с истёкшим токеном → отказ, привязки нет."""
        self.context.args = ["oldtoken"]
        mock_by_token.return_value = {
            "id": "cli-1",
            "name": "Kate",
            "telegram_link_token_expires_at": "2000-01-01T00:00:00+00:00",
        }

        await start_command(self.update, self.context)

        mock_link.assert_not_called()
        message_text = self.message.reply_text.call_args[0][0]
        self.assertIn("истёк", message_text.lower())

    @patch('tg_bot.commands.get_user_by_telegram_id')
    async def test_start_command_nutritionist(self, mock_get_user):
        """Тест /start для нутрициолога (распознан по NUTRITIONIST_TELEGRAM_ID)"""
        mock_get_user.return_value = {"id": "nut-1", "role": "nutritionist"}

        await start_command(self.update, self.context)

        self.message.reply_text.assert_called_once()
        message_text = self.message.reply_text.call_args[0][0]
        self.assertIn("ассистент", message_text.lower())
        self.assertIn("алерт", message_text.lower())

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
        self.update.effective_chat = self.chat
        self.update.message = self.message
        self.message.media_group_id = None

        self.context = Mock(spec=ContextTypes.DEFAULT_TYPE)

        # Фаза 2: тесты хендлеров проверяют контракт «хендлер → немедленная диспетчеризация».
        # Отключаем turn-буфер (debounce=0 → обработка сразу), чтобы assert'ы на route_message
        # оставались валидны. Буферизацию проверяет отдельный TestTurnBuffer.
        os.environ["TELEGRAM_TURN_DEBOUNCE_SEC"] = "0"

    @patch('tg_bot.handlers.get_user_by_telegram_id')
    async def test_handle_text_unregistered_user(self, mock_get_client):
        """Тест обработки текста от незарегистрированного пользователя"""
        mock_get_client.return_value = None

        await handle_text_message(self.update, self.context)

        self.message.reply_text.assert_called_once()
        call_args = self.message.reply_text.call_args
        message_text = call_args[0][0]

        self.assertIn("не зарегистрированы", message_text)

    @patch('tg_bot.handlers.route_message')
    @patch('tg_bot.handlers.get_user_by_telegram_id')
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
    @patch('tg_bot.handlers.get_user_by_telegram_id')
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

    @patch('tg_bot.handlers.get_user_by_telegram_id')
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
    @patch('tg_bot.handlers.get_user_by_telegram_id')
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
    @patch('tg_bot.handlers.get_user_by_telegram_id')
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


class TestTurnBuffer(unittest.IsolatedAsyncioTestCase):
    """Тесты turn-буфера (Фаза 2): склейка серии текстов и альбомов."""

    def setUp(self):
        import asyncio  # noqa: F401 — для читаемости
        from tg_bot import turn_buffer

        self.turn_buffer = turn_buffer
        turn_buffer._buffers.clear()
        # Маленький debounce, чтобы тесты были быстрыми.
        os.environ["TELEGRAM_TURN_DEBOUNCE_SEC"] = "0.05"

    def _mk_update(self, chat_id=555, text="", caption=None, message_id=1):
        user = Mock(spec=User)
        user.id = chat_id
        user.username = "u"

        chat = Mock(spec=Chat)
        chat.id = chat_id
        chat.send_action = AsyncMock()

        msg = Mock(spec=Message)
        msg.text = text
        msg.caption = caption
        msg.message_id = message_id
        msg.reply_text = AsyncMock()
        msg.chat = chat

        upd = Mock(spec=Update)
        upd.effective_user = user
        upd.effective_chat = chat
        upd.message = msg
        return upd

    async def _wait_flush(self):
        import asyncio
        await asyncio.sleep(0.2)  # > debounce (0.05)

    @patch("tg_bot.handlers._dispatch_to_router", new_callable=AsyncMock)
    async def test_text_burst_coalesced(self, mock_dispatch):
        """Три текста подряд → один ход с конкатенацией."""
        for i, txt in enumerate(["вешу 80", "и съел кашу", "как дела?"]):
            await self.turn_buffer.enqueue(
                {"kind": "text", "update": self._mk_update(text=txt, message_id=i), "message": txt}
            )
        await self._wait_flush()

        mock_dispatch.assert_called_once()
        kwargs = mock_dispatch.call_args.kwargs
        self.assertEqual(kwargs["message_type"], "text")
        self.assertEqual(kwargs["message"], "вешу 80\nи съел кашу\nкак дела?")

    @patch("tg_bot.handlers._dispatch_to_router", new_callable=AsyncMock)
    async def test_album_coalesced_to_first_photo(self, mock_dispatch):
        """Альбом (один media_group_id) → один ход по первому фото + heads-up «получено N»."""
        updates = []
        for i in range(3):
            upd = self._mk_update(caption=("обед" if i == 0 else None), message_id=i)
            updates.append(upd)
            await self.turn_buffer.enqueue({
                "kind": "photo",
                "update": upd,
                "message": upd.message.caption or "",
                "media_group_id": "ALBUM1",
                "metadata": {"image_bytes": b"\xff\xd8", "mime_type": "image/jpeg"},
            })
        await self._wait_flush()

        mock_dispatch.assert_called_once()
        kwargs = mock_dispatch.call_args.kwargs
        self.assertEqual(kwargs["message_type"], "photo")
        self.assertEqual(kwargs["message"], "обед")          # общая подпись альбома
        self.assertEqual(kwargs["metadata"]["album_count"], 3)
        updates[0].message.reply_text.assert_called_once()    # heads-up «получено N фото»

    @patch("tg_bot.handlers._dispatch_to_router", new_callable=AsyncMock)
    async def test_mixed_text_then_voice_two_turns(self, mock_dispatch):
        """Текст + голос → два отдельных хода."""
        await self.turn_buffer.enqueue(
            {"kind": "text", "update": self._mk_update(text="привет"), "message": "привет"}
        )
        await self.turn_buffer.enqueue({
            "kind": "voice",
            "update": self._mk_update(message_id=2),
            "message": "",
            "metadata": {"audio_bytes": b"ogg", "audio_name": "voice.ogg"},
        })
        await self._wait_flush()

        self.assertEqual(mock_dispatch.call_count, 2)
        types = [c.kwargs["message_type"] for c in mock_dispatch.call_args_list]
        self.assertEqual(types, ["text", "voice"])

    @patch("tg_bot.handlers._dispatch_to_router", new_callable=AsyncMock)
    async def test_debounce_resets_on_new_message(self, mock_dispatch):
        """Сообщение в пределах окна перевзводит таймер → единый сброс обоими сообщениями."""
        import asyncio
        await self.turn_buffer.enqueue(
            {"kind": "text", "update": self._mk_update(text="раз"), "message": "раз"}
        )
        await asyncio.sleep(0.02)  # < debounce
        await self.turn_buffer.enqueue(
            {"kind": "text", "update": self._mk_update(text="два", message_id=2), "message": "два"}
        )
        await self._wait_flush()

        mock_dispatch.assert_called_once()
        self.assertEqual(mock_dispatch.call_args.kwargs["message"], "раз\nдва")


def run_tests():
    """Запуск всех тестов через стандартный раннер (поддерживает async-тесты)."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestTelegramCommands))
    suite.addTests(loader.loadTestsFromTestCase(TestTelegramHandlers))
    suite.addTests(loader.loadTestsFromTestCase(TestTurnBuffer))

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
