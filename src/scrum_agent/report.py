"""Markdown sprint report."""

from __future__ import annotations

from .analysis import SprintHealth
from .trackers.base import ActionResult, WorkItem

REPORT_MARKER = "<!-- scrum-agent:report -->"
RISK_BADGE = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🔴 High"}


def _link(number: int, url: str) -> str:
    return f"[#{number}]({url})"


def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _items(rows: list[WorkItem]) -> str:
    return "\n".join(f"- {_link(i.number, i.url)} {i.title}" for i in rows) or "_None_"


def render(
    health: SprintHealth,
    risk_level: str,
    narrative: str,
    flagged: list[int],
    actions: list[ActionResult],
    dry_run: bool,
    model: str | None,
) -> str:
    s = health.sprint
    due = s.due_on.date().isoformat() if s.due_on else "no due date"
    left = "" if health.days_left is None else (
        f" · {health.days_left:g} days left" if health.days_left >= 0 else f" · **{-health.days_left:g} days overdue**"
    )
    out = [
        REPORT_MARKER,
        f"# Sprint report: [{s.title}]({s.url})",
        f"Due {due}{left} · Risk **{RISK_BADGE.get(risk_level, risk_level)}** · "
        f"generated {health.generated_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"`{_bar(health.percent_done)}` **{health.percent_done:g}%** done "
        f"({health.closed}/{health.total} closed, {health.open} open)",
        "",
        "| Check | Count |",
        "|---|---|",
        f"| Stale (idle ≥ threshold) | {len(health.stale)} |",
        f"| Blocked | {len(health.blocked)} |",
        f"| Unassigned | {len(health.unassigned)} |",
        f"| Missing estimate | {len(health.missing_estimate)} |",
        f"| People over WIP limit | {len(health.over_wip)} |",
        "",
    ]
    if narrative.strip():
        out += ["## Analysis", narrative.strip(), ""]

    if health.stale:
        out += ["## Stale issues", "| Issue | Assignees | Idle | Flagged |", "|---|---|---|---|"]
        for f in health.stale:
            who = ", ".join(f"@{a}" for a in f.assignees) or "—"
            mark = "✅" if f.number in flagged else "—"
            out.append(f"| {_link(f.number, f.url)} {f.title} | {who} | {f.hours_idle / 24:.1f}d | {mark} |")
        out.append("")

    out += ["## Blocked", _items(health.blocked), "",
            "## Unassigned", _items(health.unassigned), "",
            "## Missing estimate", _items(health.missing_estimate), ""]

    if health.over_wip:
        out += ["## Over WIP limit", *[f"- @{a}: {n} open issues" for a, n in health.over_wip.items()], ""]

    if health.by_assignee:
        out += ["## By assignee", "| Person | Open | Closed |", "|---|---|---|"]
        out += [f"| {a} | {r['open']} | {r['closed']} |" for a, r in health.by_assignee.items()]
        out.append("")

    out.append("## Actions" + (" (dry run, nothing changed)" if dry_run else ""))
    if actions:
        for a in actions:
            status = f"⚠️ {a.error}" if a.error else a.detail
            out.append(f"- #{a.item_key}: {status}")
    else:
        out.append("_No actions needed._")
    out += ["", f"<sub>scrum-agent · model: {model or 'none (rules only)'}</sub>"]
    return "\n".join(out)
