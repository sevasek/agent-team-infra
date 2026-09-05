"""Regression guard for the 2026-09-04 SOUL.md live-copy bug. This is the
same test shape as comms-agent's tests/test_soul_md_safety.py, but against
the actual Python function now instead of extracting a shell heredoc --
the whole point of extracting this package is that there's exactly one
implementation left to test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_team_infra.knowledge_pull import apply_soul_at_boot, knowledge_pull


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def synced_repo(tmp_path):
    """A hermes_home with a knowledge/ checkout tracking a real origin
    whose SOUL.md/MEMORY.md differ from what's currently "running"."""
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    knowledge_dir = hermes_home / "knowledge"

    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-q", str(origin)], cwd=tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(["init", "-q", "."], cwd=seed)
    _git(["config", "user.email", "t@t"], cwd=seed)
    _git(["config", "user.name", "t"], cwd=seed)
    (seed / "SOUL.md").write_text("NEW SOUL — from repo\n")
    (seed / "MEMORY.md").write_text("NEW MEMORY — from repo\n")
    _git(["add", "-A"], cwd=seed)
    _git(["commit", "-q", "-m", "seed"], cwd=seed)
    _git(["remote", "add", "origin", str(origin)], cwd=seed)
    _git(["push", "-q", "origin", "HEAD:main"], cwd=seed)

    subprocess.run(["git", "clone", "-q", str(origin), str(knowledge_dir)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=knowledge_dir)

    (hermes_home / "SOUL.md").write_text("OLD SOUL — currently running\n")
    (hermes_home / "MEMORY.md").write_text("OLD MEMORY — currently running\n")

    return hermes_home, knowledge_dir


def test_never_overwrites_running_soul(synced_repo):
    hermes_home, _ = synced_repo
    knowledge_pull(hermes_home)
    assert (hermes_home / "SOUL.md").read_text() == "OLD SOUL — currently running\n", (
        "knowledge_pull overwrote the running SOUL.md live — this is exactly "
        "the 2026-09-04 bug. SOUL.md must only be applied at container start."
    )


def test_still_syncs_memory_live(synced_repo):
    hermes_home, _ = synced_repo
    knowledge_pull(hermes_home)
    assert (hermes_home / "MEMORY.md").read_text() == "NEW MEMORY — from repo\n"


def test_notifies_once_per_soul_version(synced_repo):
    hermes_home, _ = synced_repo
    sent = []

    import agent_team_infra.knowledge_pull as kp_module

    def fake_send(bot_token, chat_id, text):
        sent.append(text)
        return True

    kp_module.send_telegram = fake_send

    result1 = knowledge_pull(hermes_home, bot_token="tok", owner_id="123")
    assert "SOUL.md changed upstream" in result1
    assert len(sent) == 1

    result2 = knowledge_pull(hermes_home, bot_token="tok", owner_id="123")
    assert "SOUL.md changed upstream" not in result2
    assert len(sent) == 1, "should not re-notify for a version already flagged"


def test_apply_soul_at_boot_does_apply_it(synced_repo):
    """The one place SOUL.md IS applied -- container start, before Hermes
    has loaded anything into a live session."""
    hermes_home, knowledge_dir = synced_repo
    apply_soul_at_boot(hermes_home, knowledge_dir)
    assert (hermes_home / "SOUL.md").read_text() == "NEW SOUL — from repo\n"
    assert not (hermes_home / ".soul-notified-hash").exists()


def test_auto_commit_pending_changes_before_pull(tmp_path):
    """A knowledge-provisioner agent sometimes edits its own knowledge dir
    directly mid-session -- those must be committed and pushed, not
    silently discarded by the reset --hard that follows."""
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    knowledge_dir = hermes_home / "knowledge"

    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-q", str(origin)], cwd=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(["init", "-q", "."], cwd=seed)
    _git(["config", "user.email", "t@t"], cwd=seed)
    _git(["config", "user.name", "t"], cwd=seed)
    (seed / "org.md").write_text("v1\n")
    _git(["add", "-A"], cwd=seed)
    _git(["commit", "-q", "-m", "seed"], cwd=seed)
    _git(["remote", "add", "origin", str(origin)], cwd=seed)
    _git(["push", "-q", "origin", "HEAD:main"], cwd=seed)

    subprocess.run(["git", "clone", "-q", str(origin), str(knowledge_dir)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=knowledge_dir)
    _git(["config", "user.email", "agent-a@hermes.local"], cwd=knowledge_dir)
    _git(["config", "user.name", "Agent A"], cwd=knowledge_dir)

    # Simulate an uncommitted edit made directly in the knowledge dir.
    (knowledge_dir / "org.md").write_text("v2 — edited mid-session\n")

    knowledge_pull(hermes_home, knowledge_dir=knowledge_dir, auto_commit_pending=True)

    # It should have been committed and pushed, not discarded.
    result = subprocess.run(
        ["git", "show", "origin/main:org.md"], cwd=str(knowledge_dir), capture_output=True, text=True, check=True
    )
    assert result.stdout == "v2 — edited mid-session\n"
