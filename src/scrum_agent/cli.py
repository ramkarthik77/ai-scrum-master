"""`scrum-agent` command-line interface."""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from dataclasses import asdict
from typing import Annotated

import typer

from . import auth
from .service import audit as run_service_audit
from .trackers import create

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="AI Scrum Master for GitHub Issues & Milestones.")

RepoArg = Annotated[str | None, typer.Argument(
    help="owner/repo. Defaults to $GITHUB_REPOSITORY (set in GitHub Actions).")]
TokenOpt = Annotated[str | None, typer.Option("--token", envvar=None, help="Override the saved token.")]


def _tracker(token: str | None = None):
    try:
        creds = auth.resolve_github(token)
    except PermissionError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(2)
    return create("github", creds)


def _repo(repo: str | None) -> str:
    repo = repo or os.getenv("GITHUB_REPOSITORY")
    if not repo:
        typer.secho("Pass a repository as owner/repo.", fg="red", err=True)
        raise typer.Exit(2)
    return repo


@app.command()
def login(
    with_token: Annotated[bool, typer.Option("--with-token", help="Read a token from stdin.")] = False,
    web: Annotated[bool, typer.Option("--web", help="Browser login (OAuth device flow).")] = False,
    base_url: Annotated[str | None, typer.Option(help="GitHub Enterprise API URL, e.g. https://ghe.example.com/api/v3")] = None,
):
    """Log in to GitHub. Works with any account and any repo it can access."""
    if web:
        client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
        if not client_id:
            typer.secho("Set GITHUB_OAUTH_CLIENT_ID (an OAuth App with device flow enabled), "
                        "or use a personal access token instead.", fg="red", err=True)
            raise typer.Exit(2)
        d = auth.device_flow_start(client_id)
        typer.echo(f"Open {d['verification_uri']} and enter code: ", nl=False)
        typer.secho(d["user_code"], bold=True)
        webbrowser.open(d["verification_uri"])
        token = auth.device_flow_poll(client_id, d["device_code"], d.get("interval", 5), d["expires_in"])
    elif with_token:
        token = sys.stdin.read().strip()
    else:
        typer.echo("Create a token at https://github.com/settings/tokens "
                   "(classic: 'repo' scope; fine-grained: Issues read/write, Metadata read, Contents read).")
        token = typer.prompt("GitHub token", hide_input=True).strip()

    tracker = create("github", {"token": token, "base_url": base_url})
    try:
        me = tracker.whoami()
    except Exception as e:
        typer.secho(f"Token rejected by GitHub: {e}", fg="red", err=True)
        raise typer.Exit(1)
    path = auth.save_credentials("github", {"token": token, "base_url": base_url, "login": me.login})
    typer.secho(f"Logged in as {me.login}. Credentials saved to {path}", fg="green")


@app.command()
def logout():
    """Forget the saved GitHub token."""
    typer.echo("Logged out." if auth.clear_credentials("github") else "Not logged in.")


@app.command()
def whoami(token: TokenOpt = None):
    """Show the signed-in account."""
    me = _tracker(token).whoami()
    typer.echo(f"{me.login}" + (f" ({me.name})" if me.name else ""))


@app.command()
def repos(limit: int = 50, token: TokenOpt = None):
    """List repositories you can audit (most recently updated first)."""
    for p in _tracker(token).list_projects(limit=limit):
        mark = "rw" if p.can_write else "ro"
        typer.echo(f"{mark}  {p.id}{'  (private)' if p.private else ''}")


@app.command()
def sprints(repo: RepoArg = None, all: bool = False, token: TokenOpt = None):
    """List milestones (sprints) in a repository."""
    t = _tracker(token)
    rid = _repo(repo)
    active = t.default_sprint(rid)
    for s in t.list_sprints(rid, "all" if all else "open"):
        due = s.due_on.date().isoformat() if s.due_on else "no due date"
        star = "*" if active and s.id == active.id else " "
        typer.echo(f"{star} #{s.id:<4} {s.title:<30} {s.state:<6} {due}")


@app.command()
def audit(
    repo: RepoArg = None,
    sprint: Annotated[str | None, typer.Option("--sprint", "-s", help="Milestone title or number. Default: open milestone with the nearest due date.")] = None,
    apply: Annotated[bool, typer.Option("--apply", help="Actually label/comment. Default is a dry run.")] = False,
    post_report: Annotated[bool, typer.Option("--post-report", help="With --apply, create/update a 'Sprint report' issue.")] = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Rules only, no model call.")] = False,
    model: Annotated[str | None, typer.Option(help="provider:model, e.g. anthropic:claude-sonnet-5-5 or openai:gpt-4o")] = None,
    config: Annotated[str | None, typer.Option(help="Local YAML config (else the repo's .github/scrum-agent.yml).")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o", help="Write the Markdown report to a file.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON summary instead of Markdown.")] = False,
    token: TokenOpt = None,
):
    """Audit a sprint: progress, stale/blocked/unassigned work, risks."""
    t = _tracker(token)
    overrides = {"llm_model": model, "llm_enabled": False if no_llm else None,
                 "post_report": True if post_report else None}
    try:
        r = run_service_audit(t, _repo(repo), sprint=sprint, apply=apply,
                              config_path=config, overrides=overrides)
    except (LookupError, ValueError) as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1)

    if output:
        with open(output, "w") as f:
            f.write(r.report)
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(r.report + "\n")

    if as_json:
        typer.echo(json.dumps({
            "repo": r.project_id, "sprint": r.sprint.title, "dry_run": r.dry_run,
            "percent_done": r.health.percent_done, "risk": r.health.risk_level,
            "stale": r.health.stale_numbers, "flagged": r.flagged,
            "actions": [asdict(a) for a in r.actions], "report_url": r.report_url,
            "errors": r.errors,
        }, indent=2))
    else:
        typer.echo(r.report)
    for e in r.errors:
        typer.secho(f"warning: {e}", fg="yellow", err=True)
    if r.report_url:
        typer.secho(f"Report: {r.report_url}", fg="green", err=True)
    if any(a.error for a in r.actions):
        raise typer.Exit(1)


@app.command("init-board")
def init_board(
    repo: RepoArg = None,
    apply: Annotated[bool, typer.Option("--apply", help="Make the changes. Default lists what would change.")] = False,
    labels_only: Annotated[bool, typer.Option("--labels-only", help="Only set up labels, no files.")] = False,
    token: TokenOpt = None,
):
    """Set up a repo's GitHub Issues for Scrum: labels, issue forms, PR template, workflow docs.

    Creates missing labels and updates the color/description of matching ones. Adds
    files only if they don't exist (never overwrites, never deletes).
    """
    from .setup_board import plan_and_apply

    rid = _repo(repo)
    steps = plan_and_apply(_tracker(token), rid, apply=apply, files=not labels_only)
    icon = {"create": "+", "update": "~", "keep": "=", "skip": "="}
    for s in steps:
        note = " (exists, left as is)" if s.action == "skip" else ""
        status = f"  ERROR {s.error}" if s.error else ""
        typer.echo(f" {icon[s.action]} {s.kind:<5} {s.name}{note}{status}")
    changes = [s for s in steps if s.action in ("create", "update")]
    if not apply:
        typer.secho(f"\nDry run: {len(changes)} change(s). Re-run with --apply to make them.", fg="yellow")
    else:
        failed = [s for s in steps if s.error]
        typer.secho(f"\nApplied {len(changes) - len(failed)} change(s) to {rid}.",
                    fg="red" if failed else "green")
        if failed:
            raise typer.Exit(1)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Run the web app (GitHub sign-in, repo picker, audits)."""
    import uvicorn

    uvicorn.run("scrum_agent.web.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
