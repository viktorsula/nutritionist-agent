"""
Тесты agents/nutritionist/audit_agent.py (NEW-1 — проактивный аудит клиента).
Запуск: python -m pytest agents/nutritionist/test_audit_agent.py
"""

import json
import unittest
from unittest.mock import patch

from agents.nutritionist.audit_agent import run_audit_for_client, MAX_FINDINGS_PER_RUN


def _llm(findings):
    return {"content": json.dumps({"findings": findings}), "model": "m", "usage": {}}


class TestRunAuditForClient(unittest.TestCase):
    def setUp(self):
        patcher1 = patch(
            "agents.nutritionist.audit_agent._gather_client_data",
            return_value=("данные клиента", []),
        )
        patcher2 = patch(
            "agents.nutritionist.audit_agent._vector_retrieve", return_value="",
        )
        patcher3 = patch(
            "agents.nutritionist.audit_agent.queries.get_client_by_id",
            return_value={"nutritionist_notes": "избегать сахар"},
        )
        self.gather_mock = patcher1.start()
        self.vector_mock = patcher2.start()
        self.client_mock = patcher3.start()
        self.addCleanup(patcher1.stop)
        self.addCleanup(patcher2.stop)
        self.addCleanup(patcher3.stop)

    def test_no_findings_writes_nothing(self):
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm([])), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 0)
        insert_mock.assert_not_called()

    def test_findings_are_written(self):
        findings = [
            {"title": "Расхождение по ограничениям", "description": "план не учитывает заметку", "severity": "medium"},
        ]
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm(findings)), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 1)
        insert_mock.assert_called_once_with(
            client_id="c1",
            title="Расхождение по ограничениям",
            description="план не учитывает заметку",
            severity="medium",
        )

    def test_invalid_severity_clamped_to_medium(self):
        findings = [{"title": "T", "description": "D", "severity": "critical"}]
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm(findings)), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            run_audit_for_client("c1")
        self.assertEqual(insert_mock.call_args.kwargs["severity"], "medium")

    def test_missing_severity_defaults_to_medium(self):
        findings = [{"title": "T", "description": "D"}]
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm(findings)), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            run_audit_for_client("c1")
        self.assertEqual(insert_mock.call_args.kwargs["severity"], "medium")

    def test_malformed_findings_are_filtered_out(self):
        findings = [
            {"title": "OK", "description": "valid"},
            {"title": "no description"},
            {"description": "no title"},
            "not a dict",
        ]
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm(findings)), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 1)
        insert_mock.assert_called_once()

    def test_caps_at_max_findings_per_run(self):
        findings = [
            {"title": f"T{i}", "description": f"D{i}"} for i in range(MAX_FINDINGS_PER_RUN + 5)
        ]
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm(findings)), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, MAX_FINDINGS_PER_RUN)
        self.assertEqual(insert_mock.call_count, MAX_FINDINGS_PER_RUN)

    def test_llm_failure_returns_zero_no_crash(self):
        with patch("agents.nutritionist.audit_agent.call_llm", side_effect=RuntimeError("down")), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding") as insert_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 0)
        insert_mock.assert_not_called()

    def test_gather_client_data_failure_returns_zero_no_crash(self):
        self.gather_mock.side_effect = RuntimeError("db down")
        with patch("agents.nutritionist.audit_agent.call_llm") as llm_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 0)
        llm_mock.assert_not_called()

    def test_notes_fetch_failure_is_best_effort(self):
        # Заметки не получены — аудит всё равно продолжается (notes="").
        self.client_mock.side_effect = RuntimeError("db down")
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm([])) as llm_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 0)
        llm_mock.assert_called_once()

    def test_insert_failure_for_one_finding_does_not_stop_others(self):
        findings = [
            {"title": "T1", "description": "D1"},
            {"title": "T2", "description": "D2"},
        ]
        with patch("agents.nutritionist.audit_agent.call_llm", return_value=_llm(findings)), \
             patch("agents.nutritionist.audit_agent.queries.insert_audit_finding",
                   side_effect=[RuntimeError("boom"), {"id": "f2"}]) as insert_mock:
            written = run_audit_for_client("c1")
        self.assertEqual(written, 1)
        self.assertEqual(insert_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
