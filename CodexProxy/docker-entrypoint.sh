#!/usr/bin/env bash
set -euo pipefail

# 1. First-run (or forced) import: copy tokens from the read-only-mounted
#    Codex CLI auth.json into codex-proxy's own credential store. This is
#    a no-op once codex-proxy already has credentials.json, so it's safe
#    to run on every container start/restart.
python3 /usr/local/bin/import_auth.py

# 2. Hand off to codex-proxy itself. It binds 0.0.0.0 by default, which
#    is what we want inside a container (Docker's port mapping handles
#    exposing it externally); the OAuth callback listener on 127.0.0.1:1455
#    is only used by `codex-proxy login`, which this image doesn't run.
exec codex-proxy serve --host "${CODEX_PROXY_HOST:-0.0.0.0}" --port "${CODEX_PROXY_PORT:-8787}"
