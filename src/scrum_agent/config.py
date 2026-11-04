"""Agent configuration.

Resolution order (later wins):
  1. built-in defaults
  2. a YAML file (``--config path`` or ``.github/scrum-agent.yml`` in the audited repo)
  3. environment variables (``SCRUM_AGENT_*``)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MODEL = "anthropic:claude-sonnet-5-5"
REPO_CONFIG_PATH = ".github/scrum-agent.yml"


@dataclass
class AgentConfig:
    # Discipline rules
    stale_hours: int = 48
    #: "in_progress" = open issues that are assigned or carry an in-progress label
    #: "all_open"    = every open issue in the sprint
    stale_scope: str = "in_progress"
    stale_label: str = "status: stale"
    in_progress_labels: list[str] = field(default_factory=lambda: ["status: in-progress", "status: in-review"])
    blocked_labels: list[str] = field(default_factory=lambda: ["status: blocked"])
    #: issues with any of these labels are never nudged
    exempt_labels: list[str] = field(default_factory=lambda: ["status: blocked", "on-hold"])
    #: board columns, in order, for the status breakdown (no label = Backlog)
    status_columns: list[str] = field(
        default_factory=lambda: ["status: ready", "status: in-progress", "status: in-review"]
    )
    #: issues with these labels are not expected to carry an estimate
    no_estimate_labels: list[str] = field(default_factory=lambda: ["type: epic"])
    estimate_label_prefixes: list[str] = field(
        default_factory=lambda: ["points:", "size:", "estimate:", "sp:"]
    )
    wip_limit_per_person: int = 3

    # LLM
    llm_model: str = DEFAULT_MODEL  # "provider:model", e.g. "openai:gpt-4o"
    llm_enabled: bool = True
    llm_temperature: float = 0.0

    # Output
    post_report: bool = False  # create/update a "Sprint report: <milestone>" issue

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AgentConfig:
        data = data or {}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")
        return cls(**data)

    @classmethod
    def from_yaml_text(cls, text: str) -> AgentConfig:
        return cls.from_dict(yaml.safe_load(text) or {})

    @classmethod
    def load(cls, path: str | Path | None = None, yaml_text: str | None = None) -> AgentConfig:
        if path:
            cfg = cls.from_yaml_text(Path(path).read_text())
        elif yaml_text:
            cfg = cls.from_yaml_text(yaml_text)
        else:
            cfg = cls()
        return cfg.with_env_overrides()

    def with_env_overrides(self, env: dict[str, str] | None = None) -> AgentConfig:
        env = os.environ if env is None else env
        if v := env.get("SCRUM_AGENT_MODEL"):
            self.llm_model = v
        if v := env.get("SCRUM_AGENT_STALE_HOURS"):
            self.stale_hours = int(v)
        if v := env.get("SCRUM_AGENT_STALE_SCOPE"):
            self.stale_scope = v
        if (v := env.get("SCRUM_AGENT_LLM_ENABLED")) is not None:
            self.llm_enabled = v.lower() not in ("0", "false", "no", "off")
        self.validate()
        return self

    def validate(self) -> None:
        if self.stale_scope not in ("in_progress", "all_open"):
            raise ValueError("stale_scope must be 'in_progress' or 'all_open'")
        if self.stale_hours < 1:
            raise ValueError("stale_hours must be >= 1")
        if ":" not in self.llm_model:
            raise ValueError("llm_model must look like 'provider:model', e.g. 'anthropic:claude-sonnet-5-5'")
