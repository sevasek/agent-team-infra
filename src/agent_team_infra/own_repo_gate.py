"""Decide whether a push into an agent's OWN repo warrants a full wake
(invoke the LLM) or just the routine `knowledge_pull` refresh.

This is deliberately not the source-repo gate (`source_repo_gate.py`'s
job) -- when an agent watches an external source repo it doesn't own,
the content is raw and unvetted, and deciding what it means is real
agentic work. But when a knowledge-provisioner agent commits into
another agent's OWN repo, that content already went through the full
approval flow before it was committed -- there's nothing left to
interpret, just knowledge to reload. The one exception
is a *task* file: a new or updated task needs someone to act on it or
schedule acting on it, which a silent refresh doesn't accomplish. So the
decision is made by which file changed, not by who pushed it:

  - a commit touches a designated task file  -> "wake"
  - anything else (company/*, MEMORY.md, ...) -> "refresh"

Self-authored pushes (the agent's own status-flip edit to its own task
file) still classify as "wake" by this rule alone -- see
`is_self_authored` for the separate, optional check a caller can use to
skip a *redundant* wake, since the agent that just made the edit is
already active. That's an efficiency optimization, not a safety one:
unlike the source-repo self-trigger guard, there's no risk here, only
wasted cost.
"""

from __future__ import annotations

from typing import Iterable, Optional


def _changed_files(job: dict) -> set:
    files = set()
    for commit in job.get("commits", []):
        files.update(commit.get("added", []))
        files.update(commit.get("removed", []))
        files.update(commit.get("modified", []))
    return files


def is_self_authored(job: dict, identity_email: str) -> bool:
    """True if every commit in the push was authored by this identity --
    i.e. the watching agent's own edit, not something to react to."""
    commits = job.get("commits", [])
    if not commits:
        return False
    return all(c.get("author", {}).get("email") == identity_email for c in commits)


def classify(job: dict, task_file_paths: Iterable[str]) -> str:
    """Returns "wake" or "refresh"."""
    task_file_paths = set(task_file_paths)
    if _changed_files(job) & task_file_paths:
        return "wake"
    return "refresh"
