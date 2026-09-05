from __future__ import annotations

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

from agent_team_infra import own_repo_gate_cli


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _setup_hermes_home(tmp_path):
    """A hermes_home with a knowledge/ checkout tracking a real origin,
    for exercising the refresh path's real knowledge_pull call."""
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
    (seed / "MEMORY.md").write_text("NEW MEMORY\n")
    _git(["add", "-A"], cwd=seed)
    _git(["commit", "-q", "-m", "seed"], cwd=seed)
    _git(["remote", "add", "origin", str(origin)], cwd=seed)
    _git(["push", "-q", "origin", "HEAD:main"], cwd=seed)

    subprocess.run(["git", "clone", "-q", str(origin), str(knowledge_dir)], check=True, capture_output=True)
    _git(["checkout", "-q", "main"], cwd=knowledge_dir)
    (hermes_home / "MEMORY.md").write_text("OLD MEMORY\n")

    return hermes_home


def _run_main(monkeypatch, hermes_home, jobs_dir, task_file_paths="project-tasks.md", identity_email=None):
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("OWN_REPO_JOBS_DIR", str(jobs_dir))
    monkeypatch.setenv("TASK_FILE_PATHS", task_file_paths)
    if identity_email:
        monkeypatch.setenv("AGENT_IDENTITY_EMAIL", identity_email)
    else:
        monkeypatch.delenv("AGENT_IDENTITY_EMAIL", raising=False)
    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    own_repo_gate_cli.main()
    return captured.getvalue()


def _write_job(jobs_dir: Path, **overrides):
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "id": "job1",
        "repo": "sevasek/performance-agent",
        "pusher": "riker",
        "commits": [{"message": "task update", "author": {"email": "riker@hermes.local"}, "modified": ["project-tasks.md"]}],
        "received_at": "2026-09-05T00:00:00Z",
    }
    job.update(overrides)
    (jobs_dir / "job1.json").write_text(json.dumps(job))


def test_no_pending_jobs_no_wake(monkeypatch, tmp_path):
    hermes_home = _setup_hermes_home(tmp_path)
    output = _run_main(monkeypatch, hermes_home, tmp_path / "jobs")
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}


def test_task_file_commit_wakes(monkeypatch, tmp_path):
    hermes_home = _setup_hermes_home(tmp_path)
    jobs_dir = tmp_path / "jobs"
    _write_job(jobs_dir)

    output = _run_main(monkeypatch, hermes_home, jobs_dir)
    assert "task file" in output
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": True}


def test_knowledge_file_commit_only_refreshes(monkeypatch, tmp_path):
    hermes_home = _setup_hermes_home(tmp_path)
    jobs_dir = tmp_path / "jobs"
    _write_job(
        jobs_dir,
        commits=[{"message": "fact update", "author": {"email": "riker@hermes.local"}, "modified": ["company/company.md"]}],
    )

    output = _run_main(monkeypatch, hermes_home, jobs_dir)
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}
    # The refresh actually ran -- MEMORY.md picked up the new content.
    assert (hermes_home / "MEMORY.md").read_text() == "NEW MEMORY\n"


def test_self_authored_task_edit_downgrades_to_refresh(monkeypatch, tmp_path):
    hermes_home = _setup_hermes_home(tmp_path)
    jobs_dir = tmp_path / "jobs"
    _write_job(
        jobs_dir,
        commits=[{"message": "status flip", "author": {"email": "danielle@hermes.local"}, "modified": ["project-tasks.md"]}],
    )

    output = _run_main(monkeypatch, hermes_home, jobs_dir, identity_email="danielle@hermes.local")
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}, (
        "a task-file edit authored entirely by the agent itself should be a "
        "redundant wake, not a real one -- it's already active, it just made this edit"
    )


def test_task_edit_by_someone_else_still_wakes_even_with_identity_set(monkeypatch, tmp_path):
    hermes_home = _setup_hermes_home(tmp_path)
    jobs_dir = tmp_path / "jobs"
    _write_job(jobs_dir)  # authored by riker@hermes.local

    output = _run_main(monkeypatch, hermes_home, jobs_dir, identity_email="danielle@hermes.local")
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": True}


def test_malformed_job_does_not_crash(monkeypatch, tmp_path):
    hermes_home = _setup_hermes_home(tmp_path)
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "bad.json").write_text("{not valid")

    output = _run_main(monkeypatch, hermes_home, jobs_dir)
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}
