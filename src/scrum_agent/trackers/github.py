"""GitHub implementation: Issues = work items, Milestones = sprints."""

from __future__ import annotations

from github import Auth, Github, GithubException
from github.Repository import Repository

from .base import (
    Project,
    Sprint,
    TrackerIdentity,
    TrackerProvider,
    WorkItem,
)

RULE_FILES = (".claude/CLAUDE.md", "CLAUDE.md", "AGENTS.md")
RULES_MAX_CHARS = 8000
REPORT_LABEL = "sprint-report"
LABEL_COLORS = {"status: stale": "fbca04", REPORT_LABEL: "0e8a16"}


class GitHubTracker(TrackerProvider):
    name = "github"

    def __init__(self, token: str, base_url: str | None = None):
        if not token:
            raise ValueError("A GitHub token is required (run `scrum-agent login`).")
        kwargs = {"auth": Auth.Token(token), "per_page": 100}
        if base_url:  # GitHub Enterprise Server: https://ghe.example.com/api/v3
            kwargs["base_url"] = base_url
        self._gh = Github(**kwargs)
        self._repos: dict[str, Repository] = {}

    # -- helpers ---------------------------------------------------------
    def _repo(self, project_id: str) -> Repository:
        if "/" not in project_id:
            raise ValueError(f"Expected 'owner/repo', got {project_id!r}")
        if project_id not in self._repos:
            self._repos[project_id] = self._gh.get_repo(project_id)
        return self._repos[project_id]

    def _milestone(self, project_id: str, sprint_id: str):
        repo = self._repo(project_id)
        if sprint_id.isdigit():
            return repo.get_milestone(int(sprint_id))
        for m in repo.get_milestones(state="all"):
            if m.title == sprint_id:
                return m
        raise LookupError(f"Milestone {sprint_id!r} not found in {project_id}")

    @staticmethod
    def _sprint(m) -> Sprint:
        return Sprint(
            id=str(m.number),
            title=m.title,
            state=m.state,
            url=m.html_url,
            due_on=m.due_on,
            description=m.description or "",
        )

    def _ensure_label(self, repo: Repository, label: str) -> None:
        try:
            repo.get_label(label)
        except GithubException as e:
            if e.status != 404:
                raise
            repo.create_label(label, LABEL_COLORS.get(label, "ededed"))

    # -- interface -------------------------------------------------------
    def whoami(self) -> TrackerIdentity:
        u = self._gh.get_user()
        return TrackerIdentity(login=u.login, name=u.name, avatar_url=u.avatar_url)

    def list_projects(self, limit: int = 100) -> list[Project]:
        out: list[Project] = []
        for r in self._gh.get_user().get_repos(sort="updated", affiliation="owner,collaborator,organization_member"):
            perms = r.permissions
            out.append(
                Project(
                    id=r.full_name,
                    name=r.full_name,
                    url=r.html_url,
                    private=r.private,
                    can_write=bool(perms and (perms.push or perms.triage or perms.admin)),
                    description=r.description or "",
                )
            )
            if len(out) >= limit:
                break
        return out

    def list_sprints(self, project_id: str, state: str = "open") -> list[Sprint]:
        return [self._sprint(m) for m in self._repo(project_id).get_milestones(state=state)]

    def get_sprint(self, project_id: str, sprint_id: str) -> Sprint:
        return self._sprint(self._milestone(project_id, sprint_id))

    def list_items(self, project_id: str, sprint_id: str) -> list[WorkItem]:
        repo = self._repo(project_id)
        milestone = self._milestone(project_id, sprint_id)
        items: list[WorkItem] = []
        for i in repo.get_issues(milestone=milestone, state="all"):
            if REPORT_LABEL in {lbl.name for lbl in i.labels}:
                continue  # don't audit our own report issue
            items.append(
                WorkItem(
                    key=str(i.number),
                    number=i.number,
                    title=i.title,
                    url=i.html_url,
                    state=i.state,
                    assignees=tuple(a.login for a in i.assignees),
                    labels=tuple(lbl.name for lbl in i.labels),
                    created_at=i.created_at,
                    updated_at=i.updated_at,
                    closed_at=i.closed_at,
                    comments_count=i.comments,
                    is_pull_request=i.pull_request is not None,
                )
            )
        return items

    def read_project_rules(self, project_id: str) -> str:
        repo = self._repo(project_id)
        parts = []
        for path in RULE_FILES:
            try:
                f = repo.get_contents(path)
            except GithubException:
                continue
            if isinstance(f, list):
                continue
            text = f.decoded_content.decode("utf-8", errors="replace")
            parts.append(f"## {path}\n{text}")
        return "\n\n".join(parts)[:RULES_MAX_CHARS]

    def existing_labels(self, project_id: str) -> dict[str, tuple[str, str]]:
        return {lbl.name: (lbl.color, lbl.description or "") for lbl in self._repo(project_id).get_labels()}

    def upsert_label(self, project_id: str, name: str, color: str, description: str) -> None:
        repo = self._repo(project_id)
        try:
            repo.get_label(name).edit(name, color, description)
        except GithubException as e:
            if e.status != 404:
                raise
            repo.create_label(name, color, description)

    def file_exists(self, project_id: str, path: str) -> bool:
        try:
            self._repo(project_id).get_contents(path)
            return True
        except GithubException as e:
            if e.status == 404:
                return False
            raise

    def create_file(self, project_id: str, path: str, content: str, message: str) -> None:
        self._repo(project_id).create_file(path, message, content)

    def read_agent_config(self, project_id: str) -> str:
        try:
            f = self._repo(project_id).get_contents(".github/scrum-agent.yml")
        except GithubException:
            return ""
        return "" if isinstance(f, list) else f.decoded_content.decode("utf-8", errors="replace")

    def add_label(self, project_id: str, item_key: str, label: str) -> None:
        repo = self._repo(project_id)
        self._ensure_label(repo, label)
        repo.get_issue(int(item_key)).add_to_labels(label)

    def add_comment(self, project_id: str, item_key: str, body: str) -> None:
        self._repo(project_id).get_issue(int(item_key)).create_comment(body)

    def list_recent_comments(self, project_id: str, item_key: str, limit: int = 5) -> list[str]:
        issue = self._repo(project_id).get_issue(int(item_key))
        if issue.comments == 0:
            return []
        comments = issue.get_comments()
        start = max(0, issue.comments - limit)
        return [c.body or "" for c in comments[start:]]

    def upsert_report(self, project_id: str, sprint: Sprint, body: str) -> str:
        """Keep one 'Sprint report' issue per milestone and refresh its body."""
        repo = self._repo(project_id)
        self._ensure_label(repo, REPORT_LABEL)
        title = f"Sprint report: {sprint.title}"
        for issue in repo.get_issues(state="open", labels=[REPORT_LABEL]):
            if issue.title == title:
                issue.edit(body=body)
                return issue.html_url
        issue = repo.create_issue(title=title, body=body, labels=[REPORT_LABEL])
        return issue.html_url
