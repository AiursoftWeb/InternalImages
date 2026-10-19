"""aiohttp proxy server exposing OpenAI-compatible endpoints."""

import json
import logging
import os
import time
from typing import Any

from aiohttp import web
from curl_cffi import CurlOpt
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException

from codex_proxy.auth import ensure_credentials, extract_account_id
from codex_proxy.config import CODEX_MODELS, RESPONSES_ENDPOINT
from codex_proxy.translator import (
    AnthropicStreamTranslator,
    ResponseStreamTranslator,
    anthropic_messages_to_responses,
    chat_to_responses,
)

log = logging.getLogger(__name__)

# --- API key authentication middleware ---
_API_KEY = os.environ.get("CODEX_PROXY_API_KEY")
_PUBLIC_PATHS = {"/health"}


@web.middleware
async def api_key_middleware(request: web.Request, handler):
    """Reject requests without a valid API key (if CODEX_PROXY_API_KEY is set)."""
    if not _API_KEY or request.path in _PUBLIC_PATHS:
        return await handler(request)

    auth = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key", "")

    provided = None
    if auth.startswith("Bearer "):
        provided = auth[7:]
    elif api_key_header:
        provided = api_key_header

    if provided != _API_KEY:
        return web.json_response(
            {"error": {"message": "Invalid or missing API key", "type": "auth_error"}},
            status=401,
        )
    return await handler(request)
_UNSUPPORTED_RESPONSES_PARAMS = {
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
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
    "prompt_cache_retention",
    "safety_identifier",
}
_DEFAULT_CLIENT_MAX_SIZE_MIB = 32
_CLIENT_MAX_SIZE_ENV_VAR = "CODEX_PROXY_CLIENT_MAX_SIZE_MIB"


def _get_client_max_size_bytes() -> int:
    """Read the aiohttp request-body limit from the environment."""
    raw_value = os.environ.get(
        _CLIENT_MAX_SIZE_ENV_VAR,
        str(_DEFAULT_CLIENT_MAX_SIZE_MIB),
    )
    try:
        max_size_mib = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"{_CLIENT_MAX_SIZE_ENV_VAR} must be a positive integer, got {raw_value!r}"
        ) from exc
    if max_size_mib <= 0:
        raise RuntimeError(
            f"{_CLIENT_MAX_SIZE_ENV_VAR} must be a positive integer, got {raw_value!r}"
        )
    return max_size_mib * 1024 * 1024


_CLIENT_MAX_SIZE = _get_client_max_size_bytes()
_UPSTREAM_TIMEOUT_SECONDS = 120
_MAX_UPSTREAM_ATTEMPTS = 2
_RETRIABLE_UPSTREAM_ERROR_CODES = {18, 35, 52, 55, 56, 92}
_RETRIABLE_UPSTREAM_EVENT_MARKERS = (
    "serviceunavailable",
    "service_unavailable",
    "api_connection_error",
    "connection error",
    "temporarily unavailable",
    "please retry",
    "an error occurred while processing your request",
)


def _normalize_tool_strict(value: Any) -> bool:
    """Normalize tool strictness to a boolean value."""
    return value if isinstance(value, bool) else False


def _normalize_input_content(content: Any) -> Any:
    """Normalize message content parts for ChatGPT codex upstream."""
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if not isinstance(content, list):
        return content

    normalized: list[Any] = []
    for part in content:
        if not isinstance(part, dict):
            normalized.append(part)
            continue

        if part.get("type") == "text":
            normalized.append({"type": "input_text", "text": part.get("text", "")})
            continue

        if part.get("type") == "image_url":
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = image_url.get("url", "")
                detail = image_url.get("detail")
            else:
                url = image_url or ""
                detail = None

            input_image = {"type": "input_image", "image_url": url}
            if detail:
                input_image["detail"] = detail
            normalized.append(input_image)
            continue

        normalized.append(part)
    return normalized


def _normalize_responses_input(input_value: Any) -> Any:
    """Normalize /responses input items from OpenAI-style payloads."""
    if isinstance(input_value, str):
        return [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": input_value}],
            }
        ]
    if not isinstance(input_value, list):
        return input_value

    normalized: list[Any] = []
    converted = 0
    for item in input_value:
        if not isinstance(item, dict):
            normalized.append(item)
            continue

        if item.get("type") == "message":
            converted += 1
            new_item = dict(item)
            new_item.pop("type", None)
            if "content" in new_item:
                new_item["content"] = _normalize_input_content(new_item["content"])
            normalized.append(new_item)
            continue

        new_item = dict(item)
        if "content" in new_item:
            new_item["content"] = _normalize_input_content(new_item["content"])
        normalized.append(new_item)

    if converted:
        log.info("Normalized %d OpenAI-style input message items on /responses", converted)
    return normalized


def _normalize_responses_tools(tools: Any) -> Any:
    """Accept both Chat Completions and Responses tools schema on /responses."""
    if not isinstance(tools, list):
        return tools

    converted_count = 0
    normalized_tools: list[Any] = []
    for tool in tools:
        if not isinstance(tool, dict):
            normalized_tools.append(tool)
            continue

        fn = tool.get("function")
        if tool.get("type") == "function" and isinstance(fn, dict):
            normalized_tools.append(
                {
                    "type": "function",
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                    "strict": _normalize_tool_strict(fn.get("strict")),
                }
            )
            converted_count += 1
            continue

        if tool.get("type") == "function":
            direct = dict(tool)
            direct["strict"] = _normalize_tool_strict(direct.get("strict"))
            normalized_tools.append(direct)
            continue

        normalized_tools.append(tool)

    if converted_count:
        log.info("Normalized %d chat-style tools on /responses", converted_count)
    return normalized_tools


def _normalize_responses_tool_choice(tool_choice: Any) -> Any:
    """Normalize chat.completions-style tool_choice for /responses."""
    if not isinstance(tool_choice, dict):
        return tool_choice

    fn = tool_choice.get("function")
    if tool_choice.get("type") == "function" and isinstance(fn, dict):
        return {
            "type": "function",
            "name": fn.get("name", ""),
        }

    return tool_choice


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def handle_models(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "object": "list",
            "data": CODEX_MODELS,
        }
    )


def _estimate_anthropic_input_tokens(payload: dict[str, Any]) -> dict[str, int]:
    """Estimate Anthropic input tokens with a rough chars/4 heuristic."""
    total_chars = 0

    system = payload.get("system")
    if isinstance(system, str):
        total_chars += len(system)
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                total_chars += len(block.get("text", ""))

    messages = payload.get("messages", [])
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                total_chars += len(content)
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    total_chars += len(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    tool_content = block.get("content", "")
                    if isinstance(tool_content, str):
                        total_chars += len(tool_content)
                    else:
                        total_chars += len(json.dumps(tool_content, ensure_ascii=False))

    return {"input_tokens": max(1, total_chars // 4)}


def _build_upstream_headers(credentials: dict[str, Any], accept: str) -> dict[str, str]:
    """Build auth headers for ChatGPT backend requests."""
    access_token = credentials["access_token"]
    account_id = credentials.get("account_id") or extract_account_id(access_token)
    return {
        "Authorization": f"Bearer {access_token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "Content-Type": "application/json",
        "Accept": accept,
    }


def _make_stream_response() -> web.StreamResponse:
    """Build a standard SSE response for downstream clients."""
    response = web.StreamResponse()
    response.content_type = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    return response


async def _ensure_stream_prepared(
    response: web.StreamResponse, request: web.Request
) -> web.StreamResponse:
    """Prepare an SSE response exactly once."""
    if not response.prepared:
        await response.prepare(request)
    return response


def _build_error_payload(message: str, error_type: str, detail: str | None = None) -> dict[str, Any]:
    """Build a standard OpenAI-style error payload."""
    error: dict[str, Any] = {"message": message, "type": error_type}
    if detail:
        error["detail"] = detail
    return {"error": error}


def _build_anthropic_error_payload(
    message: str, error_type: str, detail: str | None = None
) -> dict[str, Any]:
    """Build an Anthropic-style error payload."""
    error: dict[str, Any] = {"message": message, "type": error_type}
    if detail:
        error["detail"] = detail
    return {"type": "error", "error": error}


async def _write_chat_stream_error(
    request: web.Request,
    response: web.StreamResponse,
    message: str,
    error_type: str,
    detail: str | None = None,
) -> web.StreamResponse:
    """Write a downstream chat-completions SSE error and terminate the stream."""
    payload = _build_error_payload(message, error_type, detail)
    await _ensure_stream_prepared(response, request)
    await response.write(f"data: {json.dumps(payload)}\n\n".encode())
    await response.write(b"data: [DONE]\n\n")
    return response


async def _write_responses_stream_error(
    request: web.Request,
    response: web.StreamResponse,
    message: str,
    error_type: str,
    detail: str | None = None,
) -> web.StreamResponse:
    """Write a downstream Responses-API SSE error and terminate the stream."""
    payload: dict[str, Any] = {
        "type": "error",
        "error": {
            "message": message,
            "type": error_type,
        },
    }
    if detail:
        payload["error"]["detail"] = detail
    await _ensure_stream_prepared(response, request)
    await response.write(f"data: {json.dumps(payload)}\n\n".encode())
    await response.write(b"data: [DONE]\n\n")
    return response


def _is_retriable_upstream_error(exc: Exception) -> bool:
    """Return whether an upstream curl/network error is worth one reconnect attempt."""
    code = getattr(exc, "code", None)
    if isinstance(exc, RequestException) and code in _RETRIABLE_UPSTREAM_ERROR_CODES:
        return True

    lowered = str(exc).lower()
    return "connection reset by peer" in lowered or "recv failure" in lowered


def _should_retry_upstream_error(exc: Exception, attempt: int, sent_to_client: bool) -> bool:
    """Retry only before any downstream bytes are sent."""
    return (
        not sent_to_client
        and attempt < _MAX_UPSTREAM_ATTEMPTS
        and _is_retriable_upstream_error(exc)
    )


def _is_retriable_upstream_event(event_type: str, event_data: dict[str, Any]) -> bool:
    """Return whether an upstream SSE error event looks transient."""
    if event_type not in {"error", "response.failed"}:
        return False

    lowered = json.dumps(event_data, ensure_ascii=False).lower()
    return any(marker in lowered for marker in _RETRIABLE_UPSTREAM_EVENT_MARKERS)


async def _read_upstream_text(upstream: Any) -> str:
    """Read full upstream response body as text."""
    try:
        chunks = []
        async for chunk in upstream.aiter_content():
            chunks.append(chunk.decode(errors="replace") if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)
    except Exception:
        text = getattr(upstream, "text", "")
        if isinstance(text, bytes):
            return text.decode(errors="replace")
        return str(text)


def _normalize_responses_body(raw_body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Normalize OpenAI-style /responses request for ChatGPT codex upstream."""
    body = dict(raw_body)
    client_stream = bool(body.get("stream"))

    dropped = _UNSUPPORTED_RESPONSES_PARAMS & body.keys()
    for key in dropped:
        body.pop(key, None)
    if dropped:
        log.warning("Dropping unsupported /responses parameters: %s", ", ".join(sorted(dropped)))

    # ChatGPT Codex responses endpoint requires instructions.
    # Add a sensible default for OpenAI-compatible clients that omit it.
    if not body.get("instructions"):
        body["instructions"] = "You are a helpful assistant."

    if body.get("store") is not False:
        body["store"] = False

    # OpenAI Responses API allows input as a plain string.
    # Normalize to ChatGPT Codex format that expects a list of input items.
    if "input" in body:
        body["input"] = _normalize_responses_input(body.get("input"))

    if "tools" in body:
        body["tools"] = _normalize_responses_tools(body.get("tools"))
    if "tool_choice" in body:
        body["tool_choice"] = _normalize_responses_tool_choice(body.get("tool_choice"))
    if body.get("tools") and "parallel_tool_calls" not in body:
        # LiteLLM <=1.81.x responses streaming chunks use a fixed tool index (0),
        # which can merge multiple calls in downstream aggregators.
        # Default to sequential tool calls unless the client explicitly opts in.
        body["parallel_tool_calls"] = False

    # ChatGPT Codex responses endpoint currently enforces stream=true.
    # For client stream=false, we aggregate upstream SSE into a final JSON response.
    body["stream"] = True
    return body, client_stream


def _parse_sse_data_line(line: str) -> str | None:
    """Extract payload from one SSE `data:` line."""
    stripped = line.strip()
    if not stripped.startswith("data: "):
        return None
    return stripped[6:]


def _merge_tool_call_delta(tool_calls_by_index: dict[int, dict[str, Any]], delta_calls: Any) -> None:
    """Merge streamed tool_call deltas into indexed tool call state."""
    if not isinstance(delta_calls, list):
        return

    for call in delta_calls:
        if not isinstance(call, dict):
            continue
        index = call.get("index")
        if not isinstance(index, int):
            continue

        state = tool_calls_by_index.setdefault(
            index,
            {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            },
        )

        call_id = call.get("id")
        if isinstance(call_id, str) and call_id:
            state["id"] = call_id

        call_type = call.get("type")
        if isinstance(call_type, str) and call_type:
            state["type"] = call_type

        fn_delta = call.get("function")
        if not isinstance(fn_delta, dict):
            continue

        fn_state = state["function"]
        fn_name = fn_delta.get("name")
        if isinstance(fn_name, str) and fn_name:
            fn_state["name"] = fn_name

        fn_args = fn_delta.get("arguments")
        if isinstance(fn_args, str) and fn_args:
            fn_state["arguments"] = f"{fn_state['arguments']}{fn_args}"


def _aggregate_nonstream_chat_completion(chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build one OpenAI Chat Completions JSON response from streaming chunks."""
    if not chunks:
        return None

    response_id: str | None = None
    model: str | None = None
    created: int | None = None
    usage: dict[str, Any] | None = None
    role: str | None = None
    finish_reason: str | None = None
    content_parts: list[str] = []
    tool_calls_by_index: dict[int, dict[str, Any]] = {}

    for chunk in chunks:
        if response_id is None:
            chunk_id = chunk.get("id")
            if isinstance(chunk_id, str) and chunk_id:
                response_id = chunk_id

        if model is None:
            chunk_model = chunk.get("model")
            if isinstance(chunk_model, str) and chunk_model:
                model = chunk_model

        if created is None:
            chunk_created = chunk.get("created")
            if isinstance(chunk_created, int):
                created = chunk_created

        chunk_usage = chunk.get("usage")
        if isinstance(chunk_usage, dict):
            usage = chunk_usage

        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            continue

        choice0 = choices[0]
        if not isinstance(choice0, dict):
            continue

        chunk_finish_reason = choice0.get("finish_reason")
        if isinstance(chunk_finish_reason, str):
            finish_reason = chunk_finish_reason

        delta = choice0.get("delta")
        if not isinstance(delta, dict):
            continue

        delta_role = delta.get("role")
        if isinstance(delta_role, str) and delta_role:
            role = delta_role

        delta_content = delta.get("content")
        if isinstance(delta_content, str):
            content_parts.append(delta_content)

        _merge_tool_call_delta(tool_calls_by_index, delta.get("tool_calls"))

    tool_calls: list[dict[str, Any]] = []
    for index in sorted(tool_calls_by_index):
        state = tool_calls_by_index[index]
        fn_state = state["function"]
        tool_calls.append(
            {
                "id": state["id"] or f"call_{index}",
                "type": state["type"] or "function",
                "function": {
                    "name": fn_state["name"] or "",
                    "arguments": fn_state["arguments"] or "",
                },
            }
        )

    content = "".join(content_parts)
    message: dict[str, Any] = {"role": role or "assistant"}
    if tool_calls:
        message["content"] = content or None
        message["tool_calls"] = tool_calls
        if finish_reason is None:
            finish_reason = "tool_calls"
    else:
        message["content"] = content
        if finish_reason is None:
            finish_reason = "stop"

    completion: dict[str, Any] = {
        "id": response_id or "chatcmpl-proxy",
        "object": "chat.completion",
        "created": created if created is not None else int(time.time()),
        "model": model or "",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage is not None:
        completion["usage"] = usage
    return completion


async def handle_chat_completions(request: web.Request) -> web.StreamResponse | web.Response:
    """Main proxy endpoint: translate and forward to ChatGPT backend."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    # Get credentials (auto-refresh if expired)
    try:
        credentials = await ensure_credentials()
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=401)

    # Translate request
    client_stream = bool(body.get("stream"))
    model = body.get("model", "gpt-5.1")
    responses_body = chat_to_responses(body)

    # Build headers for ChatGPT backend
    headers = _build_upstream_headers(credentials, accept="text/event-stream")

    # Forward to ChatGPT backend
    translator = ResponseStreamTranslator(model)
    response = _make_stream_response() if client_stream else None

    tools_count = len(responses_body.get("tools", []))
    log.info(
        "Upstream request: model=%s, tools=%d, tool_choice=%s, input_items=%d",
        responses_body.get("model"),
        tools_count,
        responses_body.get("tool_choice", "N/A"),
        len(responses_body.get("input", [])),
    )
    log.debug("Upstream request body: %s", json.dumps(responses_body)[:5000])

    session: AsyncSession = request.app["upstream_session"]
    for attempt in range(1, _MAX_UPSTREAM_ATTEMPTS + 1):
        sent_to_client = bool(response is not None and response.prepared)
        try:
            upstream = await session.post(
                RESPONSES_ENDPOINT,
                json=responses_body,
                headers=headers,
                stream=True,
                timeout=_UPSTREAM_TIMEOUT_SECONDS,
            )

            if upstream.status_code != 200:
                error_text = await _read_upstream_text(upstream)
                log.error("Upstream error %d: %s", upstream.status_code, error_text[:1000])
                return web.json_response(
                    _build_error_payload(
                        f"ChatGPT API error: {upstream.status_code}",
                        "upstream_error",
                        error_text[:500],
                    ),
                    status=upstream.status_code,
                )

            if client_stream and response is not None:
                retry_stream = False
                async for line_bytes in upstream.aiter_lines():
                    line = line_bytes.decode() if isinstance(line_bytes, bytes) else line_bytes
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        await _ensure_stream_prepared(response, request)
                        await response.write(b"data: [DONE]\n\n")
                        return response

                    try:
                        event_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        log.warning("Unparseable SSE data: %s", data_str[:200])
                        continue

                    event_type = event_data.get("type", "")
                    if event_type in {"error", "response.failed"}:
                        retriable_event = (
                            not sent_to_client
                            and attempt < _MAX_UPSTREAM_ATTEMPTS
                            and _is_retriable_upstream_event(event_type, event_data)
                        )
                        log_method = log.warning if retriable_event else log.error
                        log_method(
                            "Upstream streaming event %s: %s",
                            event_type,
                            json.dumps(event_data)[:1000],
                        )
                        if retriable_event:
                            retry_stream = True
                            break

                    sse_lines = translator.translate_event(event_type, event_data)
                    for sse_line in sse_lines:
                        await _ensure_stream_prepared(response, request)
                        await response.write(sse_line.encode())
                        sent_to_client = True
                        if _parse_sse_data_line(sse_line) == "[DONE]":
                            return response

                if retry_stream:
                    log.warning(
                        "Retrying upstream chat completion after transient stream event (%d/%d)",
                        attempt,
                        _MAX_UPSTREAM_ATTEMPTS,
                    )
                    continue

                await _ensure_stream_prepared(response, request)
                await response.write(b"data: [DONE]\n\n")
                return response

            translated_chunks: list[dict[str, Any]] = []
            retry_nonstream = False
            async for line_bytes in upstream.aiter_lines():
                line = line_bytes.decode() if isinstance(line_bytes, bytes) else line_bytes
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event_data = json.loads(data_str)
                except json.JSONDecodeError:
                    log.warning("Unparseable upstream SSE data: %s", data_str[:200])
                    continue

                event_type = event_data.get("type", "")
                if event_type in {"error", "response.failed"}:
                    retriable_event = (
                        not translated_chunks
                        and attempt < _MAX_UPSTREAM_ATTEMPTS
                        and _is_retriable_upstream_event(event_type, event_data)
                    )
                    log_method = log.warning if retriable_event else log.error
                    log_method(
                        "Upstream non-stream event %s: %s",
                        event_type,
                        json.dumps(event_data)[:1000],
                    )
                    if retriable_event:
                        retry_nonstream = True
                        break

                sse_lines = translator.translate_event(event_type, event_data)
                for sse_line in sse_lines:
                    translated_payload = _parse_sse_data_line(sse_line)
                    if translated_payload is None:
                        continue
                    if translated_payload == "[DONE]":
                        break

                    try:
                        translated_chunk = json.loads(translated_payload)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(translated_chunk, dict):
                        continue
                    if "error" in translated_chunk:
                        return web.json_response({"error": translated_chunk["error"]}, status=502)
                    translated_chunks.append(translated_chunk)

            if retry_nonstream:
                log.warning(
                    "Retrying upstream non-stream chat completion after transient stream event (%d/%d)",
                    attempt,
                    _MAX_UPSTREAM_ATTEMPTS,
                )
                continue

            completion = _aggregate_nonstream_chat_completion(translated_chunks)
            if completion is not None:
                return web.json_response(completion)

            return web.json_response(
                _build_error_payload("Missing translated completion data", "upstream_error"),
                status=502,
            )

        except Exception as e:
            if _should_retry_upstream_error(e, attempt, sent_to_client):
                log.warning(
                    "Retrying upstream chat completion after transient error (%d/%d): %s",
                    attempt,
                    _MAX_UPSTREAM_ATTEMPTS,
                    e,
                )
                continue

            log.error("Connection error: %s", e)
            if client_stream and response is not None and response.prepared:
                return await _write_chat_stream_error(
                    request,
                    response,
                    str(e),
                    "connection_error",
                )
            return web.json_response(
                _build_error_payload(str(e), "connection_error"),
                status=502,
            )

    return web.json_response(
        _build_error_payload("Failed to connect to upstream", "connection_error"),
        status=502,
    )


async def handle_messages(request: web.Request) -> web.StreamResponse | web.Response:
    """Expose an Anthropic-compatible /v1/messages endpoint for Claude Code."""
    try:
        raw_body = await request.json()
    except json.JSONDecodeError:
        return web.json_response(
            _build_anthropic_error_payload("Invalid JSON", "invalid_request_error"),
            status=400,
        )

    client_stream = bool(raw_body.get("stream", False))
    body = anthropic_messages_to_responses(raw_body)
    body["stream"] = True
    response_model = raw_body.get("model") if isinstance(raw_body.get("model"), str) else body["model"]

    try:
        credentials = await ensure_credentials()
    except RuntimeError as e:
        return web.json_response(
            _build_anthropic_error_payload(str(e), "authentication_error"),
            status=401,
        )

    headers = _build_upstream_headers(credentials, accept="text/event-stream")

    session: AsyncSession = request.app["upstream_session"]
    response = _make_stream_response() if client_stream else None
    for attempt in range(1, _MAX_UPSTREAM_ATTEMPTS + 1):
        sent_to_client = bool(response is not None and response.prepared)
        translator = AnthropicStreamTranslator(response_model)
        try:
            upstream = await session.post(
                RESPONSES_ENDPOINT,
                json=body,
                headers=headers,
                stream=True,
                timeout=_UPSTREAM_TIMEOUT_SECONDS,
            )

            if upstream.status_code != 200:
                error_text = await _read_upstream_text(upstream)
                log.error("Upstream /messages error %d: %s", upstream.status_code, error_text[:1000])
                return web.json_response(
                    _build_anthropic_error_payload(error_text[:1000], "upstream_error"),
                    status=upstream.status_code,
                )

            retry_stream = False
            async for line_bytes in upstream.aiter_lines():
                line = line_bytes.decode() if isinstance(line_bytes, bytes) else line_bytes
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event_data = json.loads(data_str)
                except json.JSONDecodeError:
                    log.warning("Unparseable upstream SSE data on /messages: %s", data_str[:200])
                    continue

                event_type = event_data.get("type", "")
                if event_type in {"error", "response.failed"}:
                    retriable_event = (
                        not sent_to_client
                        and attempt < _MAX_UPSTREAM_ATTEMPTS
                        and _is_retriable_upstream_event(event_type, event_data)
                    )
                    log_method = log.warning if retriable_event else log.error
                    log_method(
                        "Upstream Anthropic event %s: %s",
                        event_type,
                        json.dumps(event_data)[:1000],
                    )
                    if retriable_event:
                        retry_stream = True
                        break
                    if client_stream and response is not None:
                        for sse_line in translator.translate_event(event_type, event_data):
                            await _ensure_stream_prepared(response, request)
                            await response.write(sse_line.encode())
                        return response
                    return web.json_response({"type": "error", "error": event_data.get("error", event_data)}, status=502)

                sse_lines = translator.translate_event(event_type, event_data)
                if client_stream and response is not None:
                    for sse_line in sse_lines:
                        await _ensure_stream_prepared(response, request)
                        await response.write(sse_line.encode())
                        sent_to_client = True

            if retry_stream:
                log.warning(
                    "Retrying upstream /messages request after transient stream event (%d/%d)",
                    attempt,
                    _MAX_UPSTREAM_ATTEMPTS,
                )
                continue

            if client_stream and response is not None:
                await _ensure_stream_prepared(response, request)
                return response

            if translator.closed:
                return web.json_response(translator.build_response())

            return web.json_response(
                _build_anthropic_error_payload("Missing response.completed event", "upstream_error"),
                status=502,
            )

        except Exception as e:
            if _should_retry_upstream_error(e, attempt, sent_to_client):
                log.warning(
                    "Retrying upstream /messages request after transient error (%d/%d): %s",
                    attempt,
                    _MAX_UPSTREAM_ATTEMPTS,
                    e,
                )
                continue

            log.error("Connection error on /messages: %s", e)
            if client_stream and response is not None and response.prepared:
                error_payload = {
                    "type": "error",
                    "error": {"type": "connection_error", "message": str(e)},
                }
                await response.write(
                    f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
                )
                return response
            return web.json_response(
                _build_anthropic_error_payload(str(e), "connection_error"),
                status=502,
            )

    return web.json_response(
        _build_anthropic_error_payload("Failed to connect to upstream", "connection_error"),
        status=502,
    )


async def handle_count_tokens(request: web.Request) -> web.Response:
    """Expose Anthropic-compatible input token estimation."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    return web.json_response(_estimate_anthropic_input_tokens(body), status=200)


async def handle_responses(request: web.Request) -> web.StreamResponse | web.Response:
    """Forward OpenAI Responses API requests directly to ChatGPT backend."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    body, client_stream = _normalize_responses_body(body)

    try:
        credentials = await ensure_credentials()
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=401)

    headers = _build_upstream_headers(
        credentials,
        accept="text/event-stream",
    )

    log.info(
        "Upstream /responses request: model=%s, stream=%s, input_items=%d",
        body.get("model"),
        client_stream,
        len(body.get("input", [])) if isinstance(body.get("input"), list) else 0,
    )
    log.debug("Upstream /responses request body: %s", json.dumps(body)[:5000])

    session: AsyncSession = request.app["upstream_session"]
    response = _make_stream_response() if client_stream else None
    for attempt in range(1, _MAX_UPSTREAM_ATTEMPTS + 1):
        sent_to_client = bool(response is not None and response.prepared)
        try:
            upstream = await session.post(
                RESPONSES_ENDPOINT,
                json=body,
                headers=headers,
                stream=True,
                timeout=_UPSTREAM_TIMEOUT_SECONDS,
            )

            if upstream.status_code != 200:
                error_text = await _read_upstream_text(upstream)
                log.error("Upstream /responses error %d: %s", upstream.status_code, error_text[:1000])
                try:
                    return web.json_response(json.loads(error_text), status=upstream.status_code)
                except json.JSONDecodeError:
                    return web.Response(text=error_text, status=upstream.status_code)

            if client_stream and response is not None:
                async for chunk in upstream.aiter_content():
                    await _ensure_stream_prepared(response, request)
                    await response.write(chunk if isinstance(chunk, bytes) else chunk.encode())
                    sent_to_client = True
                await _ensure_stream_prepared(response, request)
                return response

            completed_response: dict[str, Any] | None = None
            async for line_bytes in upstream.aiter_lines():
                line = line_bytes.decode() if isinstance(line_bytes, bytes) else line_bytes
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event_data.get("type", "")
                if event_type == "response.completed":
                    response_obj = event_data.get("response")
                    if isinstance(response_obj, dict):
                        completed_response = response_obj
                elif event_type in {"error", "response.failed"}:
                    return web.json_response(event_data, status=502)

            if completed_response is not None:
                return web.json_response(completed_response, status=200)

            return web.json_response(
                _build_error_payload("Missing response.completed event", "upstream_error"),
                status=502,
            )

        except Exception as e:
            if _should_retry_upstream_error(e, attempt, sent_to_client):
                log.warning(
                    "Retrying upstream /responses request after transient error (%d/%d): %s",
                    attempt,
                    _MAX_UPSTREAM_ATTEMPTS,
                    e,
                )
                continue

            log.error("Connection error on /responses: %s", e)
            if client_stream and response is not None and response.prepared:
                return await _write_responses_stream_error(
                    request,
                    response,
                    str(e),
                    "connection_error",
                )
            return web.json_response(
                _build_error_payload(str(e), "connection_error"),
                status=502,
            )

    return web.json_response(
        _build_error_payload("Failed to connect to upstream", "connection_error"),
        status=502,
    )


async def _create_upstream_session(app: web.Application) -> None:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    app["upstream_session"] = AsyncSession(
        impersonate="chrome",
        proxies={"https": proxy} if proxy else None,
        http_version="v1",
        curl_options={CurlOpt.TCP_KEEPALIVE: 1},
    )


async def _close_upstream_session(app: web.Application) -> None:
    session: AsyncSession = app["upstream_session"]
    await session.close()


def create_app() -> web.Application:
    """Create the aiohttp application."""
    middlewares = [api_key_middleware] if _API_KEY else []
    if _API_KEY:
        log.info("API key authentication enabled")
    else:
        log.warning("No CODEX_PROXY_API_KEY set — running without authentication")
    app = web.Application(middlewares=middlewares, client_max_size=_CLIENT_MAX_SIZE)
    app.on_startup.append(_create_upstream_session)
    app.on_cleanup.append(_close_upstream_session)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/models", handle_models)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_post("/chat/completions", handle_chat_completions)
    app.router.add_post("/v1/responses", handle_responses)
    app.router.add_post("/responses", handle_responses)
    app.router.add_post("/v1/messages", handle_messages)
    app.router.add_post("/messages", handle_messages)
    app.router.add_post("/v1/messages/count_tokens", handle_count_tokens)
    app.router.add_post("/messages/count_tokens", handle_count_tokens)
    return app


def run_server(host: str, port: int) -> None:
    """Start the proxy server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = create_app()
    log.info("Starting codex-proxy on %s:%d", host, port)
    log.info(
        "Endpoints: POST /v1/chat/completions, POST /v1/responses, POST /v1/messages, GET /v1/models, GET /health"
    )
    web.run_app(app, host=host, port=port, print=None)
