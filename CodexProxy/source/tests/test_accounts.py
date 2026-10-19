"""Tests for local multi-account storage."""

import json

from codex_proxy.accounts import (
    activate_account,
    find_matching_accounts,
    list_accounts,
    load_registry,
    remove_account,
    upsert_account,
)
from codex_proxy.auth import save_credentials


def _credentials(account_id: str, email: str) -> dict[str, object]:
    return {
        "access_token": f"token-{account_id}",
        "refresh_token": f"refresh-{account_id}",
        "account_id": account_id,
        "email": email,
        "expires_at": 9999999999,
    }


def test_upsert_and_switch_account(tmp_path):
    registry_path = tmp_path / "accounts" / "registry.json"
    accounts_dir = tmp_path / "accounts"
    active_path = tmp_path / "credentials.json"

    upsert_account(
        _credentials("acct-1", "one@example.com"),
        label="work",
        activate=True,
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )
    upsert_account(
        _credentials("acct-2", "two@example.com"),
        label="personal",
        activate=False,
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )

    activate_account(
        "acct-2",
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )

    registry = load_registry(registry_path)
    assert registry["active_account_id"] == "acct-2"
    assert json.loads(active_path.read_text())["account_id"] == "acct-2"


def test_list_accounts_imports_legacy_active_credentials(tmp_path):
    registry_path = tmp_path / "accounts" / "registry.json"
    accounts_dir = tmp_path / "accounts"
    active_path = tmp_path / "credentials.json"
    save_credentials(_credentials("acct-1", "legacy@example.com"), active_path)

    registry, accounts = list_accounts(
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )

    assert registry["active_account_id"] == "acct-1"
    assert len(accounts) == 1
    assert accounts[0]["label"] == "legacy@example.com"


def test_find_matching_accounts_prefers_exact_label():
    registry = {
        "active_account_id": "acct-1",
        "accounts": [
            {"account_id": "acct-1", "label": "work", "email": "one@example.com"},
            {"account_id": "acct-2", "label": "workbench", "email": "two@example.com"},
        ],
    }

    matches = find_matching_accounts(registry, "work")

    assert [item["account_id"] for item in matches] == ["acct-1", "acct-2"]


def test_remove_active_account_switches_to_next_one(tmp_path):
    registry_path = tmp_path / "accounts" / "registry.json"
    accounts_dir = tmp_path / "accounts"
    active_path = tmp_path / "credentials.json"

    upsert_account(
        _credentials("acct-1", "one@example.com"),
        label="one",
        activate=True,
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )
    upsert_account(
        _credentials("acct-2", "two@example.com"),
        label="two",
        activate=False,
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )

    removed, new_active = remove_account(
        "acct-1",
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_path,
    )

    registry = load_registry(registry_path)
    assert removed["account_id"] == "acct-1"
    assert new_active is not None
    assert new_active["account_id"] == "acct-2"
    assert registry["active_account_id"] == "acct-2"
    assert json.loads(active_path.read_text())["account_id"] == "acct-2"
