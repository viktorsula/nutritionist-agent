"""
Ф3 Шаг 0 — наблюдаемость покрытия: рекордер + обе точки развилки (клиент/нутрициолог)
помечают ход ровно одним путём (orchestrator / graph_flag_off / graph_fallback).
"""

from unittest.mock import patch, MagicMock

from agents.core import coverage


# ── Рекордер ─────────────────────────────────────────────────────────────────
def test_record_and_snapshot():
    coverage.reset()
    coverage.record_turn("client", "orchestrator")
    coverage.record_turn("client", "orchestrator")
    coverage.record_turn("client", "graph_fallback", reason="llm_unavailable")
    coverage.record_turn("nutritionist", "graph_flag_off")
    snap = coverage.snapshot()
    assert snap["client:orchestrator"] == 2
    assert snap["client:graph_fallback"] == 1
    assert snap["nutritionist:graph_flag_off"] == 1


def test_unknown_path_counts_as_fallback():
    coverage.reset()
    coverage.record_turn("client", "weird")
    assert coverage.snapshot().get("client:graph_fallback") == 1


# ── Развилка клиента (process_client_message) ────────────────────────────────
def test_client_orchestrator_success_records_orchestrator():
    from agents.client import orchestrator as co
    coverage.reset()
    with patch("agents.client.agent_orchestrator.should_use", return_value=True), \
         patch("agents.client.agent_orchestrator.process", return_value={"message": "ok"}) as p, \
         patch("agents.client.orchestrator.create_client_graph") as g:
        res = co.process_client_message("cid", "привет", "web", "text", {}, {})
    assert res == {"message": "ok"}
    p.assert_called_once()
    g.assert_not_called()  # граф НЕ трогаем на успехе оркестратора
    assert coverage.snapshot().get("client:orchestrator") == 1


def test_client_flag_off_records_and_uses_graph():
    from agents.client import orchestrator as co
    coverage.reset()
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {"final_message": "g"}
    with patch("agents.client.agent_orchestrator.should_use", return_value=False), \
         patch("agents.client.orchestrator.create_client_graph", return_value=fake_graph), \
         patch("agents.client.orchestrator.extract_response", return_value={"message": "g"}):
        res = co.process_client_message("cid", "привет", "web", "text", {}, {})
    assert res == {"message": "g"}
    assert coverage.snapshot().get("client:graph_flag_off") == 1


def test_client_fallback_records_graph_fallback():
    from agents.client import orchestrator as co
    from utils.llm import LLMUnavailableError
    coverage.reset()
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {}
    with patch("agents.client.agent_orchestrator.should_use", return_value=True), \
         patch("agents.client.agent_orchestrator.process", side_effect=LLMUnavailableError("x")), \
         patch("agents.client.orchestrator.create_client_graph", return_value=fake_graph), \
         patch("agents.client.orchestrator.extract_response", return_value={"message": "g"}):
        co.process_client_message("cid", "привет", "web", "text", {}, {})
    assert coverage.snapshot().get("client:graph_fallback") == 1


# ── Развилка нутрициолога (router.route_to_nutritionist) ─────────────────────
def test_nutritionist_orchestrator_success_records():
    from agents import router
    coverage.reset()
    with patch("agents.nutritionist.agent_adapter.should_use", return_value=True), \
         patch("agents.nutritionist.agent_adapter.process", return_value={"message": "ok"}):
        res = router.route_to_nutritionist("nid", "привет", "web", "text", {})
    assert res["role"] == "nutritionist"
    assert coverage.snapshot().get("nutritionist:orchestrator") == 1


def test_nutritionist_flag_off_records_and_uses_graph():
    from agents import router
    coverage.reset()
    with patch("agents.nutritionist.agent_adapter.should_use", return_value=False), \
         patch("agents.nutritionist.orchestrator.process_nutritionist_message",
               return_value={"message": "g"}) as g:
        router.route_to_nutritionist("nid", "привет", "web", "text", {})
    g.assert_called_once()
    assert coverage.snapshot().get("nutritionist:graph_flag_off") == 1


def test_nutritionist_fallback_records():
    from agents import router
    coverage.reset()
    with patch("agents.nutritionist.agent_adapter.should_use", return_value=True), \
         patch("agents.nutritionist.agent_adapter.process", side_effect=RuntimeError("boom")), \
         patch("agents.nutritionist.orchestrator.process_nutritionist_message",
               return_value={"message": "g"}):
        router.route_to_nutritionist("nid", "привет", "web", "text", {})
    assert coverage.snapshot().get("nutritionist:graph_fallback") == 1
