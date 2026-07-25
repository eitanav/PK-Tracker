"""Sign in with Google, then exchange that for a Firebase identity.

Uses the OAuth 2.0 flow for installed apps: spin up a loopback HTTP server on
127.0.0.1, send the user to Google in their browser, catch the redirect, and
trade the authorization code for a Google ID token (PKCE throughout). That token
is then exchanged with Firebase for an ID token whose ``uid`` is the *same* one
the Android app gets for the same Google account -- which is what makes the two
dose logs converge.

Only the standard library: no SDK, no extra dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .config import SyncConfig

AUTH_PATH = Path.home() / ".pk_tracker" / "auth.json"

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_IDP_ENDPOINT = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp"
_REFRESH_ENDPOINT = "https://securetoken.googleapis.com/v1/token"
_SCOPES = "openid email profile"

# Refresh a little early rather than racing the expiry on a slow request.
_EXPIRY_MARGIN_S = 120
_BROWSER_TIMEOUT_S = 300


class AuthError(RuntimeError):
    """Sign-in could not be completed."""


@dataclass
class Credentials:
    """A signed-in Firebase identity, cached on disk between runs."""

    uid: str
    email: str
    id_token: str
    refresh_token: str
    expires_at: float = 0.0

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - _EXPIRY_MARGIN_S


# ----- small HTTP helpers ----------------------------------------------------
def _post(url: str, data: dict, *, form: bool = False) -> dict:
    if form:
        body = urllib.parse.urlencode(data).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        body = json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise AuthError(f"{url.rsplit('/', 1)[-1]} failed ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise AuthError(f"network error contacting Google: {e.reason}") from e


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# ----- loopback redirect catcher ---------------------------------------------
class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802 - name mandated by BaseHTTPRequestHandler
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        type(self).result = {k: v[0] for k, v in params.items()}
        ok = "code" in type(self).result
        message = (
            "Signed in. You can close this tab and go back to PK Tracker."
            if ok else "Sign-in failed. You can close this tab and try again."
        )
        page = (
            "<!doctype html><meta charset='utf-8'>"
            "<title>PK Tracker</title>"
            "<body style='font-family:system-ui;background:#0e1116;color:#e6edf3;"
            "display:flex;align-items:center;justify-content:center;height:100vh'>"
            f"<p>{message}</p></body>"
        )
        body = page.encode()
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass          # keep the console clean


def _await_code(server: HTTPServer, timeout: float) -> dict:
    """Serve until the browser hits the redirect, or give up."""
    _CallbackHandler.result = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while time.time() < deadline and not _CallbackHandler.result:
        time.sleep(0.2)
    server.shutdown()
    return _CallbackHandler.result


# ----- credential storage ----------------------------------------------------
def load_credentials(path: Path | None = None) -> Credentials | None:
    p = path or AUTH_PATH
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return Credentials(**raw)
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def save_credentials(creds: Credentials, path: Path | None = None) -> None:
    p = path or AUTH_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(creds), indent=2), encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)      # tokens are bearer secrets
    except OSError:
        pass


def sign_out(path: Path | None = None) -> None:
    p = path or AUTH_PATH
    try:
        p.unlink()
    except FileNotFoundError:
        pass


# ----- the flow --------------------------------------------------------------
def sign_in(cfg: SyncConfig, *, open_browser: bool = True) -> Credentials:
    """Run the full interactive sign-in. Blocks until the browser round-trips."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(16)

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
    params = {
        "client_id": cfg.oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    if open_browser:
        webbrowser.open(url)

    try:
        result = _await_code(server, _BROWSER_TIMEOUT_S)
    finally:
        server.server_close()

    if not result:
        raise AuthError("timed out waiting for the browser sign-in")
    if "error" in result:
        raise AuthError(f"Google returned an error: {result['error']}")
    if result.get("state") != state:
        raise AuthError("state mismatch on the OAuth redirect -- aborted")

    exchange = {
        "code": result["code"],
        "client_id": cfg.oauth_client_id,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    if cfg.oauth_client_secret:
        exchange["client_secret"] = cfg.oauth_client_secret
    google_token = _post(_TOKEN_ENDPOINT, exchange, form=True).get("id_token")
    if not google_token:
        raise AuthError("Google did not return an ID token")

    return _exchange_with_firebase(cfg, google_token)


def _exchange_with_firebase(cfg: SyncConfig, google_id_token: str) -> Credentials:
    """Trade a Google ID token for a Firebase one (same uid as the phone)."""
    payload = {
        "postBody": f"id_token={google_id_token}&providerId=google.com",
        "requestUri": "http://127.0.0.1",
        "returnIdpCredential": True,
        "returnSecureToken": True,
    }
    data = _post(f"{_IDP_ENDPOINT}?key={cfg.api_key}", payload)
    creds = Credentials(
        uid=data["localId"],
        email=data.get("email", ""),
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        expires_at=time.time() + float(data.get("expiresIn", 3600)),
    )
    save_credentials(creds)
    return creds


def refresh(cfg: SyncConfig, creds: Credentials) -> Credentials:
    """Renew an expired Firebase ID token using the stored refresh token."""
    data = _post(
        f"{_REFRESH_ENDPOINT}?key={cfg.api_key}",
        {"grant_type": "refresh_token", "refresh_token": creds.refresh_token},
        form=True,
    )
    creds.id_token = data["id_token"]
    creds.refresh_token = data.get("refresh_token", creds.refresh_token)
    creds.uid = data.get("user_id", creds.uid)
    creds.expires_at = time.time() + float(data.get("expires_in", 3600))
    save_credentials(creds)
    return creds


def valid_credentials(cfg: SyncConfig) -> Credentials | None:
    """Cached credentials, refreshed if stale. ``None`` if not signed in."""
    creds = load_credentials()
    if creds is None:
        return None
    if creds.expired:
        try:
            creds = refresh(cfg, creds)
        except AuthError:
            return None       # refresh token revoked or expired: sign in again
    return creds
