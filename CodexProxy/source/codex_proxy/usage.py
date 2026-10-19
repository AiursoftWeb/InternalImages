"""Fetch and format ChatGPT Codex usage information."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from codex_proxy.config import USAGE_ENDPOINT


class UsageLookupError(RuntimeError):
    """Raised when usage data could not be fetched."""


def _get_proxy() -> str | None:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def parse_usage_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize the ChatGPT usage response to a small stable shape."""
    if not isinstance(payload, dict):
        return None

    rate_limit = payload.get("rate_limit")
    primary = None
    secondary = None
    if isinstance(rate_limit, dict):
        primary = _parse_window(rate_limit.get("primary_window"))
        secondary = _parse_window(rate_limit.get("secondary_window"))

    credits = _parse_credits(payload.get("credits"))
    plan_type = payload.get("plan_type")
    if not any((primary, secondary, credits, isinstance(plan_type, str))):
        return None

    return {
        "plan_type": plan_type if isinstance(plan_type, str) else None,
        "primary": primary,
        "secondary": secondary,
        "credits": credits,
    }


def _parse_window(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    used_percent = raw.get("used_percent")
    if not isinstance(used_percent, (int, float)):
        return None

    window_seconds = raw.get("limit_window_seconds")
    reset_at = raw.get("reset_at")
    return {
        "used_percent": float(used_percent),
        "window_minutes": int(window_seconds // 60) if isinstance(window_seconds, int) else None,
        "reset_at": reset_at if isinstance(reset_at, int) else None,
    }


def _parse_credits(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "has_credits": bool(raw.get("has_credits")),
        "unlimited": bool(raw.get("unlimited")),
        "balance": raw.get("balance") if isinstance(raw.get("balance"), str) else None,
    }


async def fetch_usage(credentials: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch usage for one account from the ChatGPT backend."""
    access_token = credentials.get("access_token")
    account_id = credentials.get("account_id")
    if not access_token or not account_id:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "ChatGPT-Account-Id": account_id,
        "User-Agent": "codex-proxy",
        "Accept-Encoding": "identity",
    }

    proxy = _get_proxy()
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(USAGE_ENDPOINT, headers=headers, proxy=proxy) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise UsageLookupError(f"usage lookup failed ({resp.status}): {body[:200]}")
                data = await resp.json(content_type=None)
                return parse_usage_payload(data)
    except UsageLookupError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise UsageLookupError(str(exc)) from exc


def remaining_percent(window: dict[str, Any] | None) -> int | None:
    """Return the remaining percentage for one rate-limit window."""
    if not window:
        return None
    remaining = 100 - float(window.get("used_percent", 0))
    if remaining <= 0:
        return 0
    if remaining >= 100:
        return 100
    return int(remaining)


def format_window(name: str, window: dict[str, Any] | None) -> str:
    """Format one usage window into CLI-friendly text."""
    if not window:
        return f"{name}: n/a"

    remaining = remaining_percent(window)
    reset_at = window.get("reset_at")
    if isinstance(reset_at, int):
        reset_str = datetime.fromtimestamp(reset_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:
        reset_str = "unknown"
    return f"{name}: {remaining}% left, resets {reset_str}"


def format_credits(credits: dict[str, Any] | None) -> str:
    """Format credits info into CLI-friendly text."""
    if not credits:
        return "Credits: n/a"
    if credits.get("unlimited"):
        return "Credits: unlimited"
    balance = credits.get("balance")
    if balance:
        return f"Credits: {balance}"
    if credits.get("has_credits"):
        return "Credits: available"
    return "Credits: none"
