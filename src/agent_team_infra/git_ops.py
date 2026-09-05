"""Low-level git subprocess helpers shared by every other module here."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional


def run(args: list, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def git(repo_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(repo_dir), *args], check=check)


def clone_or_pull(repo_dir: Path, clone_url: str) -> None:
    """Clone a repo if it doesn't exist locally, or fetch+hard-reset it to
    origin/main if it does. Never leaves local commits ahead of origin --
    this is a read-through cache of the remote, not a place to develop.
    """
    if (repo_dir / ".git").is_dir():
        git(repo_dir, "remote", "set-url", "origin", clone_url, check=False)
        git(repo_dir, "fetch", "--quiet", check=False)
        git(repo_dir, "reset", "--hard", "origin/main", "--quiet", check=False)
    else:
        repo_dir.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--quiet", clone_url, str(repo_dir)], check=False)
    git(repo_dir, "remote", "set-url", "origin", clone_url, check=False)


def set_identity(repo_dir: Path, name: str, email: str) -> None:
    git(repo_dir, "config", "user.name", name, check=False)
    git(repo_dir, "config", "user.email", email, check=False)


def md5_of(path: Path):
    if not path.is_file():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()
