"""Deterministic, keyless LLM provider used for demos and CI.

In mock mode the pipeline still runs the *real* loop: code is generated with
two deliberate defects, tests execute in the sandbox and fail, the debugging
agent patches the source, tests are re-run and pass, and the reviewer signs off.
This proves the code -> test -> debug -> retest machine without any API keys.
"""

from __future__ import annotations

from typing import Any

from ..schemas import ReviewResult
from .base import LLMProvider

# ---------------------------------------------------------------------------
# Generated application template (runnable, realistic FastAPI task API)
# ---------------------------------------------------------------------------

_REQUIREMENTS = """fastapi>=0.115
uvicorn[standard]>=0.30
PyJWT>=2.8
httpx>=0.27
pytest>=8.0
"""

_README = """# FastAPI Task Management API

A minimal task-management REST API with:

- JWT authentication (`POST /auth/token`)
- CRUD operations for tasks (`/tasks`)
- Request validation via Pydantic
- Automated tests with pytest (run: `python -m pytest -q`)

Run locally: `uvicorn app.main:app --reload`
Docs: http://localhost:8000/docs
"""

_APP_INIT = ""

_GITIGNORE = """.venv/
__pycache__/
*.pyc
report.xml
.pytest_cache/
"""

_BUGGY_MAIN = '''from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

SECRET_KEY = "dev-secret-change-me"
ALGORITHM = "HS256"

app = FastAPI(title="Task Management API", version="1.0.0")
bearer = HTTPBearer(auto_error=False)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, description="Task title")
    description: str = ""


class Task(BaseModel):
    id: str
    title: str
    description: str
    status: str = "pending"
    created_at: str


tasks: dict[str, Task] = {}


def create_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> str:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload["sub"]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/token")
def login(username: str, password: str) -> dict:
    if not username or not password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credentials required")
    return {"access_token": create_token(username), "token_type": "bearer"}


@app.post("/tasks")
def create_task(task: TaskIn, user: str = Depends(get_current_user)) -> Task:
    new = Task(
        id=uuid.uuid4().hex,
        title=task.title,
        description=task.description,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    tasks[new.id] = new
    return new


@app.get("/tasks")
def list_tasks(user: str = Depends(get_current_user)) -> list[Task]:
    return list(tasks.values())


@app.get("/tasks/{task_id}")
def get_task(task_id: str, user: str = Depends(get_current_user)) -> Task:
    task = tasks.get(task_id)
    if task is None:
        # BUG: missing task should raise 404, currently returns 200 empty body
        return Task(id="", title="", description="")  # type: ignore
    return task


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, user: str = Depends(get_current_user)) -> dict:
    if task_id not in tasks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    del tasks[task_id]
    return {"deleted": task_id}
'''

_FIXED_MAIN = _BUGGY_MAIN.replace(
    '@app.post("/tasks")\ndef create_task(task: TaskIn, user: str = Depends(get_current_user)) -> Task:',
    '@app.post("/tasks", status_code=status.HTTP_201_CREATED)\ndef create_task(task: TaskIn, user: str = Depends(get_current_user)) -> Task:',
).replace(
    """    task = tasks.get(task_id)
    if task is None:
        # BUG: missing task should raise 404, currently returns 200 empty body
        return Task(id="", title="", description="")  # type: ignore
    return task""",
    """    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task""",
)

_TESTS = '''from fastapi.testclient import TestClient

from app.main import SECRET_KEY, app, create_token

client = TestClient(app)


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_token('demo')}"}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_task_returns_201():
    resp = client.post("/tasks", json={"title": "Buy milk"}, headers=_auth())
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Buy milk"
    assert body["id"]


def test_create_task_rejects_empty_title():
    resp = client.post("/tasks", json={"title": ""}, headers=_auth())
    assert resp.status_code == 422


def test_get_missing_task_returns_404():
    resp = client.get("/tasks/does-not-exist", headers=_auth())
    assert resp.status_code == 404
    assert resp.json()["detail"]


def test_auth_required():
    resp = client.post("/tasks", json={"title": "x"})
    assert resp.status_code == 401


def test_delete_missing_returns_404():
    resp = client.delete("/tasks/nope", headers=_auth())
    assert resp.status_code == 404
'''

_FIX_EXPLANATION = """Two defects were identified from the failing tests and patched:

1. `tests/test_tasks.py::test_create_task_returns_201` expected HTTP 201, but the
   `create_task` endpoint used the default 200. Fix: added `status_code=status.HTTP_201_CREATED`
   to the route decorator.
2. `tests/test_tasks.py::test_get_missing_task_returns_404` expected a 404 for a
   missing task, but the handler returned a 200 with an empty body. Fix: raised
   `HTTPException(status_code=404, detail="Task not found")` when the task id is absent.

Retesting confirms all 6 tests now pass."""

_ANALYSIS = """## Requirement Analysis

**Goal:** A task-management REST API built with FastAPI.

### Functional requirements
1. Create tasks - title + optional description; validate input.
2. List all tasks.
3. Fetch a single task by id; a missing id must yield 404.
4. Delete a task by id.
5. Secure every task endpoint with JWT bearer authentication.
6. Issue JWTs via a token endpoint.

### Non-functional requirements
- FastAPI + Python 3.x, scalable async-ready app.
- Input validation through Pydantic schemas.
- Automated tests covering auth, validation, and CRUD behaviour.
- In-memory store is acceptable for this scope (the assignment asks for an
  automated, executable loop rather than a production database).

### Acceptance criteria (derived)
- A1: plaintext tests; create returns 201; empty title rejected (422).
- A2: unknown task returns 404 with meaningful detail.
- A3: endpoints without a valid bearer token return 401.
- A4: `pytest` passes 100% before completion.

### Risks
- State is lost on process restart (documented, in-memory by design).
- JWT secret is a dev placeholder (flagged for review)."""

_PLAN = [
    "Analyze requirements and derive acceptance criteria",
    "Design API surface, data models, and dependencies",
    "Scaffold FastAPI project (app, auth, CRUD, validation)",
    "Write pytest suite for auth, validation, and CRUD",
    "Execute tests in the sandbox; collect failures",
    "Debug: patch defects from failure reports",
    "Re-run tests until green",
    "Static review: security, maintainability, requirement coverage",
    "Build final summary and commit history",
]

_ARCHITECTURE = {
    "name": "fastapi-task-management-api",
    "stack": ["fastapi", "uvicorn", "PyJWT", "pytest", "httpx"],
    "modules": {
        "app/__init__.py": "Package marker",
        "app/main.py": "FastAPI application; in-memory task store; JWT auth; CRUD endpoints",
        "tests/test_tasks.py": "Automated tests covering auth, validation, and CRUD",
        "requirements.txt": "Python dependencies",
        "README.md": "Run and usage instructions",
    },
    "apis": [
        {"method": "POST", "path": "/auth/token", "purpose": "Issue a JWT", "auth": False},
        {"method": "POST", "path": "/tasks", "purpose": "Create a task (201)", "auth": True},
        {"method": "GET", "path": "/tasks", "purpose": "List tasks", "auth": True},
        {"method": "GET", "path": "/tasks/{id}", "purpose": "Fetch a task; 404 if missing", "auth": True},
        {"method": "DELETE", "path": "/tasks/{id}", "purpose": "Delete a task; 404 if missing", "auth": True},
    ],
    "data_models": [
        {
            "name": "Task",
            "fields": {
                "id": "str (uuid hex)",
                "title": "str",
                "description": "str",
                "status": "str, default 'pending'",
                "created_at": "str ISO-8601",
            },
        },
        {
            "name": "TaskIn",
            "fields": {
                "title": "str, min_length=1",
                "description": "str, default ''",
            },
        },
    ],
    "dependencies": {
        "fastapi": "web framework & OpenAPI",
        "uvicorn": "ASGI server",
        "PyJWT": "JWT encode/decode",
        "pytest": "test runner",
        "httpx": "test client transport",
    },
    "rationale": (
        "In-memory store keeps the demo self-contained; PyJWT is lighter than "
        "python-jose and avoids native build issues; single main.py stays reviewable."
    ),
}

_REVIEW_SUMMARY = """Review passed. Overall score 92/100.

Strengths: clean module boundaries, enforced validation, uniform 401/404 semantics,
and a focused test suite that covers the acceptance criteria.

Maintainability: single-module app is acceptable for the scope; would benefit from
splitting auth/routers as surface grows.

Security notes (non-blocking): the JWT secret is a hard-coded development value and
must come from an environment variable in production; passwords here are demo-only
(no storage layer in scope).

Requirement coverage: all acceptance criteria are met and verified by executing tests."""


class MockProvider(LLMProvider):
    name = "mock"

    async def complete(
        self, system: str, user: str, json_mode: bool = False, temperature: float = 0.4
    ) -> str:
        # Generic completions are only used for free-text surfaces; agents use
        # the typed methods below which return real artifacts.
        return "OK"

    # ---- typed workflows ----

    async def analyze(self, requirement: str) -> str:
        return _ANALYSIS

    async def plan(self, requirement: str, analysis: str) -> list[str]:
        return list(_PLAN)

    async def architect(self, requirement: str, analysis: str, plan: list[str]) -> dict[str, Any]:
        return dict(_ARCHITECTURE)

    async def generate_project(
        self, requirement: str, analysis: str, architecture: dict[str, Any]
    ) -> dict[str, str]:
        # First pass ships with two defects so the debug loop is exercised.
        return {
            "requirements.txt": _REQUIREMENTS,
            "README.md": _README,
            "app/__init__.py": _APP_INIT,
            "app/main.py": _BUGGY_MAIN,
            ".gitignore": _GITIGNORE,
        }

    async def generate_tests(self, project_files: dict[str, str]) -> dict[str, str]:
        return {"tests/test_tasks.py": _TESTS}

    async def generate_fix(
        self, project_files: dict[str, str], test_result: Any, attempt: int, project_dir: str = ""
    ) -> tuple[dict[str, str], str]:
        fixed = dict(project_files)
        fixed["app/main.py"] = _FIXED_MAIN
        return fixed, _FIX_EXPLANATION

    async def review(
        self, requirement: str, project_files: dict[str, str], test_result: Any
    ) -> ReviewResult:
        return ReviewResult(
            score=92,
            passed=True,
            summary=_REVIEW_SUMMARY,
            comments=[
                {
                    "severity": "critical" if False else "warning",
                    "file": "app/main.py",
                    "line": None,
                    "message": "JWT secret is hard-coded; move to an environment variable before production.",
                },
                {
                    "severity": "info",
                    "file": "app/main.py",
                    "line": None,
                    "message": "In-memory store loses state on restart; acceptable for demo scope.",
                },
                {
                    "severity": "info",
                    "file": "tests/test_tasks.py",
                    "line": None,
                    "message": "Consider parametrizing token helper to avoid repeating the _auth() call.",
                },
            ],
        )