# agent-team-infra

Shared, tested infrastructure for the sevasek Hermes agent fleet
(Willow, Riker, Joe, Danielle, and whoever's next): knowledge-pull and
its git helpers, the cron-gate building blocks, and the GitHub webhook
receiver.

## Why this exists

On 2026-09-04, the SOUL.md-safe version of `knowledge-pull` — don't
apply SOUL.md live, only at container boot — existed in two places:
the generic `entrypoint.sh` and Riker's own copy. One got the fix, the
other didn't, and Riker's live instructions got silently swapped out
from under him every 30 minutes for an unknown stretch of time before
anyone noticed. That's the whole argument for this repo: one tested
implementation, installed the same way every agent already installs
`email-sidecar-mcp`, instead of N copies of the same shell heredocs
slowly drifting apart.

## What's in here

- **`knowledge_pull.py`** — the safety-critical sync. SOUL.md is only
  ever applied at container boot (`apply_soul_at_boot`); the periodic
  sync (`knowledge_pull`) refreshes MEMORY.md live and notifies via
  Telegram (once per changed version) if SOUL.md has drifted, but never
  touches the running copy.
- **`repo_ops.py`** — `repo_pull`, `repo_push` (commit + pull-rebase +
  push, never force-pushes — a conflict aborts and reports rather than
  clobbering a concurrent write), `knowledge_commit`.
- **`gate.py`** — `AuditLog` (append-only, rotating) and `JobQueue`
  (oldest-first, move-to-processed, prune old) — the two things every
  cron-gate script needs regardless of what it's actually gating.
- **`own_repo_gate.py`** — decides "wake" vs "refresh" for a push into
  an agent's *own* repo, based on which file changed (a task file wakes
  the agent; a knowledge file just refreshes) — not yet wired into any
  agent's live deployment.
- **`riker_job_gate.py`**, **`webhook_receiver.py`** — Riker's
  source-repo gate and the GitHub webhook receiver. The receiver no
  longer fetches diff content or holds a GitHub token at all (2026-09-05
  redesign) — it only validates the HMAC signature and relays fields
  already present in the push payload (repo, SHAs, pusher, per-commit
  message/author/changed-files). The watching agent fetches the actual
  diff itself, using its own already-scoped credentials, only if it
  decides to wake.
- **`notify.py`** — Telegram send via `requests`, not `curl` (found
  2026-09-04 that curl isn't installed in any agent's image, so the
  shell version of this had been silently no-op-ing since it was
  written).

## Installing into an agent's image

```dockerfile
RUN pip install --no-cache-dir "agent-team-infra @ git+https://github.com/sevasek/agent-team-infra.git@main"
```

Console scripts installed: `knowledge-pull`, `apply-soul-at-boot`,
`repo-pull <name>`, `repo-push <name> [message]`, `knowledge-commit
[message]` — drop-in replacements for the old heredoc-generated
`/opt/data/bin/*` scripts. They read `HERMES_HOME` (default `/opt/data`)
the same way the shell versions did.

`webhook_receiver`'s FastAPI app needs the `webhook` extra:
`pip install "agent-team-infra[webhook]"`.

## Status

Extracted and tested 2026-09-05. **Not yet wired into any agent's live
deployment** — Riker's and Willow's `entrypoint.sh` still generate their
own copies of this logic as shell heredocs. That migration is the next
step, done with the same care as Riker's git-based-deploy migration
(back up, verify, one agent at a time) rather than bundled into the
extraction itself.

## Development

```
pip install -e ".[dev]"
pytest
```
