"""Общее ядро run_agent: сборка сообщений, обрезка истории, маппинг результата."""

from unittest.mock import patch

from agents.core.agent_engine import run_agent, AgentResult


def _capture():
    """Фейковый call_llm, который запоминает kwargs и возвращает готовый ответ."""
    box = {}

    def fake(**kw):
        box.update(kw)
        return {"content": "  ответ  ", "model": "claude-sonnet-4-6",
                "usage": {"total_tokens": 7},
                "tool_calls": [{"name": "log_water", "input": {}, "is_error": False}]}

    return box, fake


def test_run_agent_assembles_messages_and_maps_result():
    box, fake = _capture()
    with patch("agents.core.agent_engine.call_llm", side_effect=fake):
        res = run_agent(
            system_prompt="СИСТЕМА",
            history=[{"role": "user", "content": "привет"},
                     {"role": "assistant", "content": "здравствуй"}],
            user_message="как дела",
            tools=[{"name": "log_water"}],
            tool_handlers={"log_water": lambda i: "ok"},
            task_type="orchestrator",
        )

    msgs = box["messages"]
    assert msgs[0] == {"role": "system", "content": "СИСТЕМА"}
    assert msgs[1] == {"role": "user", "content": "привет"}
    assert msgs[2] == {"role": "assistant", "content": "здравствуй"}
    assert msgs[-1] == {"role": "user", "content": "как дела"}
    assert box["task_type"] == "orchestrator"
    assert box["tools"] == [{"name": "log_water"}]

    assert isinstance(res, AgentResult)
    assert res.content == "ответ"  # обрезан по краям
    assert res.model == "claude-sonnet-4-6"
    assert res.usage == {"total_tokens": 7}
    assert res.tool_calls == [{"name": "log_water", "input": {}, "is_error": False}]


def test_run_agent_trims_history_to_limit():
    box, fake = _capture()
    history = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    with patch("agents.core.agent_engine.call_llm", side_effect=fake):
        run_agent(system_prompt="s", history=history, user_message="now",
                  tools=[], tool_handlers={}, task_type="orchestrator", history_limit=3)

    msgs = box["messages"]
    # system + 3 из истории + текущее
    assert [m["content"] for m in msgs] == ["s", "m17", "m18", "m19", "now"]


def test_run_agent_empty_user_message_placeholder():
    box, fake = _capture()
    with patch("agents.core.agent_engine.call_llm", side_effect=fake):
        run_agent(system_prompt="s", history=None, user_message=None,
                  tools=[], tool_handlers={}, task_type="orchestrator")
    assert box["messages"][-1] == {"role": "user", "content": "—"}


def test_run_agent_skips_empty_history_entries():
    box, fake = _capture()
    with patch("agents.core.agent_engine.call_llm", side_effect=fake):
        run_agent(system_prompt="s",
                  history=[{"role": "user", "content": ""}, {"role": "assistant", "content": "есть"}],
                  user_message="x", tools=[], tool_handlers={}, task_type="orchestrator")
    contents = [m["content"] for m in box["messages"]]
    assert "" not in contents
    assert "есть" in contents
