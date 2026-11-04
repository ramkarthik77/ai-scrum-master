from __future__ import annotations

import re
from dataclasses import replace

import pytest
from fakes import FakeTracker, item
from fastapi.testclient import TestClient

import scrum_agent.web.app as web


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    hostile = replace(item(1, assignees=["ana"], labels=["points: 3"], idle_hours=72),
                      title="<script>alert(1)</script> [x](javascript:alert(1))")
    tracker = FakeTracker([hostile, item(2, assignees=["ben"], idle_hours=2)])

    def fake_create(name, creds):
        if creds["token"] != "good":
            raise PermissionError("bad token")
        return tracker

    monkeypatch.setattr(web, "create", fake_create)
    c = TestClient(web.create_app())
    c.tracker = tracker
    return c


def login(c):
    r = c.post("/auth/token", data={"token": "good"}, follow_redirects=False)
    assert r.status_code == 303
    return r


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert "Personal access token" in client.get("/login").text


def test_bad_token(client):
    r = client.post("/auth/token", data={"token": "nope"})
    assert r.status_code == 401 and "rejected" in r.text


def test_flow_dry_run_then_apply(client):
    login(client)
    assert "o/r" in client.get("/").text
    page = client.get("/r/o/r").text
    assert "Sprint 1" in page
    token = csrf(page)

    r = client.post("/r/o/r/audit", data={"csrf": token, "sprint": "1"})
    assert r.status_code == 200
    assert "Dry run" in r.text and "Apply 1 nudge" in r.text
    # untrusted issue title is escaped and javascript: links neutralised
    assert "<script>alert(1)" not in r.text and "javascript:" not in r.text
    assert client.tracker.comments == {}

    r = client.post("/r/o/r/audit", data={"csrf": token, "sprint": "1", "apply": "on"})
    assert "Actions applied" in r.text
    assert "1" in client.tracker.comments


def test_csrf_enforced(client):
    login(client)
    r = client.post("/r/o/r/audit", data={"csrf": "wrong", "sprint": "1"})
    assert r.status_code == 400


def test_invalid_repo_name(client):
    login(client)
    assert client.get("/r/o/bad%20name").status_code == 404


def test_logout(client):
    login(client)
    token = csrf(client.get("/").text)
    client.post("/logout", data={"csrf": token})
    assert client.get("/", follow_redirects=False).status_code == 303
