"""Generic cron-gate entry point for "did my own repo just get updated"
jobs -- usable by any single-repo agent (Willow, Joe, Danielle, whoever's
next), not just Riker's source-repo case.

Reads the next pending job (written by `webhook_receiver.py` into this
agent's own job queue), decides wake vs refresh via `own_repo_gate`, and
either:
  - "refresh": runs `knowledge_pull` immediately (the whole point --
    near-instant instead of waiting up to 30 minutes for the background
    timer) and reports no-wake.
  - "wake": reports wake=true with a summary, unless every commit in the
    push was authored by this agent itself, in which case it's a
    redundant wake (the agent that just made the edit is already
    active) and gets downgraded to a refresh instead.

Environment variables:
  HERMES_HOME            — default /opt/data
  OWN_REPO_JOBS_DIR      — default ${HERMES_HOME}/jobs
  TASK_FILE_PATHS        — comma-separated paths that trigger a wake,
                           default "project-tasks.md"
  AGENT_IDENTITY_EMAIL   — this agent's own git commit-author email, used
                           to detect and downgrade a redundant self-wake.
                           If unset, self-authored downgrading is skipped
                           (every task-file push wakes).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .gate import AuditLog, JobQueue
from .knowledge_pull import knowledge_pull
from .own_repo_gate import classify, is_self_authored


def main() -> None:
    hermes_home = Path(os.environ.get("HERMES_HOME", "/opt/data"))
    jobs_dir = Path(os.environ.get("OWN_REPO_JOBS_DIR", str(hermes_home / "jobs")))
    task_file_paths = {
        p.strip() for p in os.environ.get("TASK_FILE_PATHS", "project-tasks.md").split(",") if p.strip()
    }
    identity_email = os.environ.get("AGENT_IDENTITY_EMAIL")

    queue = JobQueue(jobs_dir)
    audit = AuditLog(hermes_home / "logs" / "own-repo-gate.log")

    queue.prune_processed()

    pending = queue.pending()
    if not pending:
        audit.write("SILENT (0 pending jobs)")
        print(json.dumps({"wakeAgent": False}))
        return

    job_file = pending[0]
    try:
        job = json.loads(job_file.read_text())
    except Exception as exc:
        audit.write(f"ERROR reading {job_file.name}: {exc}")
        print(json.dumps({"wakeAgent": False}))
        return

    queue.mark_processed(job_file)

    decision = classify(job, task_file_paths)
    if decision == "wake" and identity_email and is_self_authored(job, identity_email):
        decision = "refresh"
        audit.write(f"REFRESH (downgraded, self-authored) job={job.get('id', '?')} repo={job.get('repo', '?')}")
    else:
        audit.write(f"{decision.upper()} job={job.get('id', '?')} repo={job.get('repo', '?')} remaining={len(pending) - 1}")

    if decision == "refresh":
        result = knowledge_pull(
            hermes_home=hermes_home,
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            owner_id=os.environ.get("TELEGRAM_ALLOWED_USERS"),
        )
        print(result)
        print(json.dumps({"wakeAgent": False}))
        return

    commits = job.get("commits", [])
    commit_lines = "; ".join(c.get("message", "") for c in commits) or "(no commits listed)"
    summary = (
        f"Your own repo was updated.\n"
        f"Repo: {job.get('repo')}\n"
        f"Pusher: {job.get('pusher')}\n"
        f"Commits: {commit_lines}\n"
        f"Received: {job.get('received_at')}\n\n"
        f"This touched a task file (project-tasks.md) — read the current "
        f"content directly (it's already synced locally) and decide whether "
        f"to act on it now or schedule a cron reminder for later. This content "
        f"already went through the normal approval flow before being "
        f"committed, so there's nothing here to second-guess — just act."
    )
    print(summary)
    print(json.dumps({"wakeAgent": True}))


if __name__ == "__main__":
    main()
