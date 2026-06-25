"""
Тесты трейсинга LangFuse (Этап 9) — без установленного SDK и без сети.

Проверяют:
1. No-op, когда нет ключей (is_enabled False, trace_llm_call ничего не делает)
2. trace_llm_call использует клиент, когда он включён (мок клиента)
3. trace_llm_call НИКОГДА не выбрасывает исключение (даже если клиент падает)
4. call_llm вызывает трейсинг (мок monitoring.trace_llm_call)

Запуск:
    PYTHONPATH=/workspaces/nutritionist-agent python3 monitoring/test_monitoring.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from monitoring import langfuse as lf


class TestDisabled(unittest.TestCase):
    def setUp(self):
        lf._reset_for_tests()

    @patch.dict("os.environ", {}, clear=True)
    def test_no_keys_means_disabled(self):
        self.assertFalse(lf.is_enabled())

    @patch.dict("os.environ", {}, clear=True)
    def test_trace_is_noop_without_keys(self):
        # Не должно бросать и не должно ничего отправлять
        lf.trace_llm_call(
            task_type="dialog", provider="groq", model="m",
            messages=[{"role": "user", "content": "hi"}],
            response={"content": "ok", "usage": {}},
        )
        lf.flush()  # тоже no-op


class TestEnabled(unittest.TestCase):
    def setUp(self):
        lf._reset_for_tests()

    def tearDown(self):
        lf._reset_for_tests()

    def test_trace_uses_client(self):
        fake_client = MagicMock()
        with patch("monitoring.langfuse._get_client", return_value=fake_client):
            lf.trace_llm_call(
                task_type="analysis", provider="claude", model="claude-x",
                messages=[{"role": "user", "content": "анализ"}],
                response={"content": "результат", "usage": {
                    "input_tokens": 10, "output_tokens": 20, "total_tokens": 30}},
                latency_ms=123,
            )
        fake_client.generation.assert_called_once()
        kwargs = fake_client.generation.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-x")
        self.assertEqual(kwargs["output"], "результат")
        self.assertEqual(kwargs["usage"]["total"], 30)
        self.assertEqual(kwargs["level"], "DEFAULT")

    def test_trace_error_sets_error_level(self):
        fake_client = MagicMock()
        with patch("monitoring.langfuse._get_client", return_value=fake_client):
            lf.trace_llm_call(
                task_type="dialog", provider="groq", model="m",
                messages=[{"role": "user", "content": "hi"}],
                error="rate limit",
            )
        kwargs = fake_client.generation.call_args.kwargs
        self.assertEqual(kwargs["level"], "ERROR")
        self.assertEqual(kwargs["status_message"], "rate limit")

    def test_trace_never_raises(self):
        broken = MagicMock()
        broken.generation.side_effect = RuntimeError("boom")
        with patch("monitoring.langfuse._get_client", return_value=broken):
            # Не должно поднять исключение
            lf.trace_llm_call(
                task_type="dialog", provider="groq", model="m",
                messages=[{"role": "user", "content": "hi"}],
                response={"content": "x", "usage": {}},
            )


class TestCallLlmIntegration(unittest.TestCase):
    @patch("utils.llm._call_groq")
    def test_call_llm_invokes_trace(self, mock_groq):
        from utils import llm

        mock_groq.return_value = {
            "content": "привет", "model": "llama-3.3-70b-versatile",
            "provider": "groq", "usage": {"input_tokens": 1, "output_tokens": 2,
                                          "total_tokens": 3}, "finish_reason": "stop",
        }

        with patch("monitoring.trace_llm_call") as mock_trace:
            result = llm.call_llm(
                task_type="dialog",
                messages=[{"role": "user", "content": "привет"}],
            )

        self.assertEqual(result["content"], "привет")
        mock_trace.assert_called_once()
        kwargs = mock_trace.call_args.kwargs
        self.assertEqual(kwargs["task_type"], "dialog")
        self.assertEqual(kwargs["provider"], "groq")
        self.assertIsNone(kwargs["error"])
        self.assertIsInstance(kwargs["latency_ms"], int)

    @patch("utils.llm._call_groq")
    def test_call_llm_traces_error(self, mock_groq):
        from utils import llm

        mock_groq.side_effect = RuntimeError("api down")

        with patch("monitoring.trace_llm_call") as mock_trace:
            # Все кандидаты падают (groq мокнут на сбой, резервы не сконфигурированы) →
            # LLMUnavailableError (подкласс RuntimeError) после перебора цепочки failover.
            with self.assertRaises(RuntimeError):
                llm.call_llm(
                    task_type="dialog",
                    messages=[{"role": "user", "content": "привет"}],
                )

        # Трейсится КАЖДАЯ попытка (failover, 20 июня), а не одна; первая — groq с "api down".
        mock_trace.assert_called()
        self.assertEqual(mock_trace.call_args_list[0].kwargs["error"], "api down")


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tc in (TestDisabled, TestEnabled, TestCallLlmIntegration):
        suite.addTests(loader.loadTestsFromTestCase(tc))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТЫ ТРЕЙСИНГА LANGFUSE (Этап 9)")
    print("=" * 60)
    success = run_tests()
    print("\n" + ("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ" if success else "❌ ЕСТЬ ПРОВАЛЫ"))
    sys.exit(0 if success else 1)
