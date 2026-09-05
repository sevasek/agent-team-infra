"""repo-pull / repo-push / knowledge-commit -- the manual git helpers an
agent calls mid-session to sync or publish a change to a repo it has
write access to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from . import git_ops


def repo_pull(repos_dir: Path, repo_name: str) -> Tuple[bool, str]:
    repo_dir = repos_dir / repo_name
    if not (repo_dir / ".git").is_dir():
        return False, f"Unknown repo: {repo_name}"
    git_ops.git(repo_dir, "fetch", "--quiet", check=False)
    git_ops.git(repo_dir, "reset", "--hard", "origin/main", "--quiet", check=False)
    return True, f"{repo_name}: up to date."


def repo_push(repos_dir: Path, repo_name: str, message: str = "knowledge: update") -> Tuple[bool, str]:
    """Commit + pull-rebase + push. Never force-pushes: if the rebase
    conflicts (a concurrent push landed first), abort and report -- the
    commit stays local-only for a human to resolve, rather than risk
    clobbering someone else's write.
    """
    repo_dir = repos_dir / repo_name
    if not (repo_dir / ".git").is_dir():
        return False, f"Unknown repo: {repo_name}"

    git_ops.git(repo_dir, "add", "-A", check=False)
    if git_ops.git(repo_dir, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return True, f"No changes to commit in {repo_name}."

    git_ops.git(repo_dir, "commit", "-m", message, check=False)

    rebase = git_ops.git(repo_dir, "pull", "--rebase", "--quiet", check=False)
    if rebase.returncode != 0:
        git_ops.git(repo_dir, "rebase", "--abort", check=False)
        return False, (
            f"CONFLICT: rebase failed for {repo_name}. "
            "Commit is local only — resolve manually or notify the owner."
        )

    git_ops.git(repo_dir, "push", check=False)
    return True, f"Pushed to {repo_name}."


def knowledge_commit(knowledge_dir: Path, message: str = "knowledge: update") -> Tuple[bool, str]:
    """Commit + push the agent's own knowledge repo directly (no
    rebase step -- an agent's own knowledge repo has exactly one writer,
    so there's nothing to conflict with)."""
    git_ops.git(knowledge_dir, "add", "-A", check=False)
    if git_ops.git(knowledge_dir, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return True, "No changes to commit."

    git_ops.git(knowledge_dir, "commit", "-m", message, check=False)
    git_ops.git(knowledge_dir, "push", check=False)
    return True, "Changes committed and pushed to GitHub."
