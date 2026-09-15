from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    requirement: str = Field(..., min_length=3, description="User software requirement")


class ProjectCreateResponse(BaseModel):
    project_id: str
    status: str
    message: str


class ProjectListItem(BaseModel):
    project_id: str
    requirement: str
    status: str
    created_at: str
    completed_at: str | None = None


class FileEntry(BaseModel):
    path: str
    size: int
    sha: str


class DiffEntry(BaseModel):
    path: str
    diff: str
    before: str | None = None
    after: str | None = None
    summary: str
    applied_at: str


class TestCaseResult(BaseModel):
    name: str
    outcome: str  # passed | failed | error | skipped
    duration_ms: float | None = None
    description: str = ""


class ExecutionResult(BaseModel):
    returncode: int | None = None
    passed: int = 0
    failed: int = 0
    error: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    output: str = ""
    cases: list[TestCaseResult] = []
    timeout: bool = False


class ReviewComment(BaseModel):
    severity: str = "info"  # critical | warning | info
    file: str = ""
    line: int | None = None
    message: str


class ReviewResult(BaseModel):
    score: int = 0  # 0-100
    passed: bool = False
    comments: list[ReviewComment] = []
    summary: str = ""


class Artifact(BaseModel):
    report: str
    architecture: dict
    plan: list[str]
    files: dict[str, str]
    test_results: ExecutionResult
    diffs: list[DiffEntry]
    errors: list[str]
    fixes: list[dict]
    review: ReviewResult
    summary: str
    commits: list[str]