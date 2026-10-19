"""Tests for OAuth login flow."""

import asyncio
import errno
from threading import Event
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

from codex_proxy import auth, cli


def test_start_callback_server_reports_busy_port_clearly(monkeypatch):
    def fake_http_server(server_address, handler_class):
        del server_address, handler_class
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(auth, "_CallbackHTTPServer", fake_http_server)

    with pytest.raises(RuntimeError, match="1455"):
        auth._start_callback_server("expected-state")


def test_wait_for_callback_closes_server():
    class FakeServer:
        def __init__(self):
            self.shutdown_called = False
            self.server_close_called = False

        def serve_forever(self):
            return None

        def shutdown(self):
            self.shutdown_called = True

        def server_close(self):
            self.server_close_called = True

    server = FakeServer()
    auth._CallbackHandler.received = Event()
    auth._CallbackHandler.received.set()
    auth._CallbackHandler.error = None
    auth._CallbackHandler.auth_code = "test-code"

    assert auth._wait_for_callback(server) == "test-code"
    assert server.shutdown_called is True
    assert server.server_close_called is True


def test_login_uses_fixed_redirect_uri(monkeypatch):
    fake_server = object()
    opened_urls: list[str] = []
    saved_credentials: list[dict[str, object]] = []

    monkeypatch.setattr(auth, "_generate_pkce", lambda: ("verifier", "challenge"))
    monkeypatch.setattr(auth.secrets, "token_urlsafe", lambda _: "fixed-state")
    monkeypatch.setattr(auth, "_start_callback_server", lambda state: fake_server)
    monkeypatch.setattr(auth, "_wait_for_callback", lambda server: "test-code")
    monkeypatch.setattr(auth, "_open_browser", opened_urls.append)
    monkeypatch.setattr(auth, "save_credentials", saved_credentials.append)

    async def fake_exchange_code(code: str, code_verifier: str) -> dict[str, object]:
        assert code == "test-code"
        assert code_verifier == "verifier"
        return {
            "access_token": _jwt_with_account_id("acct-123"),
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        }

    monkeypatch.setattr(auth, "_exchange_code", fake_exchange_code)

    credentials = asyncio.run(auth.login())

    redirect_uri = parse_qs(urlparse(opened_urls[0]).query)["redirect_uri"][0]
    assert redirect_uri == auth.REDIRECT_URI
    assert credentials["account_id"] == "acct-123"
    assert saved_credentials and saved_credentials[0]["account_id"] == "acct-123"


def test_cli_login_shows_clean_error_without_traceback(monkeypatch):
    async def fake_login():
        raise RuntimeError("OAuth callback port 1455 is already in use.")

    monkeypatch.setattr("codex_proxy.auth.login", fake_login)

    result = CliRunner().invoke(cli.main, ["login"])

    assert result.exit_code == 1
    assert "OAuth callback port 1455 is already in use." in result.output
    assert "Traceback" not in result.output


def _jwt_with_account_id(account_id: str) -> str:
    payload = (
        '{"https://api.openai.com/auth":{"chatgpt_account_id":"'
        + account_id
        + '"}}'
    ).encode("utf-8")
    encoded = auth.base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    return f"header.{encoded}.signature"
