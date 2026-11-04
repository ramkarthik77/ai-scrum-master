from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scrum_agent.trackers.base import Project, Sprint, TrackerIdentity, TrackerProvider, WorkItem

NOW = datetime.now(UTC)


def item(n, state="open", assignees=(), labels=(), idle_hours=1, pr=False):
    return WorkItem(
        key=str(n), number=n, title=f"Issue {n}", url=f"https://github.com/o/r/issues/{n}",
        state=state, assignees=tuple(assignees), labels=tuple(labels),
        created_at=NOW - timedelta(days=10), updated_at=NOW - timedelta(hours=idle_hours),
        closed_at=NOW if state == "closed" else None, is_pull_request=pr,
    )


class FakeTracker(TrackerProvider):
    name = "fake"

    def __init__(self, items, sprints=None, rules="", config_yaml=""):
        self.items = items
        self.sprints = sprints or [Sprint("1", "Sprint 1", "open", "https://x/m/1", NOW + timedelta(days=3))]
        self.rules = rules
        self.config_yaml = config_yaml
        self.labels: list[tuple[str, str]] = []
        self.comments: dict[str, list[str]] = {}
        self.reports: list[str] = []

    def whoami(self):
        return TrackerIdentity("tester")

    def list_projects(self, limit=100):
        return [Project("o/r", "o/r", "https://github.com/o/r", can_write=True)]

    def list_sprints(self, project_id, state="open"):
        return [s for s in self.sprints if state == "all" or s.state == state]

    def list_items(self, project_id, sprint_id):
        return self.items

    def read_project_rules(self, project_id):
        return self.rules

    def read_agent_config(self, project_id):
        return self.config_yaml

    def add_label(self, project_id, item_key, label):
        self.labels.append((item_key, label))

    def add_comment(self, project_id, item_key, body):
        self.comments.setdefault(item_key, []).append(body)

    def list_recent_comments(self, project_id, item_key, limit=5):
        return self.comments.get(item_key, [])[-limit:]

    def upsert_report(self, project_id, sprint, body):
        self.reports.append(body)
        return "https://github.com/o/r/issues/999"
