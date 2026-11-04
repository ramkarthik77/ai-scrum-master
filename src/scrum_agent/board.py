"""Standard GitHub Issues setup for Scrum, used by `scrum-agent init-board`.

Conventions follow the reference projects (copilot-scrum-guided, ai-scrum-master-template,
ai-scrum) adapted to one consistent scheme:

  Board columns  : (no status) Backlog → status: ready → status: in-progress
                   → status: in-review → closed (Done)
  Flags          : status: blocked, status: stale (set by the agent), needs: clarification
  Sprints        : one milestone per sprint, titled "Sprint N", with a due date
  Estimates      : points: 1/2/3/5/8/13 labels (read by the agent)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str
    description: str


LABELS: list[LabelSpec] = [
    # Board columns (no status label = Backlog; closed = Done)
    LabelSpec("status: ready", "c2e0c6", "Refined and planned for the current sprint"),
    LabelSpec("status: in-progress", "0e8a16", "Actively being worked on"),
    LabelSpec("status: in-review", "1d76db", "PR open or awaiting validation"),
    # Flags
    LabelSpec("status: blocked", "b60205", "Waiting on something outside the team"),
    LabelSpec("status: stale", "fbca04", "No activity past the agreed threshold (set by the scrum agent)"),
    LabelSpec("needs: clarification", "d876e3", "Missing detail or acceptance criteria"),
    # Work type
    LabelSpec("type: epic", "3e4b9e", "Large body of work split into stories"),
    LabelSpec("type: story", "5319e7", "User-facing value, has acceptance criteria"),
    LabelSpec("type: bug", "d73a4a", "Something is broken"),
    LabelSpec("type: task", "bfd4f2", "Technical or chore work"),
    LabelSpec("type: spike", "fef2c0", "Time-boxed research"),
    LabelSpec("type: impediment", "e99695", "Blocker raised to the Scrum Master"),
    # Priority
    LabelSpec("priority: high", "b60205", "Do first"),
    LabelSpec("priority: medium", "fbca04", "Normal priority"),
    LabelSpec("priority: low", "0e8a16", "Nice to have"),
    # Estimates (Fibonacci story points)
    *[LabelSpec(f"points: {p}", "ededed", f"{p} story point{'s' if p != 1 else ''}") for p in (1, 2, 3, 5, 8, 13)],
    # Agent output
    LabelSpec("sprint-report", "0e8a16", "Sprint report maintained by the scrum agent"),
]

STATUS_COLUMNS = ["status: ready", "status: in-progress", "status: in-review"]

_POINTS_HELP = "Add the matching `points: N` label during refinement so the scrum agent can track estimates."

STORY_FORM = f"""name: User story
description: User-facing value with acceptance criteria
title: "[Story] "
labels: ["type: story"]
body:
  - type: textarea
    id: story
    attributes:
      label: Story
      description: As a <who>, I want <what>, so that <why>.
      placeholder: As a team lead, I want to see stale issues, so that I can unblock people early.
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      description: Observable, testable outcomes. One per line.
      value: |
        - [ ] Given ..., when ..., then ...
        - [ ]
    validations:
      required: true
  - type: textarea
    id: verify
    attributes:
      label: How to verify
      description: Command, test or manual steps that prove it's done.
      render: shell
  - type: input
    id: epic
    attributes:
      label: Epic
      description: Parent epic issue, e.g. #4 (optional)
  - type: dropdown
    id: points
    attributes:
      label: Story points (estimate)
      description: "{_POINTS_HELP}"
      options: ["Not estimated", "1", "2", "3", "5", "8", "13"]
  - type: dropdown
    id: priority
    attributes:
      label: Priority
      options: ["Medium", "High", "Low"]
  - type: textarea
    id: notes
    attributes:
      label: Notes, designs, dependencies
"""

BUG_FORM = """name: Bug
description: Something is broken
title: "[Bug] "
labels: ["type: bug"]
body:
  - type: textarea
    id: what
    attributes:
      label: What happened?
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      value: |
        1.
        2.
        3.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behaviour
    validations:
      required: true
  - type: dropdown
    id: severity
    attributes:
      label: Severity
      options: ["Major: feature unusable", "Minor: workaround exists", "Critical: data loss or outage"]
  - type: textarea
    id: env
    attributes:
      label: Environment and logs
      render: shell
"""

TASK_FORM = f"""name: Task or spike
description: Technical work, chore or time-boxed research
title: "[Task] "
labels: ["type: task"]
body:
  - type: textarea
    id: goal
    attributes:
      label: Goal
      description: What needs doing and why. For a spike, the question to answer and the time box.
    validations:
      required: true
  - type: textarea
    id: done
    attributes:
      label: Done when
      value: |
        - [ ]
    validations:
      required: true
  - type: dropdown
    id: points
    attributes:
      label: Story points (estimate)
      description: "{_POINTS_HELP}"
      options: ["Not estimated", "1", "2", "3", "5", "8", "13"]
"""

EPIC_FORM = """name: Epic
description: A large outcome split into stories
title: "[Epic] "
labels: ["type: epic"]
body:
  - type: textarea
    id: outcome
    attributes:
      label: Outcome
      description: What changes for users or the business when this is done?
    validations:
      required: true
  - type: textarea
    id: stories
    attributes:
      label: Stories
      description: Task list of the stories in this epic. Create them with the User story template.
      value: |
        - [ ] #
    validations:
      required: true
  - type: textarea
    id: success
    attributes:
      label: Success measures
"""

IMPEDIMENT_FORM = """name: Impediment
description: Something is blocking the team; raise it to the Scrum Master
title: "[Impediment] "
labels: ["type: impediment", "priority: high"]
body:
  - type: textarea
    id: blocker
    attributes:
      label: What is blocked, and by what?
      description: Link the blocked issues (e.g. #12) and add `status: blocked` to them.
    validations:
      required: true
  - type: textarea
    id: impact
    attributes:
      label: Impact on the sprint goal
    validations:
      required: true
  - type: input
    id: owner
    attributes:
      label: Who can unblock it?
  - type: input
    id: needed_by
    attributes:
      label: Needed by (date)
"""

TEMPLATE_CONFIG = """blank_issues_enabled: true
contact_links:
  - name: Sprint workflow and label guide
    url: ../../blob/HEAD/docs/scrum/WORKFLOW.md
    about: How we use issues, labels and milestones
"""

PR_TEMPLATE = """## What and why

Closes #

## How to test

-

## Checklist (Definition of Done)
- [ ] Acceptance criteria met
- [ ] Tests added or updated, CI green
- [ ] Docs updated if behaviour changed
- [ ] Issue moved to `status: in-review`
"""

WORKFLOW_DOC = """# Sprint workflow

How this repository uses GitHub Issues for Scrum. The AI Scrum Master agent reads
these conventions to audit sprints.

## Board

| Column | How it's represented |
|---|---|
| Backlog | Open issue with no `status:` label and no milestone |
| Ready (in sprint) | Milestone `Sprint N` + `status: ready` |
| In progress | `status: in-progress` and an assignee |
| In review | `status: in-review` (PR open or awaiting validation) |
| Done | Issue closed as completed (via PR `Closes #N` or manually) |
| Abandoned | Issue closed as "not planned", with a comment saying why |

Flags that can sit on any open issue:
- `status: blocked`: waiting on something outside the team. Link an Impediment issue. The agent never nudges blocked issues.
- `status: stale`: added by the agent when an in-progress issue has no activity past the threshold. Reply with a status update and remove it.
- `needs: clarification`: missing detail or acceptance criteria; not ready for a sprint.

Move an issue between columns by swapping its `status:` label. Keep only one column label at a time.

**WIP limit:** each person has at most 3 issues in progress (`wip_limit_per_person` in
`.github/scrum-agent.yml`). Finish or hand over before pulling new work. When handing over,
comment with what's done, what's left and how to verify, then reassign.

## Sprints

- One milestone per sprint, titled `Sprint N`, with a due date (the sprint end).
- The open milestone with the nearest due date is the active sprint.
- Sprint planning: pick issues from the backlog, set the milestone, add `status: ready`, an assignee, a priority and a `points:` estimate.
- Unfinished work at sprint end is moved to the next milestone (carry-over) and noted in `docs/sprints/velocity.md`.

## Issue types

Use the templates on the New issue page:
- **Epic** (`type: epic`): a large outcome; list its stories as a task list and link each story back with "Epic: #N".
- **User story** (`type: story`): as a / I want / so that, plus acceptance criteria.
- **Bug** (`type: bug`): steps to reproduce and expected behaviour.
- **Task or spike** (`type: task` / `type: spike`): technical work or time-boxed research.
- **Impediment** (`type: impediment`): something blocking the team.

## Estimates and priority

- Story points use Fibonacci labels: `points: 1, 2, 3, 5, 8, 13`. Split anything bigger than 8.
- Priority labels: `priority: high`, `priority: medium`, `priority: low`.

## Definition of Ready

- Clear title and description; stories have acceptance criteria and a "How to verify"
- Estimated (`points:` label) and prioritised
- No unresolved `needs: clarification`

## Definition of Done

- Acceptance criteria met and verified
- Code reviewed and merged; CI green
- Tests added or updated
- Docs updated if behaviour changed
- Issue closed

## AI Scrum Master

- Runs daily (see `.github/workflows/sprint-agent.yml`) and on demand from the web app.
- Reports progress, blocked, unassigned and unestimated work, WIP overload and stale issues.
- Dry run by default; with apply on, it labels stale issues and comments asking the assignee for an update.
- Settings live in `.github/scrum-agent.yml`.
"""

VELOCITY_DOC = """# Velocity

Update at each sprint review. Points come from the `points:` labels on issues closed in the sprint.

| Sprint | Dates | Goal | Planned pts | Done pts | Carry-over | Notes |
|---|---|---|---|---|---|---|
| Sprint 1 | | | | | | |
"""

SPRINT_LOG_TEMPLATE = """# Sprint N log

- **Dates:** YYYY-MM-DD → YYYY-MM-DD
- **Milestone:** [Sprint N](../../milestones)
- **Sprint goal:**
- **Planned:** N issues / N points

## Daily notes
### YYYY-MM-DD
- Completed:
- In progress:
- Blockers:

## Review
- Done:
- Not done (carried over):

## Retrospective
- Keep:
- Problem:
- Try:
"""

FILES: dict[str, str] = {
    ".github/ISSUE_TEMPLATE/story.yml": STORY_FORM,
    ".github/ISSUE_TEMPLATE/bug.yml": BUG_FORM,
    ".github/ISSUE_TEMPLATE/task.yml": TASK_FORM,
    ".github/ISSUE_TEMPLATE/epic.yml": EPIC_FORM,
    ".github/ISSUE_TEMPLATE/impediment.yml": IMPEDIMENT_FORM,
    ".github/ISSUE_TEMPLATE/config.yml": TEMPLATE_CONFIG,
    ".github/pull_request_template.md": PR_TEMPLATE,
    "docs/scrum/WORKFLOW.md": WORKFLOW_DOC,
    "docs/sprints/velocity.md": VELOCITY_DOC,
    "docs/sprints/sprint-template.md": SPRINT_LOG_TEMPLATE,
}
