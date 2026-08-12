"""Runtime patch layer for upstream codex-proxy.

This module is auto-imported by Python when present on PYTHONPATH. We use it
from the container wrapper image so we can extend upstream behavior without
forking or editing the upstream codex-proxy source tree.
"""

from __future__ import annotations

import logging

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
