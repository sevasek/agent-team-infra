"""Console-script entry points -- these are what an entrypoint.sh or a
Dockerfile actually invokes. Kept as one function per command, matching
the original separate script names, so `pip install agent-team-infra`
is a drop-in replacement for the old heredoc-generated `/opt/data/bin/*`
scripts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import repo_ops
from .knowledge_pull import apply_soul_at_boot, knowledge_pull


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "/opt/data"))


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def cmd_knowledge_pull() -> int:
    hermes_home = _hermes_home()
    result = knowledge_pull(
        hermes_home=hermes_home,
        auto_commit_pending=_env_flag("AGENT_AUTO_COMMIT_PENDING"),
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        owner_id=os.environ.get("TELEGRAM_ALLOWED_USERS"),
    )
    print(result)
    return 0


def cmd_apply_soul_at_boot() -> int:
    hermes_home = _hermes_home()
    apply_soul_at_boot(hermes_home, hermes_home / "knowledge")
    return 0


def cmd_repo_pull() -> int:
    if len(sys.argv) < 2:
        print("Usage: repo-pull <repo-name>", file=sys.stderr)
        return 1
    ok, message = repo_ops.repo_pull(_hermes_home() / "repos", sys.argv[1])
    print(message)
    return 0 if ok else 1


def cmd_repo_push() -> int:
    if len(sys.argv) < 2:
        print("Usage: repo-push <repo-name> [message]", file=sys.stderr)
        return 1
    repo_name = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else "knowledge: update"
    ok, result_message = repo_ops.repo_push(_hermes_home() / "repos", repo_name, message)
    print(result_message)
    return 0 if ok else 1


def cmd_knowledge_commit() -> int:
    message = sys.argv[1] if len(sys.argv) > 1 else "knowledge: update"
    ok, result_message = repo_ops.knowledge_commit(_hermes_home() / "knowledge", message)
    print(result_message)
    return 0 if ok else 1
