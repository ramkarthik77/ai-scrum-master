"""Web app: sign in with GitHub (OAuth) or a token, pick any repo + milestone, run audits.

Environment:
  GITHUB_OAUTH_CLIENT_ID / GITHUB_OAUTH_CLIENT_SECRET  enable "Sign in with GitHub"
  PUBLIC_URL               external base URL (for the OAuth callback); default: derived from the request
  ALLOW_TOKEN_LOGIN        "true" (default) shows the personal-access-token form
  SESSION_TTL_HOURS        default 8
  ANTHROPIC_API_KEY / OPENAI_API_KEY  for the LLM review (otherwise use rules-only)

Sessions live in server memory (tokens never go into cookies). Run a single
worker, or swap ``SessionStore`` for Redis when scaling out.
"""

from __future__ import annotations

import html
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import markdown as md_lib
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import auth
from ..config import DEFAULT_MODEL
from ..service import audit
from ..trackers import create

HERE = Path(__file__).parent
COOKIE = "sa_sid"
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.lower() in ("1", "true", "yes", "on")


# -- sessions ---------------------------------------------------------------
@dataclass
class Session:
    token: str
    login: str
    avatar_url: str | None
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    created: float = field(default_factory=time.time)
    last_result: dict | None = None


class SessionStore:
    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._data: dict[str, Session] = {}
        self._pending_oauth: dict[str, float] = {}
        self._lock = threading.Lock()

    def create(self, s: Session) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._data[sid] = s
        return sid

    def get(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        with self._lock:
            s = self._data.get(sid)
            if s and time.time() - s.created > self.ttl:
                del self._data[sid]
                return None
            return s

    def drop(self, sid: str | None) -> None:
        with self._lock:
            self._data.pop(sid or "", None)

    def add_state(self, state: str) -> None:
        with self._lock:
            now = time.time()
            self._pending_oauth = {k: v for k, v in self._pending_oauth.items() if now - v < 600}
            self._pending_oauth[state] = now

    def pop_state(self, state: str) -> bool:
        with self._lock:
            return self._pending_oauth.pop(state, None) is not None


# -- markdown rendering (untrusted content: no raw HTML, safe links only) ----
_SAFE_HREF = re.compile(r'href="(?!https?://|#|mailto:)[^"]*"')
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SUB = re.compile(r"</?sub>")


def render_markdown(text: str) -> str:
    text = _SUB.sub("", _HTML_COMMENT.sub("", text))
    m = md_lib.Markdown(extensions=["tables", "sane_lists"])
    m.preprocessors.deregister("html_block")
    m.inlinePatterns.deregister("html")
    out = m.convert(text)
    out = out.replace("<a href=", '<a rel="noopener noreferrer" target="_blank" href=')
    return _SAFE_HREF.sub('href="#"', out)


def report_body(report: str) -> str:
    """Drop the report's summary header; the web page shows those numbers as cards."""
    i = report.find("\n## ")
    return report[i:] if i >= 0 else report


def create_app() -> FastAPI:
    app = FastAPI(title="AI Scrum Master", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    store = SessionStore(int(float(os.getenv("SESSION_TTL_HOURS", "8")) * 3600))
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
    configured_url = (os.getenv("PUBLIC_URL") or "").rstrip("/")

    def public_url(request: Request) -> str:
        """PUBLIC_URL if set, else derived from the (proxied) request."""
        if configured_url:
            return configured_url
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        return f"{proto}://{host}"
    oauth_enabled = bool(client_id and client_secret)
    token_login = _env_bool("ALLOW_TOKEN_LOGIN", True)
    llm_key_present = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
    api_base = os.getenv("GITHUB_API_URL") or None

    def tracker(s: Session):
        return create("github", {"token": s.token, "base_url": api_base})

    def session_or_redirect(request: Request) -> Session:
        s = store.get(request.cookies.get(COOKIE))
        if not s:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        return s

    def check_csrf(s: Session, token: str) -> None:
        if not secrets.compare_digest(s.csrf, token or ""):
            raise HTTPException(400, "Form expired. Reload the page and try again.")

    def repo_id(owner: str, repo: str) -> str:
        if not (NAME_RE.match(owner) and NAME_RE.match(repo)):
            raise HTTPException(404)
        return f"{owner}/{repo}"

    def start_session(request: Request, token: str) -> RedirectResponse:
        me = create("github", {"token": token, "base_url": api_base}).whoami()
        sid = store.create(Session(token=token, login=me.login, avatar_url=me.avatar_url))
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=public_url(request).startswith("https://"),
                        max_age=store.ttl)
        return resp

    def page(request: Request, name: str, s: Session | None = None, status: int = 200, **ctx):
        return templates.TemplateResponse(request, name, {"user": s, **ctx}, status_code=status)

    # -- auth routes ------------------------------------------------------
    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str | None = None):
        return page(request, "login.html", oauth_enabled=oauth_enabled,
                    token_login=token_login, error=error)

    @app.get("/auth/github")
    def auth_github(request: Request):
        if not oauth_enabled:
            raise HTTPException(404, "GitHub OAuth is not configured.")
        url, state = auth.oauth_authorize_url(client_id, f"{public_url(request)}/auth/callback")
        store.add_state(state)
        return RedirectResponse(url, status_code=302)

    @app.get("/auth/callback")
    def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if error or not code or not store.pop_state(state):
            return RedirectResponse("/login?error=GitHub+sign-in+was+cancelled+or+expired", 303)
        try:
            token = auth.oauth_exchange_code(client_id, client_secret, code, f"{public_url(request)}/auth/callback")
            return start_session(request, token)
        except Exception:
            return RedirectResponse("/login?error=Could+not+complete+GitHub+sign-in", 303)

    @app.post("/auth/token")
    def auth_token(request: Request, token: str = Form(...)):
        if not token_login:
            raise HTTPException(404)
        try:
            return start_session(request, token.strip())
        except Exception:
            return page(request, "login.html", oauth_enabled=oauth_enabled, token_login=token_login,
                        error="GitHub rejected that token. Check it hasn't expired and has the 'repo' scope.",
                        status=401)

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        s = store.get(request.cookies.get(COOKIE))
        if s:
            check_csrf(s, csrf)
        store.drop(request.cookies.get(COOKIE))
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    # -- app routes -------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        s = session_or_redirect(request)
        try:
            projects = tracker(s).list_projects(limit=200)
        except Exception as e:
            return page(request, "error.html", s, status=502, message=f"Could not load repositories: {e}")
        return page(request, "repos.html", s, projects=projects)

    @app.get("/r/{owner}/{repo}", response_class=HTMLResponse)
    def repo_page(request: Request, owner: str, repo: str):
        s = session_or_redirect(request)
        rid = repo_id(owner, repo)
        t = tracker(s)
        try:
            sprints = t.list_sprints(rid, "open")
            active = t.default_sprint(rid)
        except Exception as e:
            return page(request, "error.html", s, status=404, message=f"Could not open {rid}: {e}")
        return page(request, "repo.html", s, repo=rid, sprints=sprints, active=active,
                    llm_available=llm_key_present, model=os.getenv("SCRUM_AGENT_MODEL", DEFAULT_MODEL))

    @app.post("/r/{owner}/{repo}/audit", response_class=HTMLResponse)
    def run_audit(
        request: Request, owner: str, repo: str,
        csrf: str = Form(""), sprint: str = Form(""), use_llm: str = Form(""),
        apply: str = Form(""), post_report: str = Form(""),
    ):
        s = session_or_redirect(request)
        check_csrf(s, csrf)
        rid = repo_id(owner, repo)
        do_apply = apply == "on"
        try:
            r = audit(tracker(s), rid, sprint=sprint or None, apply=do_apply,
                      overrides={"llm_enabled": use_llm == "on" and llm_key_present,
                                 "post_report": post_report == "on"})
        except Exception as e:
            return page(request, "error.html", s, status=400, message=str(e), back=f"/r/{rid}")
        return page(request, "result.html", s, repo=rid, r=r,
                    report_html=render_markdown(report_body(r.report)),
                    form={"sprint": r.sprint.id, "use_llm": use_llm, "post_report": post_report})

    @app.exception_handler(HTTPException)
    def http_error(request: Request, exc: HTTPException):
        if exc.status_code in (302, 303) and exc.headers:
            return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
        s = store.get(request.cookies.get(COOKIE))
        return page(request, "error.html", s, status=exc.status_code,
                    message=html.unescape(str(exc.detail)) if exc.detail else "Not found")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
