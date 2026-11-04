from __future__ import annotations

import pytest
from fakes import FakeTracker, item

from scrum_agent.actions import NUDGE_MARKER
from scrum_agent.analysis import analyze
from scrum_agent.config import AgentConfig
from scrum_agent.llm import SprintReview, StuckIssue, parse_stuck_numbers
from scrum_agent.service import audit


def board():
    return [
        item(1, assignees=["ana"], labels=["points: 3"], idle_hours=72),          # stale
        item(2, assignees=["ben"], labels=["size: small"], idle_hours=5),         # fresh
        item(3, idle_hours=100),                                                   # unassigned; not in-progress
        item(4, assignees=["ana"], labels=["status: blocked"], idle_hours=200),  # exempt
        item(5, state="closed", assignees=["ben"], labels=["points: 1"]),
        item(6, labels=["status: in-progress", "points: 2"], idle_hours=60),       # stale via label
        item(7, pr=True, idle_hours=500),                                          # PRs ignored
    ]


class FakeLLM:
    """Mimics a LangChain chat model with structured output."""

    def __init__(self, reviews):
        self.reviews = list(reviews)
        self.calls = 0

    def with_structured_output(self, schema, **kw):
        return self

    def invoke(self, messages):
        self.calls += 1
        return self.reviews.pop(0)


def test_analysis_rules():
    h = analyze(FakeTracker([]).sprints[0], board(), AgentConfig())
    assert h.total == 6 and h.closed == 1
    assert h.stale_numbers == [1, 6]
    assert [i.number for i in h.unassigned] == [3, 6]
    assert [i.number for i in h.missing_estimate] == [3, 4]
    assert [i.number for i in h.blocked] == [4]


def test_all_open_scope_includes_unassigned():
    h = analyze(FakeTracker([]).sprints[0], board(), AgentConfig(stale_scope="all_open"))
    assert sorted(h.stale_numbers) == [1, 3, 6]


def test_dry_run_changes_nothing():
    t = FakeTracker(board())
    r = audit(t, "o/r", overrides={"llm_enabled": False})
    assert r.dry_run and r.flagged == [1, 6]
    assert t.labels == [] and t.comments == {} and t.reports == []
    assert "dry run" in r.report


def test_apply_labels_comments_and_is_idempotent():
    t = FakeTracker(board())
    audit(t, "o/r", apply=True, overrides={"llm_enabled": False, "post_report": True})
    assert ("1", "status: stale") in t.labels and NUDGE_MARKER in t.comments["1"][0]
    assert "@ana" in t.comments["1"][0]
    assert len(t.reports) == 1

    # second run: issue now carries the label and our nudge is the latest comment
    t.items = [item(1, assignees=["ana"], labels=["points: 3", "status: stale"], idle_hours=72)]
    r = audit(t, "o/r", apply=True, overrides={"llm_enabled": False})
    assert len(t.comments["1"]) == 1
    assert "already nudged" in r.actions[0].detail


def test_llm_cannot_flag_non_candidates_and_retries():
    bad = SprintReview(risk_level="high", report_markdown="x",
                       stuck=[StuckIssue(number=2, reason="r", nudge="n"),
                              StuckIssue(number=99, reason="r", nudge="n")])
    good = SprintReview(risk_level="medium", report_markdown="## Risks\nOK",
                        stuck=[StuckIssue(number=6, reason="idle", nudge="Status please?")])
    llm = FakeLLM([bad, good])
    t = FakeTracker(board())
    r = audit(t, "o/r", apply=True, llm=llm)
    assert llm.calls == 2
    assert r.flagged == [6]
    assert "Status please?" in t.comments["6"][0]
    assert "1" not in t.comments  # model chose to omit #1
    assert "Risk **🟡 Medium**" in r.report


def test_llm_failure_falls_back_to_rules():
    class Broken:
        def with_structured_output(self, s, **kw):
            raise RuntimeError("no tools")

        def invoke(self, m):
            raise RuntimeError("down")

    r = audit(FakeTracker(board()), "o/r", llm=Broken())
    assert r.flagged == [1, 6]
    assert any("LLM review failed" in e for e in r.errors)


def test_parse_stuck_numbers():
    assert parse_stuck_numbers("blah #3\nSTUCK: #12, #34, #12") == [12, 34]
    assert parse_stuck_numbers("**Stuck**: #5") == [5]
    assert parse_stuck_numbers("see #7 and #8") == [7, 8]
    assert parse_stuck_numbers("STUCK: none") == []


def test_repo_config_is_used():
    t = FakeTracker(board(), config_yaml="stale_hours: 100\nllm_enabled: false\n")
    r = audit(t, "o/r")
    assert r.flagged == []


def test_bad_config_rejected():
    with pytest.raises(ValueError):
        AgentConfig.from_yaml_text("stale_hourz: 3")
    with pytest.raises(ValueError):
        AgentConfig(stale_scope="weird").validate()


def test_named_sprint_and_missing_sprint():
    t = FakeTracker(board())
    assert audit(t, "o/r", sprint="Sprint 1", overrides={"llm_enabled": False}).sprint.id == "1"
    with pytest.raises(LookupError):
        audit(t, "o/r", sprint="Nope", overrides={"llm_enabled": False})
