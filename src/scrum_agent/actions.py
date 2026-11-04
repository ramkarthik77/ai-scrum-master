"""Side-effecting actions, exposed as LangChain tools.

All writes go through ``flag_issue_as_stuck``. It is idempotent: if the issue is
already labelled stale and the newest comment is our own nudge (nobody has
replied since), it does nothing rather than nagging again.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from .config import AgentConfig
from .trackers.base import ActionResult, TrackerProvider

NUDGE_MARKER = "<!-- scrum-agent:stale-nudge -->"


def default_nudge(assignees: tuple[str, ...] | list[str], hours_idle: float) -> str:
    who = " ".join(f"@{a}" for a in assignees) if assignees else "Team"
    days = hours_idle / 24
    return (
        f"{who}: this issue has had no activity for {days:.1f} days. "
        "Could you share a quick status update?\n\n"
        "- Current progress\n- Any blockers or dependencies\n- Delivery risk for this sprint\n\n"
        "If it's blocked, add the `status: blocked` label so it's tracked correctly."
    )


def flag_issue_as_stuck(
    tracker: TrackerProvider,
    project_id: str,
    issue_number: int,
    comment_body: str,
    cfg: AgentConfig,
    already_flagged: bool,
    apply: bool,
) -> ActionResult:
    key = str(issue_number)
    body = f"{NUDGE_MARKER}\n{comment_body.strip()}"
    if not apply:
        return ActionResult(key, "flag_stale", applied=False,
                            detail=f"dry-run: would label '{cfg.stale_label}' and comment")
    try:
        if already_flagged:
            recent = tracker.list_recent_comments(project_id, key, limit=1)
            if recent and NUDGE_MARKER in recent[-1]:
                return ActionResult(key, "flag_stale", applied=False,
                                    detail="skipped: already nudged, awaiting reply")
        else:
            tracker.add_label(project_id, key, cfg.stale_label)
        tracker.add_comment(project_id, key, body)
        return ActionResult(key, "flag_stale", applied=True,
                            detail=f"labelled '{cfg.stale_label}' and commented")
    except Exception as e:  # keep going on per-issue failures
        return ActionResult(key, "flag_stale", applied=False, error=f"{type(e).__name__}: {e}")


def make_tools(tracker: TrackerProvider, project_id: str, cfg: AgentConfig, apply: bool):
    """LangChain tools bound to one tracker + project (for tool-calling agents)."""

    def _fetch(sprint: str) -> list[dict]:
        """Retrieve all issues in a sprint (GitHub milestone title or number)."""
        return [
            {"number": i.number, "title": i.title, "state": i.state,
             "assignees": list(i.assignees), "labels": list(i.labels),
             "updated_at": i.updated_at.isoformat(), "comments": i.comments_count}
            for i in tracker.list_items(project_id, sprint)
        ]

    def _flag(issue_number: int, comment_body: str) -> str:
        """Label an issue as stale and post a polite request for a status update."""
        r = flag_issue_as_stuck(tracker, project_id, issue_number, comment_body, cfg,
                                already_flagged=False, apply=apply)
        return r.error or r.detail

    return [
        StructuredTool.from_function(_fetch, name="fetch_sprint_issues"),
        StructuredTool.from_function(_flag, name="flag_issue_as_stuck"),
    ]
