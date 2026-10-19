"""OAuth PKCE authentication for OpenAI Codex (via ChatGPT)."""

import base64
import errno
import hashlib
import json
import logging
import os
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

from codex_proxy.config import (
    AUTHORIZE_URL,
    CALLBACK_PORT,
    CLIENT_ID,
    CREDENTIALS_FILE,
    JWT_CLAIM_PATH,
    REDIRECT_URI,
    SCOPE,
    TOKEN_URL,
)

log = logging.getLogger(__name__)


def _get_proxy() -> str | None:
    """Get HTTP proxy from environment."""
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def _open_browser(url: str) -> None:
    """Open browser suppressing stderr noise (dbus/ALSA errors on WSL)."""
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        import webbrowser

        webbrowser.open(url)


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without signature verification."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format")
    # Add padding
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


def _extract_optional_claim(token: str | None, *claim_names: str) -> str | None:
    """Read one string claim from a JWT, ignoring invalid tokens."""
    if not token:
        return None
    try:
        payload = _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError):
        return None

    for claim_name in claim_names:
        value = payload.get(claim_name)
        if isinstance(value, str) and value:
            return value
    return None


def extract_account_id(token: str) -> str:
    """Extract chatgpt_account_id from a JWT access token."""
    payload = _decode_jwt_payload(token)
    auth_claim = payload.get(JWT_CLAIM_PATH, {})
    account_id = auth_claim.get("chatgpt_account_id")
    if not account_id:
        raise ValueError("No chatgpt_account_id found in JWT token")
    return account_id


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    auth_code: str | None = None
    error: str | None = None
    expected_state: str | None = None
    received = Event()

    def do_GET(self, /) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Validate state parameter if we sent one
        if _CallbackHandler.expected_state:
            received_state = params.get("state", [None])[0]
            if received_state != _CallbackHandler.expected_state:
                _CallbackHandler.error = "state_mismatch"
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Login failed: state mismatch</h1>")
                _CallbackHandler.received.set()
                return

        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Login successful!</h1><p>You can close this tab.</p>")
        elif "error" in params:
            _CallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error_desc = params.get("error_description", [""])[0]
            self.wfile.write(f"<h1>Login failed: {error_desc}</h1>".encode())
        else:
            # Ignore unexpected requests (e.g. favicon.ico)
            self.send_response(404)
            self.end_headers()
            return

        _CallbackHandler.received.set()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default request logging


class _CallbackHTTPServer(HTTPServer):
    """HTTP server that can immediately reuse the callback port."""

    allow_reuse_address = True


def _start_callback_server(state: str) -> HTTPServer:
    """Start the localhost callback server on the fixed OAuth port."""
    _CallbackHandler.auth_code = None
    _CallbackHandler.error = None
    _CallbackHandler.expected_state = state
    _CallbackHandler.received = Event()

    try:
        return _CallbackHTTPServer(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise RuntimeError(
                f"OAuth callback port {CALLBACK_PORT} is already in use. "
                "Close the app using it and try again."
            ) from exc
        raise


def _wait_for_callback(server: HTTPServer, timeout: float = 120.0) -> str:
    """Wait for the OAuth callback on an already-started server."""
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        if not _CallbackHandler.received.wait(timeout):
            raise TimeoutError("OAuth callback timed out")
        if _CallbackHandler.error:
            raise RuntimeError(f"OAuth error: {_CallbackHandler.error}")
        if not _CallbackHandler.auth_code:
            raise RuntimeError("No authorization code received")
        return _CallbackHandler.auth_code
    finally:
        server.shutdown()
        server.server_close()


async def _exchange_code(code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": REDIRECT_URI,
    }
    proxy = _get_proxy()
    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=data, proxy=proxy) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Token exchange failed ({resp.status}): {body}")
            return await resp.json()


async def _refresh_token(refresh_token: str) -> dict[str, Any]:
    """Use refresh_token to get a new access_token."""
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }
    proxy = _get_proxy()
    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=data, proxy=proxy) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Token refresh failed ({resp.status}): {body}")
            return await resp.json()


def _build_credentials(
    token_response: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build credentials dict from token response."""
    access_token = token_response["access_token"]
    id_token = token_response.get("id_token")
    identity_token = id_token if isinstance(id_token, str) else access_token
    account_id = extract_account_id(access_token)
    return {
        "access_token": access_token,
        "refresh_token": token_response.get("refresh_token"),
        "account_id": account_id,
        "email": _extract_optional_claim(identity_token, "email")
        or (previous or {}).get("email"),
        "user_id": _extract_optional_claim(identity_token, "sub", "user_id")
        or (previous or {}).get("user_id"),
        "name": _extract_optional_claim(identity_token, "name", "preferred_username")
        or (previous or {}).get("name"),
        "expires_at": time.time() + token_response.get("expires_in", 3600),
    }


def save_credentials(credentials: dict[str, Any], path: Path = CREDENTIALS_FILE) -> None:
    """Save credentials to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(credentials, indent=2))
    log.info("Credentials saved to %s", path)


def load_credentials(path: Path = CREDENTIALS_FILE) -> dict[str, Any] | None:
    """Load credentials from disk. Returns None if not found."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def is_expired(credentials: dict[str, Any], margin: float = 60.0) -> bool:
    """Check if the access token is expired (with a margin)."""
    return time.time() >= credentials.get("expires_at", 0) - margin


async def login() -> dict[str, Any]:
    """Run the full OAuth PKCE login flow."""
    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)
    server = _start_callback_server(state)

    params = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "audience": "https://api.openai.com/v1",
            "state": state,
        }
    )
    auth_url = f"{AUTHORIZE_URL}?{params}"

    print(f"Opening browser for login...\n  {auth_url}")
    _open_browser(auth_url)

    code = _wait_for_callback(server)
    log.info("Received authorization code")

    token_response = await _exchange_code(code, code_verifier)
    credentials = _build_credentials(token_response)
    save_credentials(credentials)

    print(f"Login successful! Account ID: {credentials['account_id']}")
    return credentials


async def ensure_credentials(path: Path = CREDENTIALS_FILE) -> dict[str, Any]:
    """Load credentials, refreshing if expired. Raises if no credentials."""
    credentials = load_credentials(path)
    if credentials is None:
        raise RuntimeError("Not logged in. Run 'codex-proxy login' first.")

    if is_expired(credentials):
        refresh = credentials.get("refresh_token")
        if not refresh:
            raise RuntimeError("Token expired and no refresh token. Run 'codex-proxy login'.")
        log.info("Token expired, refreshing...")
        token_response = await _refresh_token(refresh)
        credentials = _build_credentials(token_response, previous=credentials)
        save_credentials(credentials, path)
        log.info("Token refreshed successfully")

    return credentials
