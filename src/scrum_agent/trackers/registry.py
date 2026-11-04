"""Tracker registry: map a provider name to its implementation.

To add Jira later:
  1. implement ``JiraTracker(TrackerProvider)`` in ``trackers/jira.py``
  2. add a factory below, e.g. ``"jira": lambda c: JiraTracker(c["url"], c["email"], c["token"])``
Nothing else in the agent needs to change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import TrackerProvider
from .github import GitHubTracker

_FACTORIES: dict[str, Callable[[dict[str, Any]], TrackerProvider]] = {
    "github": lambda c: GitHubTracker(c["token"], c.get("base_url")),
}

PLANNED = ("jira", "linear")


def available() -> list[str]:
    return sorted(_FACTORIES)


def register(name: str, factory: Callable[[dict[str, Any]], TrackerProvider]) -> None:
    _FACTORIES[name] = factory


def create(name: str, credentials: dict[str, Any]) -> TrackerProvider:
    if name in _FACTORIES:
        return _FACTORIES[name](credentials)
    if name in PLANNED:
        raise NotImplementedError(f"The {name!r} tracker is planned but not implemented yet.")
    raise ValueError(f"Unknown tracker {name!r}. Available: {', '.join(available())}")
