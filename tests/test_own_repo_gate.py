from __future__ import annotations

from agent_team_infra.own_repo_gate import classify, is_self_authored


def _job(commits):
    return {"commits": commits}


def test_classify_wakes_on_task_file_touch():
    job = _job([{"author": {"email": "agent-a@hermes.local"}, "modified": ["project-tasks.md"]}])
    assert classify(job, task_file_paths={"project-tasks.md"}) == "wake"


def test_classify_refreshes_on_knowledge_file_touch():
    job = _job([{"author": {"email": "agent-a@hermes.local"}, "modified": ["company/company.md"]}])
    assert classify(job, task_file_paths={"project-tasks.md"}) == "refresh"


def test_classify_wakes_if_any_commit_touches_task_file():
    job = _job(
        [
            {"author": {"email": "a@a"}, "modified": ["company/company.md"]},
            {"author": {"email": "a@a"}, "modified": ["project-tasks.md"]},
        ]
    )
    assert classify(job, task_file_paths={"project-tasks.md"}) == "wake"


def test_classify_checks_added_and_removed_too():
    assert classify(_job([{"added": ["project-tasks.md"], "modified": [], "removed": []}]), {"project-tasks.md"}) == "wake"
    assert classify(_job([{"added": [], "modified": [], "removed": ["project-tasks.md"]}]), {"project-tasks.md"}) == "wake"


def test_is_self_authored_true_when_every_commit_matches():
    job = _job(
        [
            {"author": {"email": "agent-b@hermes.local"}},
            {"author": {"email": "agent-b@hermes.local"}},
        ]
    )
    assert is_self_authored(job, "agent-b@hermes.local")


def test_is_self_authored_false_on_mixed_authors():
    job = _job(
        [
            {"author": {"email": "agent-b@hermes.local"}},
            {"author": {"email": "agent-a@hermes.local"}},
        ]
    )
    assert not is_self_authored(job, "agent-b@hermes.local")


def test_is_self_authored_fails_open_on_no_commits():
    assert not is_self_authored(_job([]), "agent-b@hermes.local")
