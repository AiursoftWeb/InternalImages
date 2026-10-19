"""Tests for usage parsing helpers."""

from codex_proxy.usage import format_credits, format_window, parse_usage_payload, remaining_percent


def test_parse_usage_payload_extracts_windows_and_credits():
    payload = {
        "plan_type": "plus",
        "credits": {
            "has_credits": True,
            "unlimited": False,
            "balance": "$12.34",
        },
        "rate_limit": {
            "primary_window": {
                "used_percent": 24.5,
                "limit_window_seconds": 18000,
                "reset_at": 1710000000,
            },
            "secondary_window": {
                "used_percent": 80,
                "limit_window_seconds": 604800,
                "reset_at": 1710600000,
            },
        },
    }

    usage = parse_usage_payload(payload)

    assert usage == {
        "plan_type": "plus",
        "primary": {
            "used_percent": 24.5,
            "window_minutes": 300,
            "reset_at": 1710000000,
        },
        "secondary": {
            "used_percent": 80.0,
            "window_minutes": 10080,
            "reset_at": 1710600000,
        },
        "credits": {
            "has_credits": True,
            "unlimited": False,
            "balance": "$12.34",
        },
    }


def test_format_helpers_handle_missing_and_remaining():
    assert remaining_percent({"used_percent": 42}) == 58
    assert format_window("5h", None) == "5h: n/a"
    assert format_credits({"has_credits": True, "unlimited": True, "balance": None}) == (
        "Credits: unlimited"
    )
