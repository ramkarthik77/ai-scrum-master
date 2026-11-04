from __future__ import annotations

import json

from fakes import FakeTracker, item
from typer.testing import CliRunner

import scrum_agent.cli as cli
from scrum_agent import auth


def test_audit_json_and_step_summary(monkeypatch, tmp_path):
    t = FakeTracker([item(1, assignees=["ana"], idle_hours=72)])
    monkeypatch.setattr(cli, "create", lambda name, creds: t)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    r = CliRunner().invoke(cli.app, ["audit", "o/r", "--no-llm", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert data["flagged"] == [1] and data["dry_run"] is True
    assert "Sprint report" in summary.read_text()


def test_not_logged_in(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    r = CliRunner().invoke(cli.app, ["audit", "o/r"])
    assert r.exit_code == 2 and "Not logged in" in r.output


def test_login_with_token_saves_0600(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "create", lambda name, creds: FakeTracker([]))
    r = CliRunner().invoke(cli.app, ["login", "--with-token"], input="tok123\n")
    assert r.exit_code == 0, r.output
    p = auth.credentials_path()
    assert oct(p.stat().st_mode & 0o777) == "0o600"
    assert auth.load_credentials()["github"]["token"] == "tok123"
    assert CliRunner().invoke(cli.app, ["logout"]).exit_code == 0
    assert not p.exists()
