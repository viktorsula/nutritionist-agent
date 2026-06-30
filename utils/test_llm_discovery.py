"""
Тесты обнаружения/проверки моделей (Фаза A окна «LLM-модели»):
list_provider_models (ListModels + фильтр + кэш) и test_model (пинг).
"""

import os
from unittest.mock import patch, MagicMock

from utils.llm import list_provider_models, _MODELS_CACHE
from utils.llm import test_model as run_test_model  # импорт под алиасом: иначе pytest соберёт как тест


def _resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


def setup_function():
    _MODELS_CACHE.clear()


def test_list_gemini_filters_and_caches():
    payload = {
        "models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/gemini-2.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
        ]
    }
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "x"}), \
         patch("utils.llm.httpx.get", return_value=_resp(payload)):
        models = list_provider_models("gemini")
    assert models == ["gemini-2.5-flash", "gemini-2.5-pro"]  # без embedding и image-генерации

    # Кэш: повторный вызов не дёргает httpx.
    with patch("utils.llm.httpx.get") as g2:
        assert list_provider_models("gemini") == models
        g2.assert_not_called()


def test_list_groq_filters_non_chat():
    payload = {"data": [
        {"id": "llama-3.3-70b-versatile"},
        {"id": "whisper-large-v3"},
        {"id": "llama-guard-4"},
    ]}
    with patch.dict(os.environ, {"GROQ_API_KEY": "x"}), \
         patch("utils.llm.httpx.get", return_value=_resp(payload)):
        assert list_provider_models("groq") == ["llama-3.3-70b-versatile"]


def test_list_unknown_provider_returns_empty():
    assert list_provider_models("openai") == []


def test_list_no_key_returns_empty():
    with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
        assert list_provider_models("groq") == []


def test_list_swallows_http_error():
    with patch.dict(os.environ, {"GROQ_API_KEY": "x"}), \
         patch("utils.llm.httpx.get", side_effect=RuntimeError("boom")):
        assert list_provider_models("groq") == []


def test_test_model_ok():
    with patch("utils.llm.call_llm", return_value={"model": "gemini-2.5-flash"}):
        out = run_test_model("gemini", "gemini-2.5-flash")
    assert out["ok"] is True
    assert out["error"] is None
    assert out["model"] == "gemini-2.5-flash"
    assert isinstance(out["latency_ms"], int)


def test_test_model_error():
    with patch("utils.llm.call_llm", side_effect=RuntimeError("401 Invalid API Key")):
        out = run_test_model("groq", "bad-model")
    assert out["ok"] is False
    assert "401" in out["error"]
    assert out["model"] == "bad-model"
