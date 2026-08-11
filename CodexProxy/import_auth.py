#!/usr/bin/env python3
"""Import ChatGPT OAuth tokens from a mounted Codex CLI auth.json into
codex-proxy's own credential store.

Why this exists
----------------
codex-proxy normally gets tokens by running ``codex-proxy login``, which
opens a browser and listens for the OAuth redirect on
``127.0.0.1:1455`` inside the *same* process. That flow is awkward to run
inside a container (no browser, and the callback port is only reachable
from inside the container). codex-proxy also has no built-in support for
reading the Codex CLI's own ``~/.codex/auth.json``.

This script bridges the two: it reads a read-only-mounted
``~/.codex/auth.json`` (the file the official Codex CLI already
maintains and refreshes on the host) and converts it into the shape
codex-proxy expects at ``~/.codex-proxy/credentials.json``. From then on
codex-proxy refreshes the access token itself using the refresh token —
no further logins or file syncing are needed.

Codex CLI's auth.json (relevant subset)::

    {
      "OPENAI_API_KEY": null,
      "tokens": {
        "id_token": "<jwt>",
        "access_token": "<jwt>",
        "refresh_token": "<...>",
        "account_id": "..."
      },
      "last_refresh": "2026-01-01T00:00:00Z"
    }

codex-proxy's credentials.json::

    {
      "access_token": "...",
      "refresh_token": "...",
      "account_id": "...",
      "email": "...",
      "user_id": "...",
      "name": "...",
      "expires_at": 1234567890.0
    }

Behavior
--------
* Idempotent: if codex-proxy already has a ``credentials.json``, it is
  left untouched (codex-proxy owns token refresh from that point on).
  Set ``IMPORT_FORCE=1`` to force a re-import (e.g. after rotating the
  mounted auth.json on the host, such as re-running ``codex login``).
* If no auth.json is found and no credentials.json exists yet, the
  script logs a warning and exits 0 so the container still starts
  (useful for `codex-proxy login` to be run manually as a one-off, or
  for debugging).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="[import-auth] %(message)s",
)
log = logging.getLogger("import-auth")

try:
    from codex_proxy.accounts import upsert_account
    from codex_proxy.auth import (
        _decode_jwt_payload,
        _extract_optional_claim,
        extract_account_id,
        save_credentials,
    )
    from codex_proxy.config import CREDENTIALS_FILE
except ImportError as exc:  # pragma: no cover - image misconfiguration
    log.error("codex_proxy is not importable (%s); check the image build", exc)
    sys.exit(1)

DEFAULT_AUTH_JSON = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
AUTH_JSON_PATH = Path(os.environ.get("CODEX_AUTH_JSON", str(DEFAULT_AUTH_JSON)))
FORCE = os.environ.get("IMPORT_FORCE", "").strip().lower() in {"1", "true", "yes"}


def _jwt_exp(token: str) -> float | None:
    """Best-effort read of the `exp` claim from a JWT access token."""
    try:
        payload = _decode_jwt_payload(token)
    except Exception:
        return None
    exp = payload.get("exp")
    return float(exp) if isinstance(exp, (int, float)) else None


def build_credentials_from_codex_auth(auth_data: dict) -> dict:
    tokens = auth_data.get("tokens") or {}
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    id_token = tokens.get("id_token") or access_token

    if not access_token or not refresh_token:
        raise ValueError(
            "auth.json has no usable 'tokens.access_token'/'tokens.refresh_token'; "
            "make sure you're logged in on the host with `codex login`"
        )

    account_id = tokens.get("account_id") or extract_account_id(access_token)
    # Prefer the real expiry embedded in the access token JWT; fall back
    # to a conservative 1h assumption if it can't be decoded.
    expires_at = _jwt_exp(access_token) or (time.time() + 3600)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "email": _extract_optional_claim(id_token, "email"),
        "user_id": _extract_optional_claim(id_token, "sub", "user_id", "chatgpt_user_id"),
        "name": _extract_optional_claim(id_token, "name", "preferred_username"),
        "expires_at": expires_at,
    }


def main() -> int:
    if CREDENTIALS_FILE.exists() and not FORCE:
        log.info("credentials already present at %s, skipping import", CREDENTIALS_FILE)
        return 0

    if not AUTH_JSON_PATH.exists():
        if CREDENTIALS_FILE.exists():
            log.info("no auth.json at %s, keeping existing credentials", AUTH_JSON_PATH)
            return 0
        log.warning(
            "no auth.json found at %s and no existing credentials.json. "
            "Mount your host's ~/.codex/auth.json read-only at that path, "
            "or exec into the container and run `codex-proxy login` manually.",
            AUTH_JSON_PATH,
        )
        return 0

    try:
        auth_data = json.loads(AUTH_JSON_PATH.read_text())
        credentials = build_credentials_from_codex_auth(auth_data)
    except Exception as exc:
        log.error("failed to import %s: %s", AUTH_JSON_PATH, exc)
        return 1

    save_credentials(credentials)
    try:
        upsert_account(credentials, activate=True)
    except Exception as exc:
        # Non-fatal: the active credentials.json is already written, so
        # `codex-proxy serve` works even if the accounts registry update
        # (used by `codex-proxy accounts` / `switch`) fails.
        log.warning("saved active credentials but failed to update accounts registry: %s", exc)

    log.info(
        "imported ChatGPT OAuth tokens for account %s from %s (expires_at=%s)",
        credentials.get("account_id"),
        AUTH_JSON_PATH,
        int(credentials.get("expires_at", 0)),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
