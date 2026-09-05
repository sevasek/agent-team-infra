"""The safety-critical sync: pull an agent's own knowledge repo and apply
only the parts that are safe to change live.

History matters here. On 2026-09-04 this exact logic -- duplicated
between two entrypoint.sh files -- was found live-copying SOUL.md onto
the running agent every 30 minutes, with no restart and no warning,
because one copy got a safety fix and the other didn't. That is the
whole reason this lives in one tested package instead of N duplicated
shell heredocs.

SOUL.md is NEVER copied here. It is only ever applied at container start
(see `apply_soul_at_boot` below), the one point where doing so can't yank
instructions out from under a live session. This function's job is to
notice when SOUL.md has drifted from what's running and say so -- once
per changed version, not on every tick -- never to apply it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from . import git_ops
from .notify import send_telegram


def apply_soul_at_boot(hermes_home: Path, knowledge_dir: Path) -> None:
    """Call once, at container start only. Copies SOUL.md and MEMORY.md
    from the knowledge repo onto the live paths, and clears any pending
    SOUL-changed notification -- whatever's in the repo right now is what
    Hermes is about to load, so there's nothing left to notify about.
    """
    soul_src = knowledge_dir / "SOUL.md"
    memory_src = knowledge_dir / "MEMORY.md"
    if soul_src.is_file():
        shutil.copyfile(soul_src, hermes_home / "SOUL.md")
    if memory_src.is_file():
        shutil.copyfile(memory_src, hermes_home / "MEMORY.md")
    notified_file = hermes_home / ".soul-notified-hash"
    notified_file.unlink(missing_ok=True)


def knowledge_pull(
    hermes_home: Path,
    knowledge_dir: Optional[Path] = None,
    auto_commit_pending: bool = False,
    bot_token: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> str:
    """Sync the knowledge repo and apply the live-safe parts. Returns a
    human-readable status line, same shape as the old shell scripts
    printed, so callers/logs read the same as before.

    auto_commit_pending: Riker sometimes writes into his own knowledge
    dir directly (e.g. an org-map edit mid-session) -- set True to
    auto-commit and push any such pending changes before pulling, so a
    stray uncommitted edit can't be silently discarded by the reset that
    follows. The generic per-client agent has no such write path, so it
    defaults off.
    """
    knowledge_dir = knowledge_dir or (hermes_home / "knowledge")
    notified_file = hermes_home / ".soul-notified-hash"

    if auto_commit_pending:
        git_ops.git(knowledge_dir, "add", "-A", check=False)
        if git_ops.git(knowledge_dir, "diff", "--cached", "--quiet", check=False).returncode != 0:
            git_ops.git(knowledge_dir, "commit", "-m", "auto: commit pending changes before pull", check=False)
        git_ops.git(knowledge_dir, "push", check=False)

    git_ops.git(knowledge_dir, "fetch", "--quiet", check=False)
    git_ops.git(knowledge_dir, "reset", "--hard", "origin/main", "--quiet", check=False)

    memory_src = knowledge_dir / "MEMORY.md"
    if memory_src.is_file():
        shutil.copyfile(memory_src, hermes_home / "MEMORY.md")

    lines = ["Knowledge updated."]

    repo_hash = git_ops.md5_of(knowledge_dir / "SOUL.md")
    running_hash = git_ops.md5_of(hermes_home / "SOUL.md")
    if repo_hash is not None and running_hash is not None and repo_hash != running_hash:
        already_notified = notified_file.read_text().strip() if notified_file.is_file() else ""
        if already_notified != repo_hash:
            lines.append("SOUL.md changed upstream — restart required for new instructions to take effect.")
            if bot_token and owner_id:
                send_telegram(
                    bot_token,
                    owner_id,
                    "⚠️ SOUL.md changed upstream. Send /restart when ready to apply the new instructions.",
                )
            notified_file.write_text(repo_hash)

    return "\n".join(lines)
