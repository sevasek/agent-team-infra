from __future__ import annotations

import json
import sys
from io import StringIO

from agent_team_infra import riker_job_gate


def _run_main(monkeypatch, jobs_dir, hermes_home):
    monkeypatch.setattr(riker_job_gate, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(riker_job_gate, "HERMES_HOME", hermes_home)
    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    riker_job_gate.main()
    return captured.getvalue()


def test_no_jobs_dir_does_not_wake(monkeypatch, tmp_path):
    output = _run_main(monkeypatch, tmp_path / "does-not-exist", tmp_path)
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}


def test_empty_jobs_dir_does_not_wake(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    output = _run_main(monkeypatch, jobs_dir, tmp_path)
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}


def test_pending_job_wakes_and_no_longer_carries_diff(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job = {
        "id": "sevasek-sevasek-business-abc123-1",
        "repo": "sevasek/sevasek-business",
        "before": "aaa",
        "after": "bbb",
        "pusher": "sevasek",
        "commits": [{"message": "update pricing", "author": {"email": "sevasek@gmail.com"}}],
        "received_at": "2026-09-05T00:00:00Z",
    }
    (jobs_dir / "job1.json").write_text(json.dumps(job))

    output = _run_main(monkeypatch, jobs_dir, tmp_path)

    assert "sevasek/sevasek-business" in output
    assert "update pricing" in output
    assert "Fetch the diff yourself" in output
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": True}


def test_processed_job_is_moved_not_reprocessed(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job = {"id": "x", "repo": "a/b", "commits": []}
    (jobs_dir / "job1.json").write_text(json.dumps(job))

    _run_main(monkeypatch, jobs_dir, tmp_path)

    assert not (jobs_dir / "job1.json").exists()
    assert (jobs_dir / "processed" / "job1.json").exists()

    # Second run: nothing pending.
    output = _run_main(monkeypatch, jobs_dir, tmp_path)
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}


def test_malformed_job_does_not_crash_and_does_not_wake(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "bad.json").write_text("{not valid json")

    output = _run_main(monkeypatch, jobs_dir, tmp_path)
    assert json.loads(output.strip().splitlines()[-1]) == {"wakeAgent": False}
