"""
Тесты rolling-summary (agents/client/summary.py). Без сети: LLM и queries мокаются.
Проверяем порог обновления, разворот хронологии и запись маркера.
"""

import unittest
from unittest.mock import patch

from agents.client import summary as S


class TestBuildRollingSummary(unittest.TestCase):
    def test_no_new_messages_returns_previous(self):
        with patch.object(S, "call_llm") as m:
            out = S.build_rolling_summary("prev", [])
        self.assertEqual(out, "prev")
        m.assert_not_called()

    def test_llm_failure_returns_previous(self):
        with patch.object(S, "call_llm", side_effect=RuntimeError("down")):
            out = S.build_rolling_summary("prev", ["Клиент: привет"])
        self.assertEqual(out, "prev")

    def test_summary_capped(self):
        long = "x" * 5000
        with patch.object(S, "call_llm", return_value={"content": long}):
            out = S.build_rolling_summary("", ["Клиент: тест"])
        self.assertEqual(len(out), S.MAX_SUMMARY_CHARS)


class TestUpdateRollingSummary(unittest.TestCase):
    def _state(self, prev_count=0, summary=""):
        return {
            "client_id": "cl-1",
            "client": {"conversation_summary": summary, "summary_message_count": prev_count},
        }

    def test_below_threshold_no_update(self):
        with patch("database.queries.count_client_dialog_messages", return_value=5), \
             patch("database.queries.update_conversation_summary") as upd:
            S.update_rolling_summary(self._state(prev_count=0))
        upd.assert_not_called()

    def test_threshold_triggers_update_with_chronology(self):
        rows = [  # свежие сверху (как отдаёт get_conversations)
            {"role": "agent", "message_text": "новее"},
            {"role": "client", "message_text": "старее"},
        ]
        captured = {}
        with patch("database.queries.count_client_dialog_messages", return_value=10), \
             patch("database.queries.get_conversations", return_value=rows), \
             patch.object(S, "build_rolling_summary", return_value="NEW") as build, \
             patch("database.queries.update_conversation_summary",
                   side_effect=lambda cid, s, c: captured.update(cid=cid, s=s, c=c)):
            S.update_rolling_summary(self._state(prev_count=0, summary="OLD"))

        # хронология: client(старее) раньше agent(новее)
        msgs = build.call_args.args[1]
        self.assertEqual(msgs, ["Клиент: старее", "Ассистент: новее"])
        self.assertEqual(build.call_args.args[0], "OLD")
        self.assertEqual(captured, {"cid": "cl-1", "s": "NEW", "c": 10})

    def test_no_client_id_noop(self):
        with patch("database.queries.count_client_dialog_messages") as cnt:
            S.update_rolling_summary({"client_id": None, "client": {}})
        cnt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
