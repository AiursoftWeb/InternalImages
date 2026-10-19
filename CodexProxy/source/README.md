# codex-proxy

Local proxy that exposes ChatGPT Codex models as an OpenAI-compatible API, using your ChatGPT Plus/Pro subscription quota.

It also exposes a minimal Anthropic Messages API shim so Claude Code can use the same local proxy and still spend your ChatGPT Codex quota.

```
Client (curl, CLINE, aider, ...) ──POST /v1/chat/completions──▶ codex-proxy ──▶ chatgpt.com/backend-api/codex/responses
              ◀── OpenAI SSE ──────────────────────────────────────────────────◀── Responses API SSE

Claude Code ──POST /v1/messages──▶ codex-proxy ──▶ chatgpt.com/backend-api/codex/responses
            ◀── Anthropic SSE ────────────────────────────────────────────────◀── Responses API SSE
```

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Login (opens browser for ChatGPT OAuth)
codex-proxy login

# Start proxy
codex-proxy serve                # default: 0.0.0.0:8787
codex-proxy serve -p 9000        # custom port

# List saved accounts with usage
codex-proxy accounts

# Switch active account by account id and show its usage
codex-proxy switch <account-id>

# Remove one saved account by account id
codex-proxy accounts --remove <account-id>
```

## Authentication

### Downstream (clients → proxy)

When the `CODEX_PROXY_API_KEY` environment variable is set, all requests (except `/health`) must include a valid API key:

```
Authorization: Bearer <key>
# or
X-API-Key: <key>
```

If `CODEX_PROXY_API_KEY` is not set, the proxy runs without authentication (suitable for localhost-only use).

The systemd unit sets this to `codex-proxy` by default.

### Upstream (proxy → ChatGPT)

Upstream authentication is handled automatically via ChatGPT OAuth tokens stored in `~/.codex-proxy/credentials.json`. When you save multiple logins, snapshots are also kept under `~/.codex-proxy/accounts/`, and `codex-proxy switch <label|email|account_id>` updates the active `credentials.json`.

Run `codex-proxy login` to add the current account, `codex-proxy accounts` to list all saved accounts with usage and account ids, `codex-proxy switch <account-id>` to change the active account, and `codex-proxy accounts --remove <account-id>` to delete one saved account.

## Network Access

The proxy listens on `0.0.0.0:8787` by default, making it accessible from:

| Source | Address | Notes |
|--------|---------|-------|
| Localhost | `http://localhost:8787` | HaL subagents, local tools |
| Tailscale | `http://100.x.x.x:8787` | Remote machines on the same tailnet |

> **Security**: API key authentication + Tailscale ACLs + host firewall. The proxy does not need to be exposed to the public internet.

## Proxy Support

If you're in a region that requires a proxy to access OpenAI services, set `HTTPS_PROXY` before running commands:

```bash
export HTTPS_PROXY=http://127.0.0.1:7890

codex-proxy login    # proxy used for token exchange
codex-proxy serve    # proxy used for upstream API calls
```

## Usage

Once the proxy is running, point any OpenAI-compatible client at it:

```bash
curl http://localhost:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer codex-proxy" \
  -d '{"model":"gpt-5.1","messages":[{"role":"user","content":"Hello!"}],"stream":true}'
```

### Available Models

- `gpt-5.1`
- `gpt-5.1-codex-max`
- `gpt-5.1-codex-mini`
- `gpt-5.2`
- `gpt-5.2-codex`
- `gpt-5.3-codex`
- `gpt-5.3-codex-spark`
- `gpt-5.4`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completions (streaming and non-streaming) |
| POST | `/v1/responses` | Responses API (streaming/non-streaming) |
| POST | `/v1/messages` | Anthropic Messages API shim for Claude Code |
| POST | `/v1/messages/count_tokens` | Approximate Anthropic input token counting |
| GET | `/v1/models` | List available models |
| GET | `/health` | Health check (no auth required) |

## Integration Guide

codex-proxy exposes a standard OpenAI-compatible API at `http://localhost:8787/v1`. Any tool that supports a custom OpenAI base URL can use it directly.

### LiteLLM (used by HaL and many other tools)

```python
import litellm

response = litellm.completion(
    model="openai/gpt-5.1",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:8787",
    api_key="codex-proxy",
    stream=True,
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

If LiteLLM routes Codex-family calls to the Responses API, this proxy also supports:

```python
response = litellm.responses(
    model="openai/gpt-5.1-codex",
    input="Hello!",
    api_base="http://localhost:8787",
    api_key="codex-proxy",
    stream=True,
)
```

`/v1/responses` includes LiteLLM compatibility normalization for common payload variants such as `max_output_tokens`, chat-style `tools`/`tool_choice`, and OpenAI-style `input` message items.

### Any OpenAI-compatible CLI Agent

Most CLI agents (e.g., aider, bub, goose) support custom base URLs. For remote access via Tailscale:

```bash
export OPENAI_API_BASE=http://<tailscale-ip>:8787/v1
export OPENAI_API_KEY=codex-proxy
export OPENAI_MODEL=gpt-5.1
```

Adjust the environment variable names to match your tool's conventions.

### Claude Code

Point Claude Code at the local proxy:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8787
export ANTHROPIC_API_KEY=codex-proxy

claude
```

The Anthropic-compatible layer maps Claude-style `/v1/messages` requests onto the same ChatGPT Codex backend used by the OpenAI-compatible endpoints. Claude model names are translated onto available Codex models automatically.

Current model mapping is intentionally simple:

- `claude-opus*` → `gpt-5.4`
- `claude-sonnet*` → `gpt-5.3-codex`
- `claude-haiku*` → `gpt-5.4-mini`

Thinking requests are forwarded as Codex reasoning effort where possible. Streaming text and tool events are supported, but Anthropic-style visible thinking blocks are not yet re-emitted as separate Claude thinking events.

### General Pattern

| Setting | Value |
|---------|-------|
| Base URL | `http://localhost:8787/v1` (or `http://<tailscale-ip>:8787/v1`) |
| API Key | Value of `CODEX_PROXY_API_KEY` (default: `codex-proxy`) |
| Model | `gpt-5.1` (or any model from the list above) |

## How It Works

1. **OAuth PKCE** — `codex-proxy login` runs a standard OAuth 2.0 + PKCE flow against `auth.openai.com`, storing tokens in `~/.codex-proxy/credentials.json`
2. **Token auto-refresh** — expired tokens are automatically refreshed using the stored refresh token
3. **TLS fingerprint** — uses `curl_cffi` with Chrome impersonation to bypass Cloudflare bot detection
4. **Request translation** — OpenAI Chat Completions format is converted to ChatGPT Responses API format
5. **Response translation** — Responses API SSE events are translated back to OpenAI Chat Completions SSE chunks (including tool calls and usage)
6. **API key middleware** — optional downstream authentication via `CODEX_PROXY_API_KEY` environment variable

## Disclaimer

This project uses the unofficial ChatGPT backend API (`chatgpt.com/backend-api`). It is not endorsed by OpenAI and may break at any time. Use at your own risk.
