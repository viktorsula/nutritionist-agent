"""
Фаза 0 (LLM-оркестратор) — клиентские инструменты в Claude: цикл
tool_use → tool_result. Проверяем выполнение обработчиков, устойчивость к ошибкам,
накопление usage, предохранитель итераций, обратную совместимость и то, что наши
параметры (tool_handlers/max_tool_iterations) НЕ утекают в Anthropic .create().
"""

import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from utils.llm import _call_claude, call_llm

CFG = {"model": "claude-sonnet-4-6", "temperature": 0.3, "max_tokens": 1000}


# ── Хелперы: лёгкие двойники блоков/ответов Anthropic ────────────────────────
def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(name, inp, id_):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id_)


def _resp(stop, content, in_tok, out_tok):
    usage = SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok, server_tool_use=None)
    return SimpleNamespace(stop_reason=stop, content=content, usage=usage)


def _claude_client(responses):
    client = MagicMock()
    client.messages.create.side_effect = responses
    return client


# ── Тесты ────────────────────────────────────────────────────────────────────
def test_client_tool_loop_executes_and_returns_text():
    calls = []

    def log_meal(inp):
        calls.append(inp)
        return "ok:saved"

    responses = [
        _resp("tool_use", [_tool_use("log_meal", {"kcal": 500}, "tu_1")], 10, 5),
        _resp("end_turn", [_text("Записал обед.")], 8, 4),
    ]
    client = _claude_client(responses)
    with patch("utils.llm.Anthropic", return_value=client), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        out = _call_claude(
            [{"role": "user", "content": "фото обеда"}],
            CFG,
            tools=[{"name": "log_meal"}],
            tool_handlers={"log_meal": log_meal},
        )

    # обработчик вызван с распарсенным input
    assert calls == [{"kcal": 500}]
    # финальный текст — из второго ответа
    assert out["content"] == "Записал обед."
    assert out["finish_reason"] == "end_turn"
    # трейс инструментов
    assert out["tool_calls"] == [{"name": "log_meal", "input": {"kcal": 500}, "is_error": False}]
    # usage накоплен по обеим итерациям
    assert out["usage"]["input_tokens"] == 18
    assert out["usage"]["output_tokens"] == 9
    assert out["usage"]["total_tokens"] == 27

    # наши параметры НЕ утекли в Anthropic .create(); tools — прошёл
    first_kw = client.messages.create.call_args_list[0].kwargs
    assert "tool_handlers" not in first_kw
    assert "max_tool_iterations" not in first_kw
    assert first_kw["tools"] == [{"name": "log_meal"}]

    # второй вызов получил tool_result с корректным id и содержимым
    second_msgs = client.messages.create.call_args_list[1].kwargs["messages"]
    tr = second_msgs[-1]
    assert tr["role"] == "user"
    assert tr["content"][0]["type"] == "tool_result"
    assert tr["content"][0]["tool_use_id"] == "tu_1"
    assert tr["content"][0]["content"] == "ok:saved"
    assert "is_error" not in tr["content"][0]


def test_non_string_tool_result_is_json_encoded():
    def load_ctx(inp):
        return {"weight": 72.5, "goal": "снижение"}

    responses = [
        _resp("tool_use", [_tool_use("load_context", {"scope": "profile"}, "tu_1")], 3, 2),
        _resp("end_turn", [_text("ок")], 1, 1),
    ]
    client = _claude_client(responses)
    with patch("utils.llm.Anthropic", return_value=client), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        _call_claude([{"role": "user", "content": "мой вес?"}], CFG,
                     tool_handlers={"load_context": load_ctx})

    tr = client.messages.create.call_args_list[1].kwargs["messages"][-1]["content"][0]
    assert '"weight": 72.5' in tr["content"]
    assert "снижение" in tr["content"]  # ensure_ascii=False → кириллица читаема


def test_tool_handler_error_reported_and_recovers():
    def boom(inp):
        raise ValueError("db down")

    responses = [
        _resp("tool_use", [_tool_use("log_meal", {}, "tu_1")], 10, 5),
        _resp("end_turn", [_text("Не смог записать, попробуйте позже.")], 5, 3),
    ]
    client = _claude_client(responses)
    with patch("utils.llm.Anthropic", return_value=client), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        out = _call_claude([{"role": "user", "content": "запиши обед"}], CFG,
                           tool_handlers={"log_meal": boom})

    assert out["content"].startswith("Не смог")
    assert out["tool_calls"][0]["is_error"] is True
    tr = client.messages.create.call_args_list[1].kwargs["messages"][-1]["content"][0]
    assert tr["is_error"] is True
    assert "db down" in tr["content"]


def test_unknown_tool_reported_without_crash():
    responses = [
        _resp("tool_use", [_tool_use("nope", {}, "tu_1")], 1, 1),
        _resp("end_turn", [_text("ок")], 1, 1),
    ]
    client = _claude_client(responses)
    with patch("utils.llm.Anthropic", return_value=client), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        out = _call_claude([{"role": "user", "content": "x"}], CFG,
                           tool_handlers={"log_meal": lambda i: "x"})

    assert out["tool_calls"][0] == {"name": "nope", "input": {}, "is_error": True}
    tr = client.messages.create.call_args_list[1].kwargs["messages"][-1]["content"][0]
    assert tr["is_error"] is True
    assert "не зарегистрирован" in tr["content"]


def test_tool_loop_respects_max_iterations():
    # модель бесконечно просит инструмент → цикл обязан остановиться на пределе
    responses = [_resp("tool_use", [_tool_use("log_meal", {}, "tu")], 1, 1) for _ in range(10)]
    client = _claude_client(responses)
    with patch("utils.llm.Anthropic", return_value=client), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        _call_claude([{"role": "user", "content": "x"}], CFG,
                     tool_handlers={"log_meal": lambda i: "ok"},
                     max_tool_iterations=3)

    assert client.messages.create.call_count == 3


def test_no_tools_backward_compatible():
    client = _claude_client([_resp("end_turn", [_text("привет")], 3, 2)])
    with patch("utils.llm.Anthropic", return_value=client), \
         patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
        out = _call_claude([{"role": "user", "content": "hi"}], CFG)

    assert out["content"] == "привет"
    assert out["usage"]["total_tokens"] == 5
    assert "tool_calls" not in out  # без инструментов ключа нет


def test_call_llm_strips_tool_params_for_non_claude():
    captured = {}

    def fake_groq(messages, cand, stream=False, **kwargs):
        captured.update(kwargs)
        return {"content": "x", "model": cand["model"], "provider": "groq", "usage": {}}

    with patch("utils.llm._call_groq", side_effect=fake_groq):
        call_llm(
            provider="groq", model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t"}], tool_handlers={"t": lambda i: "x"},
            max_tool_iterations=5,
        )

    assert "tool_handlers" not in captured
    assert "tools" not in captured
    assert "max_tool_iterations" not in captured
