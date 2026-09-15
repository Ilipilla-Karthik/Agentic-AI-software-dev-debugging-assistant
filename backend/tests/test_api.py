"""API-level smoke tests using FastAPI TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] in ("mock", "openai")


def test_requires_body_for_project(client):
    r = client.post("/api/projects", json={})
    assert r.status_code == 422


def test_create_and_poll_project(client):
    import time

    r = client.post(
        "/api/projects",
        json={"requirement": "Create a small FastAPI hello app with one test."},
    )
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # poll until the workflow finishes (mock loop is fast)
    status = "queued"
    for _ in range(600):
        r = client.get(f"/api/projects/{pid}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert status == "completed"
    r = client.get(f"/api/projects/{pid}")
    data = r.json()
    assert data["test_results"]["failed"] == 0
    assert len(data["diffs"]) >= 1


def test_list_projects(client):
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_missing_project_404(client):
    r = client.get("/api/projects/does-not-exist")
    assert r.status_code == 404