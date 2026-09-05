from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from agent_team_infra import webhook_receiver


def _sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_build_job_extracts_fields_with_no_api_call():
    payload = {
        "repository": {"full_name": "acme/source-repo"},
        "before": "aaa",
        "after": "bbb",
        "pusher": {"name": "someone"},
        "commits": [
            {
                "message": "update pricing",
                "author": {"name": "Jane Doe", "email": "someone@example.com"},
                "added": ["docs/new.md"],
                "removed": [],
                "modified": ["docs/services/pricing.md"],
            }
        ],
    }
    job = webhook_receiver.build_job(payload)
    assert job["repo"] == "acme/source-repo"
    assert job["before"] == "aaa"
    assert job["after"] == "bbb"
    assert job["pusher"] == "someone"
    assert len(job["commits"]) == 1
    assert job["commits"][0]["author"]["email"] == "someone@example.com"
    assert job["commits"][0]["modified"] == ["docs/services/pricing.md"]
    assert "diff" not in job  # the whole point of the 2026-09-05 redesign


def test_webhook_rejects_bad_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(webhook_receiver, "WEBHOOK_SECRET", "supersecret")
    monkeypatch.setattr(webhook_receiver, "JOBS_ROOT", tmp_path)
    client = TestClient(webhook_receiver.app)

    body = json.dumps({"repository": {"full_name": "a/b"}, "before": "x", "after": "y"}).encode()
    response = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "push"},
    )
    assert response.status_code == 401


def test_webhook_queues_job_on_valid_push(monkeypatch, tmp_path):
    secret = "supersecret"
    monkeypatch.setattr(webhook_receiver, "WEBHOOK_SECRET", secret)
    monkeypatch.setattr(webhook_receiver, "JOBS_ROOT", tmp_path)
    client = TestClient(webhook_receiver.app)

    body = json.dumps(
        {
            "repository": {"full_name": "acme/source-repo"},
            "before": "aaa",
            "after": "bbb",
            "pusher": {"name": "someone"},
            "commits": [{"message": "m", "author": {"email": "someone@example.com"}, "added": [], "removed": [], "modified": []}],
        }
    ).encode()
    response = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(secret, body), "X-GitHub-Event": "push"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    job_files = list((tmp_path / "acme-source-repo").glob("*.json"))
    assert len(job_files) == 1


def test_webhook_routes_by_repo_job_dir_map(monkeypatch, tmp_path):
    secret = "supersecret"
    monkeypatch.setattr(webhook_receiver, "WEBHOOK_SECRET", secret)
    monkeypatch.setattr(webhook_receiver, "JOBS_ROOT", tmp_path)
    monkeypatch.setattr(webhook_receiver, "_REPO_JOB_DIR_MAP", {"acme/agent-repo": "agent-b-jobs"})
    client = TestClient(webhook_receiver.app)

    body = json.dumps(
        {
            "repository": {"full_name": "acme/agent-repo"},
            "before": "aaa",
            "after": "bbb",
            "pusher": {"name": "agent-a"},
            "commits": [],
        }
    ).encode()
    client.post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(secret, body), "X-GitHub-Event": "push"},
    )

    assert list((tmp_path / "agent-b-jobs").glob("*.json"))


def test_webhook_ignores_non_push_events(monkeypatch, tmp_path):
    secret = "supersecret"
    monkeypatch.setattr(webhook_receiver, "WEBHOOK_SECRET", secret)
    monkeypatch.setattr(webhook_receiver, "JOBS_ROOT", tmp_path)
    client = TestClient(webhook_receiver.app)

    body = b"{}"
    response = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(secret, body), "X-GitHub-Event": "ping"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
