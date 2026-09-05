"""agent-team-infra: shared, tested infrastructure for a fleet of Hermes
agents -- knowledge-pull/repo-pull/repo-push/knowledge-commit, cron-gate
helpers (audit log, job queue, source-repo and own-repo wake gates), and
a generic GitHub webhook receiver.

Configuration (which repos, which agents, which paths trigger a wake) is
left to environment variables and the calling deployment -- nothing here
hardcodes a specific organization's repo or agent names. See README.md
for the full list of env vars each piece reads.
"""

__version__ = "0.1.0"
