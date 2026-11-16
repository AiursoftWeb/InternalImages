"""验证构建补丁及 Responses 请求、响应链路，不访问真实上游。"""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from patch_responses import apply_patch

SOURCE = Path(__file__).parent / "source/codex_proxy/server.py"


@pytest.fixture
def server(tmp_path):
    target = tmp_path / "server.py"
    target.write_bytes(SOURCE.read_bytes())
    apply_patch(target)
    spec = importlib.util.spec_from_file_location("codex_proxy._patched_server", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("call_id", ["call_x", "call_" + "a" * 32, "short", "z" * 200])
def test_removes_only_synthetic_id_without_mutating_history(server, call_id):
    history = [
        {"type": "function_call", "id": "fc_" + call_id, "call_id": call_id,
         "name": "list_directory", "arguments": '{"path":"."}', "status": "completed"},
        {"type": "function_call_output", "call_id": call_id, "output": "42"},
    ]
    original = copy.deepcopy(history)
    body, _ = server._normalize_responses_body({"input": history})
    expected = copy.deepcopy(original)
    expected[0].pop("id")
    assert body["input"] == expected
    assert history == original


@pytest.mark.parametrize("item", [
    {"type": "function_call", "id": "fc_original", "call_id": "call_x"},
    {"type": "function_call", "id": "fc_call_other", "call_id": "call_x"},
    {"type": "function_call", "call_id": "call_x"},
    {"type": "function_call", "id": "fc_", "call_id": ""},
    {"type": "function_call", "id": "fc_None", "call_id": None},
    {"type": "function_call", "id": "fc_42", "call_id": 42},
    {"type": "function_call", "id": "fc_call_x"},
    {"type": "function_call_output", "id": "fc_call_x", "call_id": "call_x", "output": "42"},
    {"type": "item_reference", "id": "fc_call_x", "call_id": "call_x"},
    {"type": "reasoning", "id": "fc_call_x", "call_id": "call_x"},
    {"role": "assistant", "id": "fc_call_x", "call_id": "call_x"},
    None,
    "unknown",
])
def test_preserves_unrelated_items(server, item):
    assert server._normalize_responses_input([item]) == [item]


@pytest.mark.parametrize("value", [None, {}, 42, []])
def test_preserves_non_message_inputs(server, value):
    assert server._normalize_responses_input(value) == value


def test_existing_message_and_tool_normalization_is_preserved(server):
    body, client_stream = server._normalize_responses_body({
        "stream": False, "max_output_tokens": 10,
        "input": [{"type": "message", "role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
        "tool_choice": {"type": "function", "function": {"name": "lookup"}},
    })
    assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}]
    assert body["tools"][0]["name"] == "lookup"
    assert body["tool_choice"] == {"type": "function", "name": "lookup"}
    assert body["stream"] is True and client_stream is False
    assert body["store"] is False
    assert body["parallel_tool_calls"] is False
    assert "max_output_tokens" not in body
    assert server._normalize_responses_input("hi") == [
        {"role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False])
async def test_four_round_history_is_normalized_before_upstream_without_output_repair(server, monkeypatch, stream):
    # 最终 output 故意为空，同时包含文字 delta：确认补丁不靠补写输出掩盖问题。
    completed = {"id": "resp_test", "object": "response", "output": []}
    events = (
        b'data: {"type":"response.output_text.delta","delta":"42"}\n\n'
        + ("data: " + json.dumps({"type": "response.completed", "response": completed}) + "\n\n").encode()
    )

    class Upstream:
        status_code = 200

        async def aiter_content(self):
            yield events[:30]
            yield events[30:]

        async def aiter_lines(self):
            for line in events.splitlines():
                yield line

    post = AsyncMock(return_value=Upstream())
    monkeypatch.setattr(server, "ensure_credentials", AsyncMock(return_value={
        "access_token": "test", "account_id": "test",
    }))
    response = SimpleNamespace(prepared=False, headers={}, writes=[])

    async def prepare(request):
        response.prepared = True

    async def write(data):
        response.writes.append(data)

    response.prepare = prepare
    response.write = write
    monkeypatch.setattr(server.web, "StreamResponse", lambda: response)
    history = []
    for turn in range(4):
        call_id = f"call_{turn}"
        history.extend([
            {"type": "function_call", "id": "fc_" + call_id, "call_id": call_id,
             "name": "lookup", "arguments": "{}"},
            {"type": "function_call_output", "call_id": call_id, "output": "42"},
        ])
        original = copy.deepcopy(history)
        request = SimpleNamespace(
            json=AsyncMock(return_value={"input": history, "stream": stream, "model": "test"}),
            app={"upstream_session": SimpleNamespace(post=post)},
        )
        result = await server.handle_responses(request)
        sent = post.call_args.kwargs["json"]
        assert sent["stream"] is True
        assert len(sent["input"]) == len(history)
        for index, item in enumerate(sent["input"]):
            expected = dict(original[index])
            if expected["type"] == "function_call":
                expected.pop("id")
            assert item == expected
        assert history == original
        if stream:
            assert result is response
            assert b"".join(response.writes) == events
            response.writes.clear()
        else:
            assert result.status == 200
            assert json.loads(result.body) == completed


def test_patch_fails_closed_when_anchor_changes(tmp_path):
    target = tmp_path / "server.py"
    for source in ["unrelated", SOURCE.read_text().replace('        new_item = dict(item)\n        if "content" in new_item:\n', "changed"), SOURCE.read_text() * 2]:
        target.write_text(source)
        with pytest.raises(RuntimeError, match="锚点"):
            apply_patch(target)
        assert target.read_text() == source


def test_patch_is_valid_python_and_rejects_reapplication(tmp_path):
    target = tmp_path / "server.py"
    target.write_bytes(SOURCE.read_bytes())
    apply_patch(target)
    patched = target.read_text()
    compile(patched, str(target), "exec")
    with pytest.raises(RuntimeError, match="锚点"):
        apply_patch(target)
    assert target.read_text() == patched
