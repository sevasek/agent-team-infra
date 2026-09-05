from __future__ import annotations

import json
import time

from agent_team_infra.gate import AuditLog, JobQueue


def test_audit_log_appends(tmp_path):
    log = AuditLog(tmp_path / "gate.log")
    log.write("SILENT (no jobs)")
    log.write("WAKE job=1")
    content = (tmp_path / "gate.log").read_text()
    assert "SILENT (no jobs)" in content
    assert "WAKE job=1" in content


def test_audit_log_rotates_at_max_lines(tmp_path):
    log = AuditLog(tmp_path / "gate.log", max_lines=3)
    for i in range(5):
        log.write(f"entry {i}")
    lines = (tmp_path / "gate.log").read_text().splitlines()
    assert len(lines) == 3
    assert "entry 4" in lines[-1]
    assert "entry 0" not in "".join(lines)


def test_audit_log_never_raises_on_bad_path(tmp_path):
    # log_path's parent is a file, not a directory -- mkdir(parents=True) will fail.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    log = AuditLog(blocker / "gate.log")
    log.write("should not raise")  # must not raise


def test_job_queue_empty_returns_no_jobs(tmp_path):
    queue = JobQueue(tmp_path / "jobs")
    assert queue.pending() == []


def test_job_queue_lists_oldest_first(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "b.json").write_text("{}")
    time.sleep(0.01)
    (jobs_dir / "a.json").write_text("{}")

    queue = JobQueue(jobs_dir)
    pending = queue.pending()
    assert [p.name for p in pending] == ["b.json", "a.json"]


def test_job_queue_ignores_non_json_files(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "job.json").write_text("{}")
    (jobs_dir / "readme.txt").write_text("not a job")

    queue = JobQueue(jobs_dir)
    assert [p.name for p in queue.pending()] == ["job.json"]


def test_mark_processed_moves_job_and_prevents_double_processing(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    job_file = jobs_dir / "job.json"
    job_file.write_text(json.dumps({"id": "1"}))

    queue = JobQueue(jobs_dir)
    destination = queue.mark_processed(job_file)

    assert not job_file.exists()
    assert destination.exists()
    assert queue.pending() == []


def test_prune_processed_removes_old_but_not_recent(tmp_path):
    jobs_dir = tmp_path / "jobs"
    processed = jobs_dir / "processed"
    processed.mkdir(parents=True)
    old_file = processed / "old.json"
    recent_file = processed / "recent.json"
    old_file.write_text("{}")
    recent_file.write_text("{}")

    import os

    old_time = time.time() - 8 * 86400
    os.utime(old_file, (old_time, old_time))

    queue = JobQueue(jobs_dir, retain_days=7)
    queue.prune_processed()

    assert not old_file.exists()
    assert recent_file.exists()
