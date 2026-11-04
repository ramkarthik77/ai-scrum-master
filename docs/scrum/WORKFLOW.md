# Sprint workflow

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
