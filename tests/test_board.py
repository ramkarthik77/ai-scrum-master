from __future__ import annotations

import yaml
from fakes import BoardFakeTracker, FakeTracker, item

from scrum_agent.analysis import analyze
from scrum_agent.board import FILES, LABELS
from scrum_agent.config import AgentConfig
from scrum_agent.setup_board import plan_and_apply


def test_issue_forms_are_valid_yaml():
    for path, content in FILES.items():
        if path.endswith(".yml"):
            data = yaml.safe_load(content)
            if "ISSUE_TEMPLATE/" in path and not path.endswith("config.yml"):
                assert data["name"] and data["body"]
                label_names = {lbl.name for lbl in LABELS}
                assert set(data["labels"]) <= label_names, path


def test_dry_run_then_apply_is_idempotent():
    t = BoardFakeTracker(labels={"status: blocked": ("000000", "old")},
                         files={"docs/scrum/WORKFLOW.md": "mine"})
    steps = plan_and_apply(t, "o/r")
    assert all(not s.applied for s in steps)
    assert t.label_store == {"status: blocked": ("000000", "old")}
    by = {(s.kind, s.name): s.action for s in steps}
    assert by[("label", "status: blocked")] == "update"
    assert by[("label", "type: story")] == "create"
    assert by[("file", "docs/scrum/WORKFLOW.md")] == "skip"

    plan_and_apply(t, "o/r", apply=True)
    assert t.files["docs/scrum/WORKFLOW.md"] == "mine"  # never overwritten
    assert ".github/ISSUE_TEMPLATE/story.yml" in t.files
    again = plan_and_apply(t, "o/r")
    assert {s.action for s in again} <= {"keep", "skip"}


def test_board_columns_and_epic_estimate_exemption():
    items = [
        item(1, labels=["status: ready", "points: 1"]),
        item(2, assignees=["a"], labels=["status: in-progress", "points: 2"]),
        item(3, assignees=["a"], labels=["status: in-review", "points: 3"]),
        item(4, labels=["type: epic"]),
        item(5, state="closed", labels=["points: 1"]),
    ]
    h = analyze(FakeTracker([]).sprints[0], items, AgentConfig())
    assert h.by_status == {"Backlog": 1, "status: ready": 1, "status: in-progress": 1,
                           "status: in-review": 1, "Done": 1}
    assert h.missing_estimate == []
