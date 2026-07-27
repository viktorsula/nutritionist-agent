"""
Тесты адаптеров провайдеров (P2-15): подготовка сообщений под Gemini и унификация
finish_reason.

Почему это важно: Gemini используется как РЕЗЕРВ. Ошибка здесь проявляется только тогда,
когда основная модель уже упала, — то есть в момент, когда второго сбоя быть не должно.
"""

from utils.llm import _gemini_payload, normalize_finish_reason


class TestGeminiPayload:
    def test_system_goes_to_instruction_not_into_contents(self):
        # Ядро P2-15: раньше system маппился в роль 'user', и [system, user] давал два
        # 'user' подряд — Gemini отвечает на такое 400.
        si, contents = _gemini_payload([
            {"role": "system", "content": "ты помощник"},
            {"role": "user", "content": "привет"},
        ])
        assert si == "ты помощник"
        assert [c["role"] for c in contents] == ["user"]
        assert contents[0]["parts"] == ["привет"]

    def test_roles_alternate_after_merge(self):
        si, contents = _gemini_payload([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "первое"},
            {"role": "user", "content": "второе"},
            {"role": "assistant", "content": "ответ"},
            {"role": "user", "content": "третье"},
        ])
        roles = [c["role"] for c in contents]
        assert roles == ["user", "model", "user"]
        # Подряд идущие реплики одной роли склеены, а не отброшены.
        assert "первое" in contents[0]["parts"][0]
        assert "второе" in contents[0]["parts"][0]

    def test_assistant_maps_to_model(self):
        _, contents = _gemini_payload([{"role": "assistant", "content": "ответ"}])
        assert contents[0]["role"] == "model"

    def test_several_system_messages_join(self):
        si, contents = _gemini_payload([
            {"role": "system", "content": "часть 1"},
            {"role": "system", "content": "часть 2"},
            {"role": "user", "content": "вопрос"},
        ])
        assert "часть 1" in si and "часть 2" in si
        assert len(contents) == 1

    def test_no_system_gives_none_instruction(self):
        si, contents = _gemini_payload([{"role": "user", "content": "привет"}])
        assert si is None
        assert len(contents) == 1


class TestNormalizeFinishReason:
    def test_length_from_every_provider(self):
        # Главное практическое применение: понять, что ответ ОБОРВАН по лимиту.
        # Обрезанный JSON или обрезанный совет выглядят как валидный результат.
        assert normalize_finish_reason("length") == "length"        # OpenAI / Groq
        assert normalize_finish_reason("max_tokens") == "length"    # Anthropic
        assert normalize_finish_reason("MAX_TOKENS") == "length"    # Gemini

    def test_stop_from_every_provider(self):
        assert normalize_finish_reason("stop") == "stop"
        assert normalize_finish_reason("end_turn") == "stop"
        assert normalize_finish_reason("STOP") == "stop"

    def test_tool_use_and_filter(self):
        assert normalize_finish_reason("tool_calls") == "tool_use"
        assert normalize_finish_reason("tool_use") == "tool_use"
        assert normalize_finish_reason("SAFETY") == "filter"
        assert normalize_finish_reason("content_filter") == "filter"

    def test_unknown_and_none_are_other(self):
        assert normalize_finish_reason("что-то новое") == "other"
        assert normalize_finish_reason(None) == "other"
