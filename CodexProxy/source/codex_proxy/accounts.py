"""Local account registry for multiple ChatGPT OAuth logins."""

from __future__ import annotations

import base64
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from codex_proxy.config import ACCOUNTS_DIR, CREDENTIALS_FILE, REGISTRY_FILE

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _default_registry() -> dict[str, Any]:
    return {"active_account_id": None, "accounts": []}


def load_registry(path: Path = REGISTRY_FILE) -> dict[str, Any]:
    """Load the account registry from disk."""
    if not path.exists():
        return _default_registry()

    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        return _default_registry()

    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        data["accounts"] = []
    if "active_account_id" not in data:
        data["active_account_id"] = None
    return data


def save_registry(registry: dict[str, Any], path: Path = REGISTRY_FILE) -> None:
    """Persist the account registry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2))


def _account_filename(account_id: str) -> str:
    if _SAFE_FILENAME_RE.fullmatch(account_id):
        return f"{account_id}.json"
    encoded = base64.urlsafe_b64encode(account_id.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.json"


def account_credentials_path(account_id: str, accounts_dir: Path = ACCOUNTS_DIR) -> Path:
    """Return the stored credentials path for one account."""
    return accounts_dir / _account_filename(account_id)


def find_account_record(
    registry: dict[str, Any], account_id: str
) -> tuple[int | None, dict[str, Any] | None]:
    """Find one account record by account_id."""
    accounts = registry.get("accounts", [])
    for index, record in enumerate(accounts):
        if record.get("account_id") == account_id:
            return index, record
    return None, None


def upsert_account(
    credentials: dict[str, Any],
    *,
    label: str | None = None,
    activate: bool = True,
    registry_path: Path = REGISTRY_FILE,
    accounts_dir: Path = ACCOUNTS_DIR,
    active_credentials_path: Path = CREDENTIALS_FILE,
) -> dict[str, Any]:
    """Store one account snapshot and update the registry."""
    account_id = credentials["account_id"]
    now = int(time.time())

    registry = load_registry(registry_path)
    index, existing = find_account_record(registry, account_id)

    resolved_label = (label or "").strip() or (existing or {}).get("label")
    if not resolved_label:
        resolved_label = credentials.get("email") or account_id

    record = {
        "account_id": account_id,
        "email": credentials.get("email"),
        "user_id": credentials.get("user_id"),
        "name": credentials.get("name"),
        "label": resolved_label,
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
        "last_used_at": now if activate else (existing or {}).get("last_used_at"),
        "last_usage": (existing or {}).get("last_usage"),
        "last_usage_at": (existing or {}).get("last_usage_at"),
    }

    accounts_dir.mkdir(parents=True, exist_ok=True)
    from codex_proxy.auth import save_credentials

    save_credentials(credentials, account_credentials_path(account_id, accounts_dir))
    if activate:
        save_credentials(credentials, active_credentials_path)
        registry["active_account_id"] = account_id

    if index is None:
        registry["accounts"].append(record)
    else:
        registry["accounts"][index] = record

    save_registry(registry, registry_path)
    return record


def ensure_active_account_registered(
    *,
    registry_path: Path = REGISTRY_FILE,
    accounts_dir: Path = ACCOUNTS_DIR,
    active_credentials_path: Path = CREDENTIALS_FILE,
) -> dict[str, Any] | None:
    """Import the current active credentials into the registry if needed."""
    from codex_proxy.auth import load_credentials

    credentials = load_credentials(active_credentials_path)
    if credentials is None:
        return None

    return upsert_account(
        credentials,
        activate=True,
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_credentials_path,
    )


def list_accounts(
    *,
    registry_path: Path = REGISTRY_FILE,
    accounts_dir: Path = ACCOUNTS_DIR,
    active_credentials_path: Path = CREDENTIALS_FILE,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return registry and accounts, importing the active one if needed."""
    ensure_active_account_registered(
        registry_path=registry_path,
        accounts_dir=accounts_dir,
        active_credentials_path=active_credentials_path,
    )
    registry = load_registry(registry_path)
    accounts = list(registry.get("accounts", []))
    accounts.sort(
        key=lambda item: (
            item.get("account_id") != registry.get("active_account_id"),
            item.get("label", ""),
        )
    )
    return registry, accounts


def _match_score(record: dict[str, Any], query: str) -> int:
    lowered = query.casefold()
    for key in ("label", "email", "account_id", "name"):
        value = record.get(key)
        if not isinstance(value, str):
            continue
        candidate = value.casefold()
        if candidate == lowered:
            return 3
        if candidate.startswith(lowered):
            return 2
        if lowered in candidate:
            return 1
    return 0


def find_matching_accounts(registry: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Find accounts matching one loose query."""
    matched = []
    for record in registry.get("accounts", []):
        score = _match_score(record, query)
        if score:
            matched.append((score, record))
    matched.sort(key=lambda item: (-item[0], item[1].get("label", "")))
    return [record for _, record in matched]


def activate_account(
    account_id: str,
    *,
    registry_path: Path = REGISTRY_FILE,
    accounts_dir: Path = ACCOUNTS_DIR,
    active_credentials_path: Path = CREDENTIALS_FILE,
) -> dict[str, Any]:
    """Make one stored account the active credentials."""
    registry = load_registry(registry_path)
    index, record = find_account_record(registry, account_id)
    if record is None or index is None:
        raise KeyError(account_id)

    src = account_credentials_path(account_id, accounts_dir)
    if not src.exists():
        raise FileNotFoundError(src)

    active_credentials_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, active_credentials_path)
    record["last_used_at"] = int(time.time())
    registry["accounts"][index] = record
    registry["active_account_id"] = account_id
    save_registry(registry, registry_path)
    return record


def update_account_usage(
    account_id: str,
    usage: dict[str, Any] | None,
    *,
    used_at: int | None = None,
    registry_path: Path = REGISTRY_FILE,
) -> None:
    """Cache the latest usage snapshot in the registry."""
    registry = load_registry(registry_path)
    index, record = find_account_record(registry, account_id)
    if record is None or index is None:
        return

    record["last_usage"] = usage
    record["last_usage_at"] = used_at or int(time.time())
    record["updated_at"] = int(time.time())
    registry["accounts"][index] = record
    save_registry(registry, registry_path)


def remove_account(
    account_id: str,
    *,
    registry_path: Path = REGISTRY_FILE,
    accounts_dir: Path = ACCOUNTS_DIR,
    active_credentials_path: Path = CREDENTIALS_FILE,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Remove one stored account and return the removed and new active records."""
    registry = load_registry(registry_path)
    index, record = find_account_record(registry, account_id)
    if record is None or index is None:
        raise KeyError(account_id)

    snapshot_path = account_credentials_path(account_id, accounts_dir)
    if snapshot_path.exists():
        snapshot_path.unlink()

    removed = dict(record)
    del registry["accounts"][index]

    new_active: dict[str, Any] | None = None
    if registry.get("active_account_id") == account_id:
        registry["active_account_id"] = None
        if registry["accounts"]:
            new_active = registry["accounts"][0]
            registry["active_account_id"] = new_active["account_id"]
            active_credentials_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(
                account_credentials_path(new_active["account_id"], accounts_dir),
                active_credentials_path,
            )
        elif active_credentials_path.exists():
            active_credentials_path.unlink()

    save_registry(registry, registry_path)
    return removed, new_active
