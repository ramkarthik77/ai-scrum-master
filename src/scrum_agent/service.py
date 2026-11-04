"""Entry point shared by the CLI, web app and GitHub Action."""

from __future__ import annotations

from typing import Any

from .config import AgentConfig
from .graph import AuditResult, run_audit
from .trackers.base import TrackerProvider


def resolve_config(
    tracker: TrackerProvider,
    project_id: str,
    config_path: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> AgentConfig:
    """Local file > repo's .github/scrum-agent.yml > defaults; then env; then overrides."""
    if config_path:
        cfg = AgentConfig.load(path=config_path)
    else:
        try:
            text = tracker.read_agent_config(project_id)
        except Exception:
            text = ""
        cfg = AgentConfig.load(yaml_text=text or None)
    for k, v in (overrides or {}).items():
        if v is not None:
            setattr(cfg, k, v)
    cfg.validate()
    return cfg


def audit(
    tracker: TrackerProvider,
    project_id: str,
    sprint: str | None = None,
    apply: bool = False,
    config_path: str | None = None,
    overrides: dict[str, Any] | None = None,
    llm: Any = None,
) -> AuditResult:
    cfg = resolve_config(tracker, project_id, config_path, overrides)
    return run_audit(tracker, project_id, cfg, sprint_id=sprint, apply=apply, llm=llm)
