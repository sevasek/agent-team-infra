# agent-team-infra

Shared, tested infrastructure for a fleet of Hermes agents: knowledge-pull
and its git helpers, the cron-gate building blocks, and a generic GitHub
webhook receiver. Nothing here hardcodes a specific organization's repo
or agent names — every org-specific detail (which repos, which agents,
which file paths should trigger a wake) is configuration, passed in via
environment variables or the calling deployment.

## Why this exists

The pattern this replaces — each agent's `entrypoint.sh` generating its
own copy of `knowledge-pull` (and friends) as shell heredocs — has a
sharp failure mode: the safety-critical part of that logic (never apply
an agent's SOUL/charter file live, only at container boot) has to be
fixed identically in every copy. Miss one, and that agent's live
instructions can get silently swapped out from under it with no warning,
for however long it takes someone to notice the copies had drifted. One
tested implementation, installed the same way any other pip dependency
is, closes that gap by construction — there's exactly one place left to
get it right.

## What's in here

- **`knowledge_pull.py`** — the safety-critical sync. An agent's charter
  file is only ever applied at container boot (`apply_soul_at_boot`);
  the periodic sync (`knowledge_pull`) refreshes secondary state live and
  notifies via Telegram (once per changed version) if the charter has
  drifted, but never touches the running copy.
- **`repo_ops.py`** — `repo_pull`, `repo_push` (commit + pull-rebase +
  push, never force-pushes — a conflict aborts and reports rather than
  clobbering a concurrent write), `knowledge_commit`.
- **`gate.py`** — `AuditLog` (append-only, rotating) and `JobQueue`
  (oldest-first, move-to-processed, prune old) — the two things every
  cron-gate script needs regardless of what it's actually gating.
- **`own_repo_gate.py` / `own_repo_gate_cli.py`** — decides "wake" vs
  "refresh" for a push into an agent's *own* repo, based on which file
  changed (a designated task file wakes the agent; anything else just
  refreshes). A push authored entirely by the agent's own identity
  downgrades a would-be wake to a refresh — it's already active, it just
  made that edit.
- **`source_repo_gate.py`** — the cron pre-script for an agent that
  watches an external source repo it doesn't own and needs to decide
  what (if anything) to do about a change.
- **`webhook_receiver.py`** — a generic GitHub push-webhook receiver.
  Only validates the HMAC signature and relays fields already present in
  the payload (repo, before/after SHAs, pusher, per-commit
  message/author/changed-files) — it never calls the GitHub API and
  needs no GitHub token, since everything it hands off is already free
  in the payload. The watching agent fetches the actual diff itself,
  using its own already-scoped credentials, only if it decides to wake.
  Routes different repos to different job queues via `REPO_JOB_DIR_MAP`
  (a JSON env var mapping `"owner/repo"` to a subdirectory name).
- **`notify.py`** — Telegram send via `requests` (not `curl` — don't
  assume it's installed in the target image).

## Installing into an agent's image

```dockerfile
RUN pip install --no-cache-dir "agent-team-infra @ git+https://github.com/sevasek/agent-team-infra.git@main"
```

Console scripts installed: `knowledge-pull`, `apply-soul-at-boot`,
`repo-pull <name>`, `repo-push <name> [message]`, `knowledge-commit
[message]`, `own-repo-gate` — drop-in replacements for heredoc-generated
`/opt/data/bin/*` scripts. They read `HERMES_HOME` (default `/opt/data`)
and a handful of other env vars — see each module's docstring for the
full list.

`source_repo_gate.py` and `own_repo_gate_cli.py` are cron pre-scripts,
not console commands — copy the installed module file into your
`HERMES_HOME/scripts/` directory (most cron frameworks, Hermes included,
require gate scripts to physically live there) the same way you'd copy
in any other cron pre-script:

```sh
python3 -c 'import agent_team_infra.own_repo_gate_cli as m; print(m.__file__)'
```

`webhook_receiver`'s FastAPI app needs the `webhook` extra:
`pip install "agent-team-infra[webhook]"`.

## Development

```
pip install -e ".[dev,webhook]"
pytest
```
