from __future__ import annotations

import subprocess

from agent_team_infra import repo_ops


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _make_repo_pair(tmp_path, name="myrepo"):
    origin = tmp_path / f"{name}.git"
    _git(["init", "--bare", "-q", str(origin)], cwd=tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(["init", "-q", "."], cwd=seed)
    _git(["config", "user.email", "t@t"], cwd=seed)
    _git(["config", "user.name", "t"], cwd=seed)
    (seed / "file.md").write_text("v1\n")
    _git(["add", "-A"], cwd=seed)
    _git(["commit", "-q", "-m", "seed"], cwd=seed)
    _git(["remote", "add", "origin", str(origin)], cwd=seed)
    _git(["push", "-q", "origin", "HEAD:main"], cwd=seed)

    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    clone_dir = repos_dir / name
    subprocess.run(["git", "clone", "-q", str(origin), str(clone_dir)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=clone_dir)
    _git(["config", "user.email", "agent@hermes.local"], cwd=clone_dir)
    _git(["config", "user.name", "Agent"], cwd=clone_dir)
    return repos_dir, origin


def test_repo_pull_unknown_repo(tmp_path):
    ok, message = repo_ops.repo_pull(tmp_path, "does-not-exist")
    assert not ok
    assert "Unknown repo" in message


def test_repo_pull_fetches_upstream_changes(tmp_path):
    repos_dir, origin = _make_repo_pair(tmp_path)

    # Push a change from elsewhere.
    other_clone = tmp_path / "other-clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(other_clone)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=other_clone)
    _git(["config", "user.email", "t@t"], cwd=other_clone)
    _git(["config", "user.name", "t"], cwd=other_clone)
    (other_clone / "file.md").write_text("v2\n")
    _git(["add", "-A"], cwd=other_clone)
    _git(["commit", "-q", "-m", "update"], cwd=other_clone)
    _git(["push", "-q"], cwd=other_clone)

    ok, message = repo_ops.repo_pull(repos_dir, "myrepo")
    assert ok
    assert "up to date" in message
    assert (repos_dir / "myrepo" / "file.md").read_text() == "v2\n"


def test_repo_push_no_changes(tmp_path):
    repos_dir, _ = _make_repo_pair(tmp_path)
    ok, message = repo_ops.repo_push(repos_dir, "myrepo")
    assert ok
    assert "No changes to commit" in message


def test_repo_push_commits_and_pushes(tmp_path):
    repos_dir, origin = _make_repo_pair(tmp_path)
    (repos_dir / "myrepo" / "file.md").write_text("v2 — local edit\n")

    ok, message = repo_ops.repo_push(repos_dir, "myrepo", "test: edit")
    assert ok
    assert "Pushed to myrepo" in message

    result = subprocess.run(
        ["git", "show", "HEAD:file.md"], cwd=str(repos_dir / "myrepo"), capture_output=True, text=True, check=True
    )
    assert result.stdout == "v2 — local edit\n"


def test_repo_push_never_force_pushes_on_conflict(tmp_path):
    repos_dir, origin = _make_repo_pair(tmp_path)

    # A concurrent push lands first.
    other_clone = tmp_path / "other-clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(other_clone)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=other_clone)
    _git(["config", "user.email", "t@t"], cwd=other_clone)
    _git(["config", "user.name", "t"], cwd=other_clone)
    (other_clone / "file.md").write_text("v2 — from elsewhere\n")
    _git(["add", "-A"], cwd=other_clone)
    _git(["commit", "-q", "-m", "concurrent"], cwd=other_clone)
    _git(["push", "-q"], cwd=other_clone)

    # Our local clone edits the same line without knowing about that push.
    (repos_dir / "myrepo" / "file.md").write_text("v2 — our conflicting edit\n")

    ok, message = repo_ops.repo_push(repos_dir, "myrepo", "test: conflicting edit")
    assert not ok
    assert "CONFLICT" in message

    # The remote still has the other push's content -- nothing was force-pushed over it.
    result = subprocess.run(
        ["git", "show", "origin/main:file.md"], cwd=str(repos_dir / "myrepo"), capture_output=True, text=True, check=True
    )
    assert result.stdout == "v2 — from elsewhere\n"


def test_knowledge_commit_pushes_directly(tmp_path):
    origin = tmp_path / "knowledge.git"
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

    knowledge_dir = tmp_path / "knowledge"
    subprocess.run(["git", "clone", "-q", str(origin), str(knowledge_dir)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=knowledge_dir)
    _git(["config", "user.email", "riker@hermes.local"], cwd=knowledge_dir)
    _git(["config", "user.name", "William Riker"], cwd=knowledge_dir)

    (knowledge_dir / "org.md").write_text("v2\n")
    ok, message = repo_ops.knowledge_commit(knowledge_dir, "org: update")
    assert ok
    assert "committed and pushed" in message

    result = subprocess.run(
        ["git", "show", "origin/main:org.md"], cwd=str(knowledge_dir), capture_output=True, text=True, check=True
    )
    assert result.stdout == "v2\n"
