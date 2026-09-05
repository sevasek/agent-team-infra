"""
GitHub webhook receiver, generic across every agent's watched repo.

Only validates the HMAC signature and relays fields already present in
the webhook payload GitHub sends -- repo, before/after SHAs, pusher, and
per-commit message/author/changed-file-paths. It never calls the GitHub
API and never fetches diff content, so it needs no GitHub token at all
(2026-09-05 redesign -- previously it held a GITHUB_READ_TOKEN to fetch
full diffs via the compare API; every field this needs is already in the
push payload for free). The watching agent fetches the actual diff
itself, using its own already-scoped credentials, only if it decides to
wake for the job -- see `own_repo_gate.py`.

Environment variables:
  GITHUB_WEBHOOK_SECRET   — the secret set in the GitHub webhook config
  JOBS_ROOT               — directory jobs are written under (default: /opt/data/jobs)
  REPO_JOB_DIR_MAP        — optional JSON object mapping "owner/repo" -> a
                            subdirectory name under JOBS_ROOT, for routing
                            different repos' jobs to different agents'
                            queues. A repo not listed uses its own name
                            as the subdirectory.
"""

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/opt/data/jobs"))
_REPO_JOB_DIR_MAP = json.loads(os.environ.get("REPO_JOB_DIR_MAP", "{}"))


def _verify_signature(payload: bytes, sig_header: str) -> bool:
    if not WEBHOOK_SECRET:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def _job_dir_for(repo_full_name: str) -> Path:
    subdir = _REPO_JOB_DIR_MAP.get(repo_full_name, repo_full_name.replace("/", "-"))
    return JOBS_ROOT / subdir


def build_job(payload: dict) -> dict:
    """Pure function, no I/O -- extracts everything the job needs directly
    from an already-parsed push payload. Split out from the route handler
    so it's testable without spinning up FastAPI or a real request."""
    repo = payload.get("repository", {}).get("full_name", "")
    before = payload.get("before", "")
    after = payload.get("after", "")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = payload.get("commits", [])

    return {
        "id": f"{repo.replace('/', '-')}-{after[:8]}-{int(time.time())}",
        "repo": repo,
        "before": before,
        "after": after,
        "pusher": pusher,
        "commits": [
            {
                "message": c.get("message", ""),
                "author": c.get("author", {}),
                "added": c.get("added", []),
                "removed": c.get("removed", []),
                "modified": c.get("modified", []),
            }
            for c in commits
        ],
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    payload_bytes = await request.body()

    if not _verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "push":
        return {"status": "ignored", "event": x_github_event}

    data = json.loads(payload_bytes)
    if not data.get("repository", {}).get("full_name") or not data.get("before") or not data.get("after"):
        raise HTTPException(status_code=400, detail="Missing repo, before, or after")

    job = build_job(data)

    job_dir = _job_dir_for(job["repo"])
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / f"{job['id']}.json").write_text(json.dumps(job, indent=2))

    return {"status": "queued", "job_id": job["id"]}


@app.get("/health")
async def health():
    return {"status": "ok"}
