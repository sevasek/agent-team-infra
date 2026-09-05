"""agent-team-infra: shared, tested infrastructure for the sevasek Hermes
agent fleet -- knowledge-pull/repo-pull/repo-push/knowledge-commit, the
cron-gate helpers (audit log, job queue), and the GitHub webhook receiver.

Extracted 2026-09-05 after this logic was found duplicated across two
entrypoint.sh files, one of which had drifted and reintroduced a
safety bug the other had already been fixed for. One tested package,
installed the same way `email-sidecar-mcp` already is, instead of N
copies of the same shell heredocs.
"""

__version__ = "0.1.0"
