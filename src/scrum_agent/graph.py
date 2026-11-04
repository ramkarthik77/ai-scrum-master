"""LangGraph workflow.

    load ─► analyze ─► review ─► validate ─┬─► act ─► report ─► publish ─► END
                         ▲                 │
                         └── retry (≤1) ───┘   (model cited issues outside the candidates)

``review`` is skipped when the LLM is disabled; the deterministic stale list is
then used directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from . import llm as llm_mod
from .actions import default_nudge, flag_issue_as_stuck
from .analysis import SprintHealth, analyze
from .config import AgentConfig
from .report import render
from .trackers.base import ActionResult, Sprint, TrackerProvider, WorkItem

MAX_REVIEW_ATTEMPTS = 2


class AuditState(TypedDict, total=False):
    project_id: str
    sprint_id: str | None
    apply: bool
    sprint: Sprint
    items: list[WorkItem]
    rules: str
    health: SprintHealth
    review: llm_mod.SprintReview | None
    review_attempts: int
    review_feedback: str
    flagged: list[int]
    nudges: dict[int, str]
    actions: list[ActionResult]
    report: str
    report_url: str | None
    errors: list[str]


@dataclass
class AuditResult:
    project_id: str
    sprint: Sprint
    health: SprintHealth
    report: str
    flagged: list[int]
    actions: list[ActionResult]
    report_url: str | None
    dry_run: bool
    errors: list[str]


def build_graph(tracker: TrackerProvider, cfg: AgentConfig, llm: Any = None):
    def load(state: AuditState) -> AuditState:
        pid = state["project_id"]
        sid = state.get("sprint_id")
        if sid:
            sprint = next((s for s in tracker.list_sprints(pid, "all") if s.id == sid or s.title == sid), None)
            if sprint is None:
                raise LookupError(f"Sprint {sid!r} not found in {pid}")
        else:
            sprint = tracker.default_sprint(pid)
            if sprint is None:
                raise LookupError(f"No open milestones in {pid}. Create one to act as the sprint.")
        rules = ""
        try:
            rules = tracker.read_project_rules(pid)
        except Exception as e:  # rules are optional
            state.setdefault("errors", []).append(f"Could not read project rules: {e}")
        return {"sprint": sprint, "items": tracker.list_items(pid, sprint.id), "rules": rules,
                "review_attempts": 0, "errors": state.get("errors", [])}

    def analyze_node(state: AuditState) -> AuditState:
        return {"health": analyze(state["sprint"], state["items"], cfg)}

    def review_node(state: AuditState) -> AuditState:
        health = state["health"]
        rules = state.get("rules", "")
        if fb := state.get("review_feedback"):
            rules = (rules + "\n\nCORRECTION FROM VALIDATOR: " + fb).strip()
        try:
            rv = llm_mod.review(health, cfg, rules, llm=llm)
        except Exception as e:
            return {"review": None, "review_attempts": state.get("review_attempts", 0) + 1,
                    "errors": state.get("errors", []) + [f"LLM review failed, using rules only: {e}"]}
        return {"review": rv, "review_attempts": state.get("review_attempts", 0) + 1}

    def validate_node(state: AuditState) -> AuditState:
        health = state["health"]
        candidates = {f.number: f for f in health.stale}
        rv = state.get("review")
        if rv is None:  # no LLM: deterministic list
            chosen = list(candidates)
            nudges = {}
            invalid: list[int] = []
        else:
            chosen = [s.number for s in rv.stuck if s.number in candidates]
            invalid = [s.number for s in rv.stuck if s.number not in candidates]
            nudges = {s.number: s.nudge for s in rv.stuck if s.number in candidates and s.nudge.strip()}
        feedback = ""
        if invalid:
            feedback = (f"You listed {invalid} as stuck but they are not in STALE_CANDIDATES "
                        f"{sorted(candidates)}. Only use candidate numbers.")
        flagged = list(dict.fromkeys(chosen))
        for n in flagged:
            f = candidates[n]
            nudges.setdefault(n, default_nudge(f.assignees, f.hours_idle))
        return {"flagged": flagged, "nudges": nudges, "review_feedback": feedback}

    def route_after_validate(state: AuditState) -> str:
        if state.get("review_feedback") and state.get("review_attempts", 0) < MAX_REVIEW_ATTEMPTS:
            return "review"
        return "act"

    def act(state: AuditState) -> AuditState:
        health = state["health"]
        by_num = {f.number: f for f in health.stale}
        actions = [
            flag_issue_as_stuck(tracker, state["project_id"], n, state["nudges"][n], cfg,
                                already_flagged=by_num[n].already_flagged, apply=state["apply"])
            for n in state["flagged"]
        ]
        return {"actions": actions}

    def report_node(state: AuditState) -> AuditState:
        rv = state.get("review")
        health = state["health"]
        md = render(
            health,
            risk_level=rv.risk_level if rv else health.risk_level,
            narrative=rv.report_markdown if rv else "",
            flagged=state["flagged"],
            actions=state["actions"],
            dry_run=not state["apply"],
            model=cfg.llm_model if rv else None,
        )
        return {"report": md}

    def publish(state: AuditState) -> AuditState:
        if not (cfg.post_report and state["apply"]):
            return {"report_url": None}
        try:
            url = tracker.upsert_report(state["project_id"], state["sprint"], state["report"])
            return {"report_url": url}
        except Exception as e:
            return {"report_url": None, "errors": state.get("errors", []) + [f"Could not publish report: {e}"]}

    g = StateGraph(AuditState)
    g.add_node("load", load)
    g.add_node("analyze", analyze_node)
    g.add_node("review", review_node)
    g.add_node("validate", validate_node)
    g.add_node("act", act)
    g.add_node("report", report_node)
    g.add_node("publish", publish)

    g.set_entry_point("load")
    g.add_edge("load", "analyze")
    g.add_conditional_edges("analyze", lambda s: "review" if cfg.llm_enabled else "validate",
                            {"review": "review", "validate": "validate"})
    g.add_edge("review", "validate")
    g.add_conditional_edges("validate", route_after_validate, {"review": "review", "act": "act"})
    g.add_edge("act", "report")
    g.add_edge("report", "publish")
    g.add_edge("publish", END)
    return g.compile()


def run_audit(
    tracker: TrackerProvider,
    project_id: str,
    cfg: AgentConfig,
    sprint_id: str | None = None,
    apply: bool = False,
    llm: Any = None,
) -> AuditResult:
    app = build_graph(tracker, cfg, llm=llm)
    final = app.invoke({"project_id": project_id, "sprint_id": sprint_id, "apply": apply, "errors": []})
    return AuditResult(
        project_id=project_id,
        sprint=final["sprint"],
        health=final["health"],
        report=final["report"],
        flagged=final["flagged"],
        actions=final["actions"],
        report_url=final.get("report_url"),
        dry_run=not apply,
        errors=final.get("errors", []),
    )
