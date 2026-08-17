"""Runtime patch layer for upstream codex-proxy.

This module is auto-imported by Python when present on PYTHONPATH. We use it
from the container wrapper image so we can extend upstream behavior without
forking or editing the upstream codex-proxy source tree.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import weakref
from pathlib import Path
from typing import Any

log = logging.getLogger("codex-proxy.sitecustomize")

try:
    import codex_proxy.config as _config
except Exception as exc:  # pragma: no cover - best effort bootstrap hook
    log.warning("sitecustomize loaded but codex_proxy.config import failed: %s", exc)
else:
    _OFFICIAL_MODELS = [
        {"id": "gpt-5.6-sol", "object": "model", "owned_by": "openai"},
        {"id": "gpt-5.6-terra", "object": "model", "owned_by": "openai"},
        {"id": "gpt-5.6-luna", "object": "model", "owned_by": "openai"},
        {"id": "gpt-5.5", "object": "model", "owned_by": "openai"},
        {"id": "gpt-5.4", "object": "model", "owned_by": "openai"},
        {"id": "gpt-5.4-mini", "object": "model", "owned_by": "openai"},
        {"id": "gpt-5.2", "object": "model", "owned_by": "openai"},
        {"id": "codex-auto-review", "object": "model", "owned_by": "openai"},
    ]

    def _dedupe_models(*model_lists: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: dict[str, dict[str, str]] = {}
        for items in model_lists:
            for model in items:
                model_id = model.get("id")
                if not model_id:
                    continue
                merged[model_id] = model
        return list(merged.values())

    upstream_models = list(getattr(_config, "CODEX_MODELS", []))
    patched_models = _dedupe_models(_OFFICIAL_MODELS, upstream_models)
    _config.CODEX_MODELS = patched_models
    log.warning(
        "patched CODEX_MODELS with %d entries (%d official, %d upstream)",
        len(patched_models),
        len(_OFFICIAL_MODELS),
        len(upstream_models),
    )


_REFRESH_PATCH_MARKER = "_codex_proxy_serialized_refresh"

try:
    import codex_proxy.auth as _auth
except Exception as exc:  # pragma: no cover - best effort bootstrap hook
    log.warning("sitecustomize loaded but codex_proxy.auth import failed: %s", exc)
else:
    _current_ensure_credentials = _auth.ensure_credentials
    if getattr(_current_ensure_credentials, _REFRESH_PATCH_MARKER, False):
        _serialized_ensure_credentials = _current_ensure_credentials
    else:
        _upstream_ensure_credentials = _current_ensure_credentials
        _refresh_locks_by_loop: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, dict[str, asyncio.Lock]
        ] = weakref.WeakKeyDictionary()
        _refresh_locks_guard = threading.Lock()

        def _canonical_credentials_path(path: str | Path) -> Path:
            return Path(path).expanduser().resolve(strict=False)

        def _refresh_lock(path: Path) -> asyncio.Lock:
            loop = asyncio.get_running_loop()
            key = str(path)
            with _refresh_locks_guard:
                locks = _refresh_locks_by_loop.setdefault(loop, {})
                return locks.setdefault(key, asyncio.Lock())

        async def _serialized_ensure_credentials(
            path: str | Path = _auth.CREDENTIALS_FILE,
        ) -> dict[str, Any]:
            canonical_path = _canonical_credentials_path(path)
            credentials = _auth.load_credentials(canonical_path)
            if credentials is not None and not _auth.is_expired(credentials):
                return credentials

            async with _refresh_lock(canonical_path):
                # The upstream function reloads and rechecks credentials after
                # waiting, so queued callers reuse the token written by the
                # first refresher instead of submitting the old refresh token.
                return await _upstream_ensure_credentials(canonical_path)

        setattr(_serialized_ensure_credentials, _REFRESH_PATCH_MARKER, True)
        setattr(
            _serialized_ensure_credentials,
            "_codex_proxy_upstream_ensure_credentials",
            _upstream_ensure_credentials,
        )
        _auth.ensure_credentials = _serialized_ensure_credentials
        log.warning("serialized token refreshes by credential path")

    # server.py imports ensure_credentials by value. Normal startup imports it
    # after this patch, but repair an existing binding for reload/test cases.
    _server = sys.modules.get("codex_proxy.server")
    if _server is not None:
        _server.ensure_credentials = _serialized_ensure_credentials
