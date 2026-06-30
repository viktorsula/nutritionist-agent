"""
Тесты generic OpenAI-совместимого адаптера (Фаза C): реестр кастом-провайдеров,
доступность, диспетчеризация call_llm и контракт ответа адаптера.
"""

import os
from unittest.mock import patch, MagicMock

from utils.llm import (
    get_custom_providers,
    list_available_providers,
    call_llm,
    _call_openai_compatible,
)

REGISTRY = {"mistral": {"base_url": "https://api.mistral.ai/v1", "api_key_env": "MISTRAL_API_KEY"}}


def test_get_custom_providers_parses_and_filters():
    cfg = {"_providers": {
        "mistral": {"base_url": "https://api.mistral.ai/v1", "api_key_env": "MISTRAL_API_KEY"},
        "bad": {"base_url": "x"},  # без api_key_env → отброшен
    }}
    with patch("database.queries.get_setting", return_value=cfg):
        assert get_custom_providers() == REGISTRY


def test_get_custom_providers_empty_without_registry():
    with patch("database.queries.get_setting", return_value={"dialog": {}}):
        assert get_custom_providers() == {}


def test_list_available_includes_custom_when_key_set():
    with patch("utils.llm.get_custom_providers", return_value=REGISTRY), \
         patch.dict(os.environ, {"MISTRAL_API_KEY": "k"}):
        assert "mistral" in list_available_providers()


def test_list_available_excludes_custom_without_key():
    with patch("utils.llm.get_custom_providers", return_value=REGISTRY), \
         patch.dict(os.environ, {"MISTRAL_API_KEY": ""}):
        assert "mistral" not in list_available_providers()


def test_call_llm_dispatches_custom_to_adapter():
    fake = {"content": "hi", "model": "mistral-large", "provider": "mistral", "usage": {}}
    with patch("utils.llm.get_custom_providers", return_value=REGISTRY), \
         patch("utils.llm._call_openai_compatible", return_value=fake) as adapter:
        out = call_llm(
            provider="mistral", model="mistral-large",
            messages=[{"role": "user", "content": "ping"}],
        )
    adapter.assert_called_once()
    cand = adapter.call_args.args[1]  # (messages, cand, stream)
    assert cand["base_url"] == "https://api.mistral.ai/v1"
    assert cand["api_key_env"] == "MISTRAL_API_KEY"
    assert out["provider"] == "mistral"


def test_call_openai_compatible_builds_response():
    msg = MagicMock()
    msg.content = "pong"
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    client = MagicMock()
    client.chat.completions.create.return_value = resp

    cfg = {"provider": "mistral", "model": "m", "base_url": "http://x/v1", "api_key_env": "MISTRAL_API_KEY"}
    with patch.dict(os.environ, {"MISTRAL_API_KEY": "k"}), \
         patch("openai.OpenAI", return_value=client):
        out = _call_openai_compatible([{"role": "user", "content": "hi"}], cfg)

    assert out["content"] == "pong"
    assert out["provider"] == "mistral"
    assert out["usage"]["total_tokens"] == 3


def test_call_openai_compatible_requires_key():
    cfg = {"provider": "mistral", "model": "m", "base_url": "http://x/v1", "api_key_env": "MISTRAL_API_KEY"}
    with patch.dict(os.environ, {"MISTRAL_API_KEY": ""}):
        try:
            _call_openai_compatible([{"role": "user", "content": "hi"}], cfg)
            assert False, "ожидали RuntimeError"
        except RuntimeError as e:
            assert "MISTRAL_API_KEY" in str(e)
