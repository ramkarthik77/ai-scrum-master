"""Tracker-agnostic data model and provider interface.

Everything above this layer (analysis, LLM review, reports, CLI, web) talks only
to ``TrackerProvider``. GitHub is the first implementation; Jira, Linear, etc.
plug in by implementing the same interface and registering in ``registry.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class WorkItem:
    """A single ticket / issue, normalised across trackers."""

    key: str  # "42" for GitHub, "PROJ-42" for Jira
    number: int  # numeric id used for display and LLM references
    title: str
    url: str
    state: str  # "open" | "closed"
    assignees: tuple[str, ...]
    labels: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    comments_count: int = 0
    is_pull_request: bool = False


@dataclass(frozen=True)
class Sprint:
    """A sprint (GitHub Milestone, Jira Sprint, ...)."""

    id: str
    title: str
    state: str  # "open" | "closed"
    url: str
    due_on: datetime | None = None
    description: str = ""


@dataclass(frozen=True)
class Project:
    """A board / repository the signed-in user can access."""

    id: str  # "owner/repo" for GitHub
    name: str
    url: str
    private: bool = False
    can_write: bool = False
    description: str = ""


@dataclass
class ActionResult:
    item_key: str
    action: str
    applied: bool
    detail: str = ""
    error: str | None = None


@dataclass
class TrackerIdentity:
    login: str
    name: str | None = None
    avatar_url: str | None = None
    extra: dict = field(default_factory=dict)


class TrackerProvider(ABC):
    """Interface every tracker backend implements."""

    #: short machine name, e.g. "github", "jira"
    name: str = "base"

    @abstractmethod
    def whoami(self) -> TrackerIdentity: ...

    @abstractmethod
    def list_projects(self, limit: int = 100) -> list[Project]: ...

    @abstractmethod
    def list_sprints(self, project_id: str, state: str = "open") -> list[Sprint]: ...

    @abstractmethod
    def list_items(self, project_id: str, sprint_id: str) -> list[WorkItem]: ...

    @abstractmethod
    def read_project_rules(self, project_id: str) -> str:
        """Return project rule files (CLAUDE.md / AGENTS.md) as text, or ''."""

    @abstractmethod
    def add_label(self, project_id: str, item_key: str, label: str) -> None: ...

    @abstractmethod
    def add_comment(self, project_id: str, item_key: str, body: str) -> None: ...

    @abstractmethod
    def list_recent_comments(
        self, project_id: str, item_key: str, limit: int = 5
    ) -> list[str]:
        """Return the bodies of the most recent comments, newest last."""

    @abstractmethod
    def upsert_report(self, project_id: str, sprint: Sprint, body: str) -> str:
        """Publish the sprint report somewhere visible; return its URL."""

    def read_agent_config(self, project_id: str) -> str:
        """Return the project's agent config YAML (if the tracker stores one), or ''."""
        return ""

    def default_sprint(self, project_id: str) -> Sprint | None:
        """The 'active' sprint: open, with the nearest due date (undated last)."""
        sprints = self.list_sprints(project_id, state="open")
        if not sprints:
            return None
        far_future = datetime.max.replace(tzinfo=None)
        return sorted(
            sprints,
            key=lambda s: (s.due_on.replace(tzinfo=None) if s.due_on else far_future, s.title),
        )[0]
