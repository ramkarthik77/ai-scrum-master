"""Deterministic board-health checks.

These run without an LLM so the agent always produces a correct baseline; the
LLM layer narrates, prioritises and may *narrow* the stale list, but can never
flag an issue that fails these checks.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .config import AgentConfig
from .trackers.base import Sprint, WorkItem


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass
class Finding:
    number: int
    title: str
    url: str
    assignees: tuple[str, ...]
    hours_idle: float
    already_flagged: bool = False


@dataclass
class SprintHealth:
    sprint: Sprint
    generated_at: datetime
    total: int
    closed: int
    open: int
    percent_done: float
    days_left: float | None
    stale: list[Finding] = field(default_factory=list)
    unassigned: list[WorkItem] = field(default_factory=list)
    missing_estimate: list[WorkItem] = field(default_factory=list)
    blocked: list[WorkItem] = field(default_factory=list)
    over_wip: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    by_assignee: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def stale_numbers(self) -> list[int]:
        return [f.number for f in self.stale]

    @property
    def risk_level(self) -> str:
        """Simple heuristic; the LLM may refine it."""
        if self.total == 0:
            return "low"
        score = 0
        if self.days_left is not None and self.days_left <= 2 and self.percent_done < 70:
            score += 2
        score += min(len(self.stale), 3)
        score += min(len(self.blocked), 2)
        score += 1 if self.over_wip else 0
        return "high" if score >= 4 else "medium" if score >= 2 else "low"


def has_estimate(item: WorkItem, prefixes: list[str]) -> bool:
    low = [p.lower() for p in prefixes]
    return any(lbl.lower().startswith(p) for lbl in item.labels for p in low)


def is_in_progress(item: WorkItem, cfg: AgentConfig) -> bool:
    return item.state == "open" and (
        bool(item.assignees) or any(lbl in cfg.in_progress_labels for lbl in item.labels)
    )


def analyze(
    sprint: Sprint,
    items: list[WorkItem],
    cfg: AgentConfig,
    now: datetime | None = None,
) -> SprintHealth:
    now = _aware(now or datetime.now(UTC))
    issues = [i for i in items if not i.is_pull_request]
    closed = [i for i in issues if i.state == "closed"]
    open_ = [i for i in issues if i.state == "open"]
    total = len(issues)

    days_left = None
    if sprint.due_on:
        days_left = round((_aware(sprint.due_on) - now) / timedelta(days=1), 1)

    health = SprintHealth(
        sprint=sprint,
        generated_at=now,
        total=total,
        closed=len(closed),
        open=len(open_),
        percent_done=round(100 * len(closed) / total, 1) if total else 0.0,
        days_left=days_left,
    )

    threshold = timedelta(hours=cfg.stale_hours)
    wip: Counter[str] = Counter()
    for item in open_:
        labels = set(item.labels)
        if not item.assignees:
            health.unassigned.append(item)
        if not has_estimate(item, cfg.estimate_label_prefixes) and not labels & set(cfg.no_estimate_labels):
            health.missing_estimate.append(item)
        if labels & set(cfg.blocked_labels):
            health.blocked.append(item)
        for a in item.assignees:
            wip[a] += 1

        in_scope = cfg.stale_scope == "all_open" or is_in_progress(item, cfg)
        exempt = bool(labels & set(cfg.exempt_labels))
        idle = now - _aware(item.updated_at)
        if in_scope and not exempt and idle >= threshold:
            health.stale.append(
                Finding(
                    number=item.number,
                    title=item.title,
                    url=item.url,
                    assignees=item.assignees,
                    hours_idle=round(idle / timedelta(hours=1), 1),
                    already_flagged=cfg.stale_label in labels,
                )
            )

    health.stale.sort(key=lambda f: -f.hours_idle)

    cols = {"Backlog": 0, **{c: 0 for c in cfg.status_columns}, "Done": len(closed)}
    for item in open_:
        col = next((c for c in cfg.status_columns if c in item.labels), "Backlog")
        cols[col] += 1
    health.by_status = cols
    health.over_wip = {a: n for a, n in wip.items() if n > cfg.wip_limit_per_person}

    per: dict[str, dict[str, int]] = {}
    for item in issues:
        for a in item.assignees or ("Unassigned",):
            row = per.setdefault(a, {"open": 0, "closed": 0})
            row[item.state if item.state in row else "open"] += 1
    health.by_assignee = dict(sorted(per.items()))
    return health
