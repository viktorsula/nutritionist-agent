"""
Тесты P0-4: провайдер task_type с tool-calling (orchestrator/nutritionist_orchestrator)
обязан быть из TOOL_CAPABLE_PROVIDERS — иначе call_llm молча теряет tools/tool_handlers.
Три слоя: validate_llm_config (save-time), get_model_config/resolve_fallback_chain
(рантайм-самолечение, если в БД уже лежит непригодное значение).

Запуск: python -m pytest utils/test_llm_tool_provider_guard.py
"""

import unittest
from unittest.mock import patch

from utils.llm import (
    DEFAULT_TASK_MODEL_MAPPING,
    TOOL_CAPABLE_PROVIDERS,
    TOOL_REQUIRED_TASK_TYPES,
    get_model_config,
    resolve_fallback_chain,
    validate_llm_config,
)


class TestValidateLlmConfig(unittest.TestCase):
    def test_none_is_ok(self):
        self.assertEqual(validate_llm_config(None), [])

    def test_non_dict_rejected(self):
        self.assertTrue(validate_llm_config(["not", "a", "dict"]))

    def test_ok_when_orchestrator_is_claude(self):
        value = {"orchestrator": {"provider": "claude", "model": "claude-sonnet-4-6"}}
        self.assertEqual(validate_llm_config(value), [])

    def test_rejects_non_claude_orchestrator_provider(self):
        value = {"orchestrator": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}
        errors = validate_llm_config(value)
        self.assertTrue(errors)
        self.assertIn("orchestrator.provider", errors[0])

    def test_rejects_non_claude_nutritionist_orchestrator_provider(self):
        value = {"nutritionist_orchestrator": {"provider": "gemini", "model": "gemini-2.5-flash"}}
        errors = validate_llm_config(value)
        self.assertTrue(errors)

    def test_rejects_non_claude_fallback(self):
        value = {
            "orchestrator": {
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}],
            }
        }
        errors = validate_llm_config(value)
        self.assertTrue(any("fallbacks[0]" in e for e in errors))

    def test_claude_fallback_is_ok(self):
        value = {
            "orchestrator": {
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "fallbacks": [{"provider": "claude", "model": "claude-haiku-4-5"}],
            }
        }
        self.assertEqual(validate_llm_config(value), [])

    def test_ignores_non_tool_required_tasks(self):
        # dialog/analytics/etc не требуют tool-calling — любой провайдер ок.
        value = {"dialog": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}
        self.assertEqual(validate_llm_config(value), [])

    def test_ignores_task_not_present(self):
        self.assertEqual(validate_llm_config({}), [])


class TestGetModelConfigSelfHeals(unittest.TestCase):
    def test_uses_db_value_when_orchestrator_is_claude(self):
        db_cfg = {"orchestrator": {"provider": "claude", "model": "claude-opus-5"}}
        with patch("database.queries.get_setting", return_value=db_cfg):
            cfg = get_model_config("orchestrator")
        self.assertEqual(cfg["provider"], "claude")
        self.assertEqual(cfg["model"], "claude-opus-5")

    def test_falls_back_to_default_when_db_has_incapable_provider(self):
        db_cfg = {"orchestrator": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}
        with patch("database.queries.get_setting", return_value=db_cfg):
            cfg = get_model_config("orchestrator")
        # Игнорирует испорченное DB-значение, возвращает код-дефолт (claude).
        self.assertEqual(cfg["provider"], "claude")
        self.assertEqual(cfg, DEFAULT_TASK_MODEL_MAPPING["orchestrator"])

    def test_non_tool_task_unaffected_by_guard(self):
        db_cfg = {"dialog": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}
        with patch("database.queries.get_setting", return_value=db_cfg):
            cfg = get_model_config("dialog")
        self.assertEqual(cfg["provider"], "groq")


class TestResolveFallbackChainSelfHeals(unittest.TestCase):
    def test_keeps_claude_entries_for_orchestrator(self):
        db_cfg = {"orchestrator": {"fallbacks": [{"provider": "claude", "model": "claude-haiku-4-5"}]}}
        with patch("database.queries.get_setting", return_value=db_cfg):
            chain = resolve_fallback_chain("orchestrator")
        self.assertEqual(chain, [{"provider": "claude", "model": "claude-haiku-4-5"}])

    def test_filters_out_incapable_entries_for_orchestrator(self):
        db_cfg = {
            "orchestrator": {
                "fallbacks": [
                    {"provider": "groq", "model": "llama-3.3-70b-versatile"},
                    {"provider": "claude", "model": "claude-haiku-4-5"},
                ]
            }
        }
        with patch("database.queries.get_setting", return_value=db_cfg):
            chain = resolve_fallback_chain("orchestrator")
        self.assertEqual(chain, [{"provider": "claude", "model": "claude-haiku-4-5"}])

    def test_non_tool_task_unaffected_by_guard(self):
        db_cfg = {"dialog": {"fallbacks": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}]}}
        with patch("database.queries.get_setting", return_value=db_cfg):
            chain = resolve_fallback_chain("dialog")
        self.assertEqual(chain, [{"provider": "groq", "model": "llama-3.3-70b-versatile"}])


class TestToolCapableProvidersConsistency(unittest.TestCase):
    def test_default_orchestrator_configs_are_tool_capable(self):
        for task in TOOL_REQUIRED_TASK_TYPES:
            self.assertIn(DEFAULT_TASK_MODEL_MAPPING[task]["provider"], TOOL_CAPABLE_PROVIDERS)


if __name__ == "__main__":
    unittest.main()
