"""Credential handling for the CLI and the GitHub OAuth flows used by the web app.

Precedence for the CLI: ``GITHUB_TOKEN`` / ``GH_TOKEN`` env vars, then the
credentials saved by ``scrum-agent login`` (``~/.config/scrum-agent/credentials.json``,
file mode 0600).
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

GITHUB_WEB = os.getenv("GITHUB_WEB_URL", "https://github.com")
OAUTH_SCOPES = "repo read:user"


def config_dir() -> Path:
    base = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "scrum-agent"


def credentials_path() -> Path:
    return config_dir() / "credentials.json"


def load_credentials() -> dict:
    p = credentials_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def save_credentials(provider: str, data: dict) -> Path:
    creds = load_credentials()
    creds[provider] = data
    p = credentials_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(p, 0o600)
    return p


def clear_credentials(provider: str) -> bool:
    creds = load_credentials()
    if provider not in creds:
        return False
    del creds[provider]
    if creds:
        fd = os.open(credentials_path(), os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(creds, f, indent=2)
    else:
        credentials_path().unlink()
    return True


def resolve_github(token: str | None = None) -> dict:
    """Return {'token':..., 'base_url':...} from flag, env, or saved login."""
    if token:
        return {"token": token, "base_url": os.getenv("GITHUB_API_URL") or None}
    env_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if env_token:
        return {"token": env_token, "base_url": os.getenv("GITHUB_API_URL") or None}
    saved = load_credentials().get("github")
    if saved and saved.get("token"):
        return saved
    raise PermissionError("Not logged in. Run `scrum-agent login` or set GITHUB_TOKEN.")


# -- OAuth device flow (CLI "login with browser") ---------------------------
def device_flow_start(client_id: str) -> dict:
    r = httpx.post(f"{GITHUB_WEB}/login/device/code",
                   data={"client_id": client_id, "scope": OAUTH_SCOPES},
                   headers={"Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data.get("error_description") or data["error"])
    return data


def device_flow_poll(client_id: str, device_code: str, interval: int, expires_in: int) -> str:
    deadline = time.monotonic() + expires_in
    while time.monotonic() < deadline:
        time.sleep(interval)
        r = httpx.post(f"{GITHUB_WEB}/login/oauth/access_token",
                       data={"client_id": client_id, "device_code": device_code,
                             "grant_type": "urn:ietf:params:oauth:grant-type:device_code"},
                       headers={"Accept": "application/json"}, timeout=20)
        data = r.json()
        if tok := data.get("access_token"):
            return tok
        err = data.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise RuntimeError(data.get("error_description") or err or "device flow failed")
    raise TimeoutError("Login timed out. Run `scrum-agent login` again.")


# -- OAuth web flow (web app "Sign in with GitHub") -------------------------
def oauth_authorize_url(client_id: str, redirect_uri: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    q = urlencode({"client_id": client_id, "redirect_uri": redirect_uri,
                   "scope": OAUTH_SCOPES, "state": state, "allow_signup": "false"})
    return f"{GITHUB_WEB}/login/oauth/authorize?{q}", state


def oauth_exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> str:
    r = httpx.post(f"{GITHUB_WEB}/login/oauth/access_token",
                   data={"client_id": client_id, "client_secret": client_secret,
                         "code": code, "redirect_uri": redirect_uri},
                   headers={"Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(data.get("error_description") or data.get("error") or "OAuth exchange failed")
    return data["access_token"]
