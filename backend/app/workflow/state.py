from typing import Any, TypedDict


class DevState(TypedDict, total=False):
    project_id: str
    requirement: str
    status: str
    analysis: str
    plan: list[str]
    architecture: dict[str, Any]
    files: dict[str, str]
    tests: dict[str, str]
    test_results: dict[str, Any]
    errors: list[str]
    fixes: list[dict[str, Any]]
    diffs: list[dict[str, Any]]
    review: dict[str, Any]
    summary: str
    attempts: int
    logs: list[str]
    commits: list[str]
    project_dir: str


def new_state(project_id: str, requirement: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "requirement": requirement,
        "status": "queued",
        "analysis": "",
        "plan": [],
        "architecture": {},
        "files": {},
        "tests": {},
        "test_results": {},
        "errors": [],
        "fixes": [],
        "diffs": [],
        "review": {},
        "summary": "",
        "attempts": 0,
        "logs": [],
        "commits": [],
        "project_dir": "",
    }