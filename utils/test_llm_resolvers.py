"""
Тесты резолверов моделей (Фаза 1 централизации llm_config).

Проверяют приоритет «БД (system_settings.llm_config) → код-дефолт» и жёсткую
деградацию: любая ошибка/отсутствие записи → код-константы, прод не падает.
"""

from unittest.mock import patch

from utils.llm import resolve_fallback_chain, get_model_config, TASK_FALLBACK_CHAINS
from utils.vision import resolve_vision_model, VISION_MODEL


# ── resolve_fallback_chain ───────────────────────────────────────────────────

def test_fallback_from_db_when_present():
    cfg = {"dialog": {"provider": "groq", "model": "x",
                      "fallbacks": [{"provider": "gemini", "model": "gemini-3.5-flash"}]}}
    with patch("database.queries.get_setting", return_value=cfg):
        assert resolve_fallback_chain("dialog") == [{"provider": "gemini", "model": "gemini-3.5-flash"}]


def test_fallback_db_empty_list_is_honored():
    """Явный пустой fallbacks из БД = осознанный выбор «без резерва», не код-дефолт."""
    cfg = {"dialog": {"provider": "groq", "model": "x", "fallbacks": []}}
    with patch("database.queries.get_setting", return_value=cfg):
        assert resolve_fallback_chain("dialog") == []


def test_fallback_default_when_no_fallbacks_key():
    """Задача есть в БД, но без ключа fallbacks → сохраняем код-резерв (не теряем устойчивость)."""
    cfg = {"dialog": {"provider": "groq", "model": "x"}}
    with patch("database.queries.get_setting", return_value=cfg):
        assert resolve_fallback_chain("dialog") == TASK_FALLBACK_CHAINS["dialog"]


def test_fallback_default_when_db_missing():
    with patch("database.queries.get_setting", return_value=None):
        assert resolve_fallback_chain("analytics") == TASK_FALLBACK_CHAINS["analytics"]


def test_fallback_default_when_db_raises():
    with patch("database.queries.get_setting", side_effect=RuntimeError("db down")):
        assert resolve_fallback_chain("dialog") == TASK_FALLBACK_CHAINS["dialog"]


def test_fallback_filters_malformed_entries():
    cfg = {"dialog": {"fallbacks": [{"provider": "gemini"}, {"model": "m"},
                                    {"provider": "groq", "model": "llama"}]}}
    with patch("database.queries.get_setting", return_value=cfg):
        assert resolve_fallback_chain("dialog") == [{"provider": "groq", "model": "llama"}]


# ── get_model_config: основной конфиг без fallbacks ──────────────────────────

def test_get_model_config_strips_fallbacks_from_db():
    cfg = {"dialog": {"provider": "groq", "model": "x", "temperature": 0.7, "max_tokens": 100,
                      "fallbacks": [{"provider": "gemini", "model": "g"}]}}
    with patch("database.queries.get_setting", return_value=cfg):
        out = get_model_config("dialog")
    assert "fallbacks" not in out
    assert out["provider"] == "groq" and out["model"] == "x"


# ── resolve_vision_model ─────────────────────────────────────────────────────

def test_vision_model_from_db():
    cfg = {"vision": {"provider": "gemini", "model": "gemini-3.5-flash"}}
    with patch("database.queries.get_setting", return_value=cfg):
        assert resolve_vision_model() == "gemini-3.5-flash"


def test_vision_model_default_when_missing():
    with patch("database.queries.get_setting", return_value=None):
        assert resolve_vision_model() == VISION_MODEL


def test_vision_model_default_when_raises():
    with patch("database.queries.get_setting", side_effect=RuntimeError("x")):
        assert resolve_vision_model() == VISION_MODEL
