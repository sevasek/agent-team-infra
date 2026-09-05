"""Shared helpers for cron-gate scripts -- the cheap, zero-token-cost
pre-filters (`riker_job_gate.py`, Willow's `engagement-gate.py`, Joe's
`project-gate.py`, and whatever the next agent needs) that decide whether
to wake an agent's LLM at all, before it's ever invoked.

Every gate needs the same two small things: append-only audit logging
with rotation, and a pending-jobs directory it can list oldest-first and
move entries out of once processed. Extracted here so a fix or a test
lands once, not once per agent's own copy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List


class AuditLog:
    """Append-only log, capped at max_lines (oldest dropped first)."""

    def __init__(self, log_path: Path, max_lines: int = 500):
        self.log_path = log_path
        self.max_lines = max_lines

    def write(self, entry: str) -> None:
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            line = f"{ts} {entry}\n"
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.log_path.exists():
                lines = self.log_path.read_text().splitlines(keepends=True)
                if len(lines) >= self.max_lines:
                    lines = lines[-(self.max_lines - 1):]
                lines.append(line)
                self.log_path.write_text("".join(lines))
            else:
                self.log_path.write_text(line)
        except Exception:
            # Audit logging must never be the reason a gate fails --
            # every gate's own philosophy is fail-open, and a logging
            # error is not a reason to make a wrong wake/no-wake call.
            pass


class JobQueue:
    """A directory of pending `*.json` job files, with a `processed/`
    subdirectory jobs get moved into once handled -- never deleted
    immediately, so a crash mid-processing doesn't silently lose the
    record of what was seen.
    """

    def __init__(self, jobs_dir: Path, retain_days: int = 7):
        self.jobs_dir = jobs_dir
        self.processed_dir = jobs_dir / "processed"
        self.retain_days = retain_days

    def pending(self) -> List[Path]:
        if not self.jobs_dir.exists():
            return []
        return sorted(
            (f for f in self.jobs_dir.iterdir() if f.suffix == ".json"),
            key=lambda f: f.stat().st_mtime,
        )

    def mark_processed(self, job_file: Path) -> Path:
        """Move a job out of the pending queue before acting on it --
        prevents double-processing if the agent crashes mid-job."""
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        destination = self.processed_dir / job_file.name
        job_file.rename(destination)
        return destination

    def prune_processed(self) -> None:
        if not self.processed_dir.exists():
            return
        cutoff = datetime.now(timezone.utc).timestamp() - self.retain_days * 86400
        for f in self.processed_dir.iterdir():
            if f.suffix == ".json" and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                except OSError:
                    pass
