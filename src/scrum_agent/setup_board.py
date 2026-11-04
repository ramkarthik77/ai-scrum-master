"""Apply the standard Scrum setup (board.py) to a repository."""

from __future__ import annotations

from dataclasses import dataclass

from .board import FILES, LABELS
from .trackers.base import TrackerProvider

COMMIT_MESSAGE = "Add Scrum issue templates and workflow docs (scrum-agent init-board)"


@dataclass
class SetupStep:
    kind: str  # "label" | "file"
    name: str
    action: str  # "create" | "update" | "keep" | "skip"
    applied: bool = False
    error: str | None = None


def plan_and_apply(
    tracker: TrackerProvider,
    project_id: str,
    apply: bool = False,
    labels: bool = True,
    files: bool = True,
) -> list[SetupStep]:
    """Create missing labels (and fix colors/descriptions of ours), and add files
    that don't exist yet. Never overwrites existing files or deletes labels."""
    steps: list[SetupStep] = []
    if labels:
        existing = {k.lower(): v for k, v in tracker.existing_labels(project_id).items()}
        for spec in LABELS:
            cur = existing.get(spec.name.lower())
            if cur is None:
                action = "create"
            elif cur[0].lower() != spec.color or (cur[1] or "") != spec.description:
                action = "update"
            else:
                action = "keep"
            steps.append(SetupStep("label", spec.name, action))
            if apply and action != "keep":
                try:
                    tracker.upsert_label(project_id, spec.name, spec.color, spec.description)
                    steps[-1].applied = True
                except Exception as e:
                    steps[-1].error = f"{type(e).__name__}: {e}"
    if files:
        for path, content in FILES.items():
            action = "skip" if tracker.file_exists(project_id, path) else "create"
            steps.append(SetupStep("file", path, action))
            if apply and action == "create":
                try:
                    tracker.create_file(project_id, path, content, f"{COMMIT_MESSAGE}: {path}")
                    steps[-1].applied = True
                except Exception as e:
                    steps[-1].error = f"{type(e).__name__}: {e}"
    return steps
