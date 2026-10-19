"""Translate between OpenAI Chat Completions and ChatGPT Responses API formats."""

import json
import logging
import time
import uuid
from typing import Any

log = logging.getLogger(__name__)

# Parameters that the Codex/Responses API does not support.
# We log a warning when clients send these so failures are traceable.
_UNSUPPORTED_PARAMS = {
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "max_tokens",
    "max_completion_tokens",
    "stop",
    "response_format",
    "logprobs",
    "top_logprobs",
    "seed",
    "n",
    "stream_options",
    "user",
    "modalities",
    "audio",
    "prediction",
    "service_tier",
}

_CLAUDE_MODEL_ALIASES = {
    "claude-opus": "gpt-5.4",
    "claude-sonnet": "gpt-5.3-codex",
    "claude-haiku": "gpt-5.4-mini",
}


def chat_to_responses(request: dict[str, Any]) -> dict[str, Any]:
    """Convert a Chat Completions request to a Responses API request body.

    Input: standard OpenAI /v1/chat/completions request
    Output: ChatGPT /backend-api/responses request body
    """
    # Warn about unsupported parameters so clients can trace silent drops.
    dropped = _UNSUPPORTED_PARAMS & request.keys()
    if dropped:
        log.warning("Dropping unsupported parameters: %s", ", ".join(sorted(dropped)))

    messages = request.get("messages", [])
    system_parts: list[str] = []
    input_items: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            # Collect all system messages; they are concatenated later.
            text = _extract_text(content)
            if text:
                system_parts.append(text)

        elif role == "user":
            input_items.append(
                {
                    "role": "user",
                    "content": _to_input_content(content),
                }
            )

        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            # Preserve text content even when tool_calls coexist.
            text = _extract_text(content)
            if text:
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": text}],
                    }
                )
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    call_id = _normalize_tool_call_id(tc.get("id", ""))
                    input_items.append(
                        {
                            "type": "function_call",
                            "id": call_id,
                            "call_id": call_id,
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", ""),
                        }
                    )

        elif role == "tool":
            # Tool result → function_call_output
            call_id = _normalize_tool_call_id(msg.get("tool_call_id", ""))
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": _extract_text(content),
                }
            )

    # Strip provider prefix (e.g. "vllm/gpt-5.1" → "gpt-5.1")
    model = _normalize_model_name(request.get("model"), default="gpt-5.1")

    instructions = "\n\n".join(system_parts) if system_parts else "You are a helpful assistant."

    body: dict[str, Any] = {
        "model": model,
        "stream": True,
        "store": False,
        "instructions": instructions,
        "input": input_items,
        "include": ["reasoning.encrypted_content"],
    }

    reasoning_effort = request.get("reasoning_effort")
    if isinstance(reasoning_effort, str) and reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}

    verbosity = request.get("verbosity")
    if isinstance(verbosity, str) and verbosity:
        body["text"] = {"verbosity": verbosity}

    if request.get("tools"):
        body["tools"] = _convert_tools(request["tools"])
        # Only set tool_choice / parallel_tool_calls when tools are present
        body["tool_choice"] = request.get("tool_choice", "auto")
        body["parallel_tool_calls"] = request.get("parallel_tool_calls", True)

    return body


def _extract_text(content: Any) -> str:
    """Extract plain text from content (string or content parts array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"text", "output_text"}:
                parts.append(part.get("text", ""))
        return "\n".join(parts)
    return str(content) if content else ""


def _to_input_content(content: Any) -> list[dict[str, Any]]:
    """Convert message content to Responses API input content format."""
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if isinstance(content, list):
        result = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") in {"text", "output_text"}:
                    result.append({"type": "input_text", "text": part.get("text", "")})
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url")
                    if isinstance(image_url, dict):
                        url = image_url.get("url", "")
                        detail = image_url.get("detail")
                    else:
                        url = image_url or ""
                        detail = None

                    input_image: dict[str, Any] = {"type": "input_image", "image_url": url}
                    if detail:
                        input_image["detail"] = detail
                    result.append(input_image)
                elif part.get("type") == "image":
                    input_image = _anthropic_image_to_input_image(part)
                    if input_image is not None:
                        result.append(input_image)
        return result
    return [{"type": "input_text", "text": str(content)}]


def anthropic_messages_to_responses(request: dict[str, Any]) -> dict[str, Any]:
    """Convert Anthropic Messages payloads into ChatGPT Responses payloads."""
    system = request.get("system")
    messages = request.get("messages", [])
    model = _normalize_model_name(request.get("model"), default="gpt-5.4")
    input_items: list[dict[str, Any]] = []

    def flush_user_content(content: list[dict[str, Any]]) -> None:
        if content:
            input_items.append({"role": "user", "content": list(content)})
            content.clear()

    def flush_assistant_content(content: list[dict[str, Any]]) -> None:
        if content:
            input_items.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": list(content),
                }
            )
            content.clear()

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role", "")
        content = msg.get("content", [])

        if role == "user":
            text_or_media: list[dict[str, Any]] = []
            for part in _as_content_blocks(content):
                part_type = part.get("type")
                if part_type == "tool_result":
                    flush_user_content(text_or_media)
                    call_id = _normalize_tool_call_id(part.get("tool_use_id", ""))
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": _extract_tool_result_output(part.get("content")),
                        }
                    )
                    continue

                normalized_part = _anthropic_part_to_input_content(part)
                if normalized_part is not None:
                    text_or_media.append(normalized_part)

            flush_user_content(text_or_media)

        elif role == "assistant":
            assistant_text: list[dict[str, Any]] = []
            for part in _as_content_blocks(content):
                part_type = part.get("type")
                if part_type == "tool_use":
                    flush_assistant_content(assistant_text)
                    call_id = _normalize_tool_call_id(part.get("id", ""))
                    input_items.append(
                        {
                            "type": "function_call",
                            "id": call_id,
                            "call_id": call_id,
                            "name": part.get("name", ""),
                            "arguments": json.dumps(part.get("input", {}), ensure_ascii=False),
                        }
                    )
                    continue
                if part_type == "thinking":
                    text = part.get("thinking", "")
                    if text:
                        assistant_text.append({"type": "output_text", "text": text})
                    continue

                normalized_part = _anthropic_part_to_assistant_content(part)
                if normalized_part is not None:
                    assistant_text.append(normalized_part)

            flush_assistant_content(assistant_text)

    body: dict[str, Any] = {
        "model": model,
        "stream": bool(request.get("stream", True)),
        "store": False,
        "instructions": _extract_anthropic_system_text(system) or "You are a helpful assistant.",
        "input": input_items,
        "include": ["reasoning.encrypted_content"],
    }

    tools = request.get("tools")
    if isinstance(tools, list) and tools:
        body["tools"] = _convert_anthropic_tools(tools)
        body["tool_choice"] = _convert_anthropic_tool_choice(request.get("tool_choice"))
        body["parallel_tool_calls"] = False

    thinking = _convert_anthropic_thinking(request.get("thinking"))
    if thinking:
        body["reasoning"] = thinking

    return body


def _normalize_tool_call_id(call_id: str) -> str:
    """Ensure tool call ID starts with 'fc_' and is <= 64 chars."""
    if not call_id.startswith("fc_"):
        call_id = f"fc_{call_id}"
    return call_id[:64]


def _tool_call_id_to_anthropic(call_id: str) -> str:
    """Convert an upstream function call ID into an Anthropic-style tool_use ID."""
    normalized = _normalize_tool_call_id(call_id)
    suffix = normalized[3:] if normalized.startswith("fc_") else normalized
    suffix = suffix.replace("-", "").replace("_", "")
    return f"toolu_{suffix[:40] or uuid.uuid4().hex[:12]}"


def _normalize_model_name(model: Any, default: str) -> str:
    if not isinstance(model, str) or not model:
        return default
    if "/" in model:
        model = model.split("/", 1)[1]
    lowered = model.lower()
    for prefix, target in _CLAUDE_MODEL_ALIASES.items():
        if lowered.startswith(prefix):
            return target
    return model


def _normalize_tool_strict(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _as_content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        return [part for part in content if isinstance(part, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _extract_anthropic_system_text(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "\n\n".join(parts)
    return ""


def _anthropic_part_to_input_content(part: dict[str, Any]) -> dict[str, Any] | None:
    part_type = part.get("type")
    if part_type == "text":
        return {"type": "input_text", "text": part.get("text", "")}
    if part_type == "image":
        return _anthropic_image_to_input_image(part)
    return None


def _anthropic_part_to_assistant_content(part: dict[str, Any]) -> dict[str, Any] | None:
    if part.get("type") == "text":
        return {"type": "output_text", "text": part.get("text", "")}
    return None


def _anthropic_image_to_input_image(part: dict[str, Any]) -> dict[str, Any] | None:
    source = part.get("source")
    if not isinstance(source, dict):
        return None

    if source.get("type") == "base64":
        media_type = source.get("media_type", "image/png")
        data = source.get("data", "")
        return {
            "type": "input_image",
            "image_url": f"data:{media_type};base64,{data}",
        }

    if source.get("type") == "url":
        url = source.get("url", "")
        if isinstance(url, str) and url:
            return {"type": "input_image", "image_url": url}

    return None


def _extract_tool_result_output(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return json.dumps(content, ensure_ascii=False) if content is not None else ""


def _convert_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        result.append(
            {
                "type": "function",
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
                "strict": _normalize_tool_strict(tool.get("strict")),
            }
        )
    return result


def _convert_anthropic_tool_choice(tool_choice: Any) -> Any:
    if not isinstance(tool_choice, dict):
        return "auto"

    choice_type = tool_choice.get("type")
    if choice_type == "tool":
        return {"type": "function", "name": tool_choice.get("name", "")}
    if choice_type == "any":
        return "required"
    if choice_type == "none":
        return "none"
    return "auto"


def _convert_anthropic_thinking(thinking: Any) -> dict[str, str] | None:
    if not thinking:
        return None

    if isinstance(thinking, dict):
        thinking_type = thinking.get("type")
        if thinking_type == "adaptive":
            return {"effort": "high"}
        if thinking_type == "enabled":
            budget = thinking.get("budget_tokens")
            if not isinstance(budget, int):
                budget = thinking.get("budgetTokens")
            if isinstance(budget, int):
                if budget >= 16000:
                    return {"effort": "high"}
                if budget <= 2048:
                    return {"effort": "low"}
            return {"effort": "medium"}
        if thinking_type == "disabled":
            return None

    return {"effort": "medium"}


def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Chat Completions tools to Responses API format."""
    result = []
    for tool in tools:
        if tool.get("type") == "function":
            fn = tool.get("function", {})
            result.append(
                {
                    "type": "function",
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                    "strict": fn.get("strict", False),
                }
            )
    return result


# --- Response SSE translation ---


def make_chunk(
    chunk_id: str,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an OpenAI Chat Completions streaming chunk."""
    chunk: dict[str, Any] = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        chunk["usage"] = usage
    return chunk


def format_sse(data: str) -> str:
    """Format a string as an SSE data line."""
    return f"data: {data}\n\n"


class ResponseStreamTranslator:
    """Stateful translator that converts Responses API SSE events
    into OpenAI Chat Completions SSE chunks."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        self.sent_role = False
        self.tool_call_index = -1
        # Track function_call item IDs to assign sequential indices
        self._fc_items: dict[str, int] = {}
        # Track arguments accumulated per function_call item so we can top up
        # from the authoritative response.output_item.done event when the
        # arguments arrive inline or the deltas are missing.
        self._fc_args: dict[str, str] = {}

    def translate_event(self, event_type: str, event_data: dict[str, Any]) -> list[str]:
        """Translate a single Responses API event into SSE lines.

        Returns a list of SSE-formatted strings (may be empty).
        """
        handler = _EVENT_HANDLERS.get(event_type)
        if handler:
            return handler(self, event_data)
        return []

    def _on_output_item_added(self, data: dict[str, Any]) -> list[str]:
        item = data.get("item", {})
        item_type = item.get("type", "")

        if item_type == "message":
            if not self.sent_role:
                self.sent_role = True
                chunk = make_chunk(self.chunk_id, self.model, {"role": "assistant", "content": ""})
                return [format_sse(json.dumps(chunk))]

        elif item_type == "function_call":
            self.tool_call_index += 1
            idx = self.tool_call_index
            item_id = item.get("id", "")
            self._fc_items[item_id] = idx
            # Some backends deliver the complete arguments inline in the item
            # instead of streaming them via response.function_call_arguments.delta.
            # Preserve them so they aren't silently dropped.
            arguments = item.get("arguments", "")
            if not isinstance(arguments, str):
                arguments = ""
            self._fc_args[item_id] = arguments
            call_id = _normalize_tool_call_id(item.get("call_id", item_id))
            delta = {
                "tool_calls": [
                    {
                        "index": idx,
                        "id": call_id,
                        "type": "function",
                        "function": {"name": item.get("name", ""), "arguments": arguments},
                    }
                ]
            }
            chunk = make_chunk(self.chunk_id, self.model, delta)
            return [format_sse(json.dumps(chunk))]

        return []

    def _on_text_delta(self, data: dict[str, Any]) -> list[str]:
        delta_text = data.get("delta", "")
        if not delta_text:
            return []
        if not self.sent_role:
            self.sent_role = True
        chunk = make_chunk(self.chunk_id, self.model, {"content": delta_text})
        return [format_sse(json.dumps(chunk))]

    def _on_function_args_delta(self, data: dict[str, Any]) -> list[str]:
        delta_text = data.get("delta", "")
        if not delta_text:
            return []
        item_id = data.get("item_id", "")
        if item_id in self._fc_items:
            self._fc_args[item_id] = self._fc_args.get(item_id, "") + delta_text
        idx = self._fc_items.get(item_id, self.tool_call_index)
        delta = {
            "tool_calls": [
                {
                    "index": idx,
                    "function": {"arguments": delta_text},
                }
            ]
        }
        chunk = make_chunk(self.chunk_id, self.model, delta)
        return [format_sse(json.dumps(chunk))]

    def _on_output_item_done(self, data: dict[str, Any]) -> list[str]:
        """Top up a function_call's arguments from its complete item.

        The Responses API also emits a final ``response.output_item.done`` with
        the full ``arguments``. When arguments were delivered inline or the
        delta stream was truncated/missing, emit only the tail we haven't
        already streamed so downstream clients still see complete arguments.
        """
        item = data.get("item", {})
        if item.get("type") != "function_call":
            return []
        item_id = item.get("id", "")
        idx = self._fc_items.get(item_id)
        if idx is None:
            return []
        complete = item.get("arguments", "")
        if not isinstance(complete, str):
            complete = ""
        accumulated = self._fc_args.get(item_id, "")
        if not complete or not complete.startswith(accumulated):
            return []
        tail = complete[len(accumulated):]
        if not tail:
            return []
        self._fc_args[item_id] = complete
        delta = {
            "tool_calls": [
                {
                    "index": idx,
                    "function": {"arguments": tail},
                }
            ]
        }
        chunk = make_chunk(self.chunk_id, self.model, delta)
        return [format_sse(json.dumps(chunk))]

    def _on_completed(self, data: dict[str, Any]) -> list[str]:
        response = data.get("response", {})
        usage_data = response.get("usage", {})

        # Map stop reason
        status = response.get("status", "completed")
        finish_reason = "stop"
        if status == "incomplete":
            finish_reason = "length"
        if self.tool_call_index >= 0:
            finish_reason = "tool_calls"

        usage = None
        if usage_data:
            input_details = usage_data.get("input_tokens_details", {})
            usage = {
                "prompt_tokens": usage_data.get("input_tokens", 0),
                "completion_tokens": usage_data.get("output_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
                "prompt_tokens_details": {
                    "cached_tokens": input_details.get("cached_tokens", 0),
                },
            }

        chunk = make_chunk(self.chunk_id, self.model, {}, finish_reason, usage)
        lines = [format_sse(json.dumps(chunk))]
        lines.append(format_sse("[DONE]"))
        return lines

    def _on_error(self, data: dict[str, Any]) -> list[str]:
        chunk = make_chunk(self.chunk_id, self.model, {}, "stop")
        chunk["error"] = data
        return [format_sse(json.dumps(chunk)), format_sse("[DONE]")]


_EVENT_HANDLERS: dict[str, Any] = {
    "response.output_item.added": ResponseStreamTranslator._on_output_item_added,
    "response.output_text.delta": ResponseStreamTranslator._on_text_delta,
    "response.content_part.delta": ResponseStreamTranslator._on_text_delta,
    "response.function_call_arguments.delta": ResponseStreamTranslator._on_function_args_delta,
    "response.output_item.done": ResponseStreamTranslator._on_output_item_done,
    "response.completed": ResponseStreamTranslator._on_completed,
    "error": ResponseStreamTranslator._on_error,
    "response.failed": ResponseStreamTranslator._on_error,
}


def _format_anthropic_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class AnthropicStreamTranslator:
    """Translate Responses SSE events into Anthropic Messages SSE events."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.message_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.started = False
        self.closed = False
        self.current_block_index: int | None = None
        self.current_block_type: str | None = None
        self.current_item_id: str | None = None
        self.current_stop_reason = "end_turn"
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.content: list[dict[str, Any]] = []
        self._tool_call_by_item_id: dict[str, str] = {}
        self._tool_input_buffers: dict[str, str] = {}

    def translate_event(self, event_type: str, event_data: dict[str, Any]) -> list[str]:
        handler = _ANTHROPIC_EVENT_HANDLERS.get(event_type)
        if handler:
            return handler(self, event_data)
        return []

    def build_response(self) -> dict[str, Any]:
        return {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "model": self.model,
            "content": self.content or [{"type": "text", "text": ""}],
            "stop_reason": self.current_stop_reason,
            "stop_sequence": None,
            "usage": dict(self.usage),
        }

    def _ensure_started(self) -> list[str]:
        if self.started:
            return []
        self.started = True
        return [
            _format_anthropic_sse(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": self.message_id,
                        "type": "message",
                        "role": "assistant",
                        "model": self.model,
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
            )
        ]

    def _close_current_block(self) -> list[str]:
        if self.current_block_index is None:
            return []
        index = self.current_block_index
        self.current_block_index = None
        self.current_block_type = None
        self.current_item_id = None
        return [
            _format_anthropic_sse(
                "content_block_stop",
                {"type": "content_block_stop", "index": index},
            )
        ]

    def _start_text_block(self) -> list[str]:
        if self.current_block_type == "text":
            return []
        lines = self._ensure_started()
        lines.extend(self._close_current_block())
        self.current_block_index = len(self.content)
        self.current_block_type = "text"
        self.current_item_id = None
        self.content.append({"type": "text", "text": ""})
        lines.append(
            _format_anthropic_sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": self.current_block_index,
                    "content_block": {"type": "text", "text": ""},
                },
            )
        )
        return lines

    def _start_tool_block(self, item: dict[str, Any]) -> list[str]:
        lines = self._ensure_started()
        lines.extend(self._close_current_block())
        item_id = item.get("id", "")
        tool_id = _tool_call_id_to_anthropic(item.get("call_id", item_id))
        self._tool_call_by_item_id[item_id] = tool_id
        # Preserve inline arguments if the backend sent them atomically instead
        # of streaming them via response.function_call_arguments.delta.
        arguments = item.get("arguments", "")
        if not isinstance(arguments, str):
            arguments = ""
        self._tool_input_buffers[item_id] = arguments
        tool_input: dict[str, Any] = {}
        if arguments:
            try:
                tool_input = json.loads(arguments)
            except json.JSONDecodeError:
                tool_input = {}
        self.current_stop_reason = "tool_use"
        self.current_block_index = len(self.content)
        self.current_block_type = "tool_use"
        self.current_item_id = item_id
        self.content.append(
            {
                "type": "tool_use",
                "id": tool_id,
                "name": item.get("name", ""),
                "input": tool_input,
            }
        )
        lines.append(
            _format_anthropic_sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": self.current_block_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": item.get("name", ""),
                        "input": {},
                    },
                },
            )
        )
        if arguments:
            lines.append(
                _format_anthropic_sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": self.current_block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": arguments,
                        },
                    },
                )
            )
        return lines

    def _on_output_item_added(self, data: dict[str, Any]) -> list[str]:
        item = data.get("item", {})
        item_type = item.get("type")
        if item_type == "message":
            return self._ensure_started()
        if item_type == "function_call":
            return self._start_tool_block(item)
        return []

    def _on_text_delta(self, data: dict[str, Any]) -> list[str]:
        delta_text = data.get("delta", "")
        if not delta_text:
            return []
        lines = self._start_text_block()
        assert self.current_block_index is not None
        self.content[self.current_block_index]["text"] += delta_text
        lines.append(
            _format_anthropic_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": self.current_block_index,
                    "delta": {"type": "text_delta", "text": delta_text},
                },
            )
        )
        return lines

    def _on_function_args_delta(self, data: dict[str, Any]) -> list[str]:
        item_id = data.get("item_id", "")
        delta_text = data.get("delta", "")
        if not item_id or not delta_text:
            return []
        index = self.current_block_index
        if item_id != self.current_item_id:
            index = next(
                (
                    idx
                    for idx, block in enumerate(self.content)
                    if block.get("type") == "tool_use"
                    and block.get("id") == self._tool_call_by_item_id.get(item_id)
                ),
                None,
            )
        if index is None:
            return []
        self._tool_input_buffers[item_id] = self._tool_input_buffers.get(item_id, "") + delta_text
        try:
            self.content[index]["input"] = json.loads(self._tool_input_buffers[item_id])
        except json.JSONDecodeError:
            pass
        return [
            _format_anthropic_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": delta_text},
                },
            )
        ]

    def _on_output_item_done(self, data: dict[str, Any]) -> list[str]:
        """Fill a tool_use block's ``input`` from its complete item.

        The Responses API emits a final ``response.output_item.done`` carrying
        the full ``arguments``. Use it to repair the tool input when arguments
        arrived inline or the delta stream was truncated/missing, and emit any
        tail as an ``input_json_delta`` for streaming clients.
        """
        item = data.get("item", {})
        if item.get("type") != "function_call":
            return []
        item_id = item.get("id", "")
        index = next(
            (
                idx
                for idx, block in enumerate(self.content)
                if block.get("type") == "tool_use"
                and block.get("id") == self._tool_call_by_item_id.get(item_id)
            ),
            None,
        )
        if index is None:
            return []
        complete = item.get("arguments", "")
        if not isinstance(complete, str):
            complete = ""
        if complete:
            try:
                self.content[index]["input"] = json.loads(complete)
            except json.JSONDecodeError:
                pass
        accumulated = self._tool_input_buffers.get(item_id, "")
        if not complete or not complete.startswith(accumulated):
            return []
        tail = complete[len(accumulated):]
        if not tail:
            return []
        self._tool_input_buffers[item_id] = complete
        return [
            _format_anthropic_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": tail},
                },
            )
        ]

    def _on_completed(self, data: dict[str, Any]) -> list[str]:
        response = data.get("response", {})
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        incomplete = (
            response.get("incomplete_details")
            if isinstance(response.get("incomplete_details"), dict)
            else {}
        )
        reason = incomplete.get("reason")
        if reason in {"max_tokens", "max_output_tokens"} or response.get("status") == "incomplete":
            self.current_stop_reason = "max_tokens"
        elif reason == "model_context_window_exceeded":
            self.current_stop_reason = "model_context_window_exceeded"

        self.usage = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }
        lines = self._ensure_started()
        lines.extend(self._close_current_block())
        lines.append(
            _format_anthropic_sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": self.current_stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": dict(self.usage),
                },
            )
        )
        lines.append(_format_anthropic_sse("message_stop", {"type": "message_stop"}))
        self.closed = True
        return lines

    def _on_error(self, data: dict[str, Any]) -> list[str]:
        payload = data.get("error", data)
        return [
            _format_anthropic_sse(
                "error",
                {
                    "type": "error",
                    "error": (
                        payload
                        if isinstance(payload, dict)
                        else {"message": str(payload)}
                    ),
                },
            )
        ]


_ANTHROPIC_EVENT_HANDLERS: dict[str, Any] = {
    "response.output_item.added": AnthropicStreamTranslator._on_output_item_added,
    "response.output_text.delta": AnthropicStreamTranslator._on_text_delta,
    "response.content_part.delta": AnthropicStreamTranslator._on_text_delta,
    "response.function_call_arguments.delta": AnthropicStreamTranslator._on_function_args_delta,
    "response.output_item.done": AnthropicStreamTranslator._on_output_item_done,
    "response.completed": AnthropicStreamTranslator._on_completed,
    "error": AnthropicStreamTranslator._on_error,
    "response.failed": AnthropicStreamTranslator._on_error,
}
