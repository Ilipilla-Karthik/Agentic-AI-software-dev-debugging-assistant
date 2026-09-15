from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..db import create_project, get_project, list_projects, update_project
from ..memory import memory as global_memory
from ..schemas import ProjectCreate, ProjectCreateResponse, ProjectListItem
from ..workflow.events import broker
from ..workflow.graph import run_workflow

router = APIRouter(prefix="/projects", tags=["projects"])

_tasks: dict[str, asyncio.Task] = {}


@router.post("", response_model=ProjectCreateResponse, status_code=201)
async def start_project(body: ProjectCreate) -> ProjectCreateResponse:
    rec = await create_project(body.requirement)
    task = asyncio.create_task(
        run_workflow(rec.id, rec.requirement, global_memory),
        name=f"wf-{rec.id}",
    )
    _tasks[rec.id] = task
    task.add_done_callback(lambda t: _tasks.pop(rec.id, None))
    return ProjectCreateResponse(project_id=rec.id, status="queued", message="Development workflow started.")


@router.get("")
async def get_projects(limit: int = 50) -> list[ProjectListItem]:
    records = await list_projects(limit)
    return [
        ProjectListItem(
            project_id=r.id,
            requirement=r.requirement,
            status=r.status,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in records
    ]


@router.get("/{project_id}")
async def get_project_state(project_id: str) -> dict:
    rec = await get_project(project_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = dict(rec.data or {})
    data["status"] = rec.status
    data["requirement"] = rec.requirement
    data["created_at"] = rec.created_at
    data["completed_at"] = rec.completed_at
    return data


@router.get("/{project_id}/memory")
async def get_memory(project_id: str, agent: Optional[str] = None) -> list[dict]:
    entries = await global_memory.recall(project_id, agent)
    return entries


@router.get("/{project_id}/events")
async def project_events(project_id: str):
    async def event_stream():
        q = await broker.subscribe(project_id)
        try:
            # replay any persisted/current state as a baseline event
            from ..config import settings

            yield {"event": "ping", "data": "{}"}
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": ev.get("type", "event"), "data": _json(ev)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            await broker.unsubscribe(project_id, q)

    return EventSourceResponse(event_stream(), ping=15)


def _json(obj) -> str:
    import json

    return json.dumps(obj, default=str)


@router.post("/{project_id}/rerun")
async def rerun_project(project_id: str) -> dict:
    rec = await get_project(project_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Project not found")
    prev = await global_memory.clear(project_id)
    await update_project(project_id, "queued", {})
    task = asyncio.create_task(
        run_workflow(project_id, rec.requirement, global_memory),
        name=f"wf-{project_id}-rerun",
    )
    _tasks[project_id] = task
    return {"project_id": project_id, "status": "queued", "restarted": True}