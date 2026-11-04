# AI Scrum Master

An AI Scrum Master and project manager agent that runs on **GitHub Issues**. It works with **any GitHub account and any repository** that account can reach: milestones are sprints, labels are board columns.

It audits a sprint and reports on:
- **Progress:** percent done and days left.
- **Stale work:** issues idle longer than 48 hours by default.
- **Untracked work:** blocked, unassigned and unestimated issues.
- **Overload:** people over their WIP limit.
- **Delivery risk:** an overall risk rating for the sprint.

It can also nudge stale issues with a polite comment and a `status: stale` label.

There are three ways to run it, all on the same engine:

| | For | Login |
|---|---|---|
| **Web app** | Interactive: pick a repo and sprint, review, then apply | Sign in with GitHub (OAuth) or a personal access token |
| **CLI** | Local use and scripts | `scrum-agent login` (token or browser) |
| **GitHub Action** | Daily scheduled audits | Repo's `GITHUB_TOKEN` or a PAT secret |

**Safe by default:** every run is a **dry run** unless you pass `--apply` or tick *Apply actions*.

---

## How it works

```
load ─► analyze ─► review (LLM) ─► validate ─┬─► act ─► report ─► publish
                     ▲                        │
                     └──── retry ≤1 ──────────┘
```

- **load:** fetches the milestone's issues. It also reads the repo's `.claude/CLAUDE.md`, `CLAUDE.md` or `AGENTS.md` as project rules, and `.github/scrum-agent.yml` as config.
- **analyze:** deterministic checks with no LLM. These produce the *stale candidates*.
- **review:** the LLM (Claude by default) writes the narrative report and tailored nudges, returning structured output. For providers without tool calling, it falls back to parsing a `STUCK: #12, #34` line.
- **validate:** the LLM may only flag issues that are in the deterministic candidate list. If it cites any other issue, the graph loops back once with a correction. This keeps hallucinated issue numbers from being touched.
- **act:** labels and comments on flagged issues, skipping any issue that was already nudged with no reply since.
- **report / publish:** Markdown report. Optionally, it keeps a `Sprint report: <milestone>` issue up to date.

If no LLM key is set, or the model call fails, it runs **rules-only** and still produces a full report.

## Quick start (CLI)

```bash
pip install -e ".[web,openai]"           # Python 3.11+
scrum-agent login                        # paste a token (or: --web for browser login)
export ANTHROPIC_API_KEY=sk-ant-...      # optional; omit for rules-only

scrum-agent repos                        # repos you can audit
scrum-agent sprints acme/web             # open milestones (* = default)
scrum-agent audit acme/web               # dry run on the nearest-due milestone
scrum-agent audit acme/web -s "Sprint 14" --apply --post-report
```

Other useful flags:
- `--no-llm`: skip the model and run the deterministic checks only.
- `--model openai:gpt-4o`: use a different model.
- `--json`: print a JSON summary instead of Markdown.
- `-o report.md`: also write the report to a file.

**Token permissions.** Either token type works:
- **Classic token:** the `repo` scope.
- **Fine-grained token:** *Issues* read/write, *Contents* read, *Metadata* read.

**Login details:**
- Credentials are stored in `~/.config/scrum-agent/credentials.json` with mode 0600.
- `GITHUB_TOKEN` or `GH_TOKEN`, if set, take precedence over the saved login.
- For **GitHub Enterprise**, use `scrum-agent login --base-url https://ghe.example.com/api/v3`.

## Web app

```bash
cp .env.example .env    # fill in values, then export them
scrum-agent serve       # http://127.0.0.1:8000
# or: docker build -t scrum-agent . && docker run --env-file .env -p 8000:8000 scrum-agent
```

**Sign in with GitHub.** Create an OAuth App under GitHub → Settings → Developer settings → OAuth Apps:
- Set the callback URL to `$PUBLIC_URL/auth/callback`.
- Put the app's client ID and secret in `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET`.
- Tick *Enable Device Flow* if you also want `scrum-agent login --web` to work.

**Token login.** A personal-access-token form is shown by default. Set `ALLOW_TOKEN_LOGIN=false` to hide it.

**Using the app:** pick a repo, pick a milestone, then run the audit. Results open as a dry run with an *Apply N nudges* button.

**Security notes:**
- Tokens live in server memory only; the cookie holds just a random session ID.
- Forms are CSRF-protected.
- Untrusted issue text is escaped, and unsafe links are stripped from the rendered report.
- Run a single worker, or replace `SessionStore` with Redis to scale out.

## GitHub Action

`.github/workflows/sprint-agent.yml` runs weekdays at 13:07 UTC, and you can also start it manually.

**Default behaviour.** It audits *this* repository as a dry run, writes the report to the job summary and uploads it as an artifact.

**Repository variables:**

| Variable | Effect |
|---|---|
| `SCRUM_AGENT_APPLY=true` | Scheduled runs label and comment |
| `SCRUM_AGENT_POST_REPORT=true` | Keep the report issue updated |
| `SCRUM_AGENT_REPOS=["acme/web","acme/api"]` | Audit several repos; also needs a `SCRUM_AGENT_TOKEN` secret with access to them |
| `SCRUM_AGENT_MODEL` | For example `openai:gpt-4o` |

**Secrets:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. Without either, the audit runs rules-only.

**Other repositories.** To audit a repo on its own, without copying this code, drop [`examples/sprint-agent-consumer.yml`](examples/sprint-agent-consumer.yml) into its `.github/workflows/`.

## Per-repo configuration

Put a `.github/scrum-agent.yml` in any audited repo; all keys are optional. See [`examples/scrum-agent.yml`](examples/scrum-agent.yml). Highlights:

- `stale_hours`: default 48.
- `stale_scope`: sets which open issues can be marked stale.
  - `in_progress` (default) covers issues that are assigned or carry an in-progress label.
  - `all_open` covers every open issue in the sprint.
- `exempt_labels`: issues with these labels are never nudged. Default: `status: blocked`, `on-hold`.
- `estimate_label_prefixes`: labels that count as an estimate. Default: `points:`, `size:`, `estimate:`, `sp:`.
- `llm_model`: any LangChain `provider:model` string. Default: `anthropic:claude-sonnet-5-5`.

Environment overrides: `SCRUM_AGENT_MODEL`, `SCRUM_AGENT_STALE_HOURS`, `SCRUM_AGENT_STALE_SCOPE`, `SCRUM_AGENT_LLM_ENABLED`.

## Extending to Jira (and others)

All logic talks to `TrackerProvider` (`src/scrum_agent/trackers/base.py`), never to GitHub directly. To add Jira:

1. Implement `JiraTracker(TrackerProvider)` in `trackers/jira.py`:
   - Sprints come from the Agile API.
   - Issues come from JQL `sprint = <id>`.
   - Labels and comments come from the REST API.
2. Register it in `trackers/registry.py`.
3. Add a `--tracker jira` option to the CLI and a sign-in option to the web app.

The analysis, LLM review, guard rails, report, CLI audit and web result pages stay the same.

## Development

```bash
pip install -e ".[web,openai,dev]"
pytest -q
```

The tests use an in-memory fake tracker and a fake LLM. They cover:
- the deterministic checks;
- dry run vs apply, and idempotent nudges;
- the LLM guard rail and its retry;
- rules-only fallback;
- the CLI login file (mode 0600);
- the web flow: login, CSRF and XSS escaping.

## Project layout

```
src/scrum_agent/
  trackers/   base.py (interface) · github.py · registry.py
  analysis.py  deterministic sprint health
  llm.py       prompts, structured review, STUCK-line parser
  actions.py   idempotent label + comment (also exposed as LangChain tools)
  graph.py     LangGraph workflow
  report.py    Markdown report
  service.py   config resolution + audit entry point
  auth.py      token store, OAuth web + device flows
  cli.py       `scrum-agent` CLI
  web/         FastAPI app, templates, CSS
```
