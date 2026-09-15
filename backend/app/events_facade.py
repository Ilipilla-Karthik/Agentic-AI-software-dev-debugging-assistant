"""Safe event emissions used across the workflow (entry points outside a request)."""

from __future__ import annotations

import asyncio
from typing import Any

from .workflow.events import broker


async def safe_emit(project_id: str, kind: str, message: str, payload: Any = None) -> None:
    try:
        await broker.publish(project_id, {"type": kind, "stage": "system", "message": message, "payload": payload})
    except Exception:
        pass


def emit_sync(project_id: str, kind: str, message: str, payload: Any = None) -> None:
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(safe_emit(project_id, kind, message, payload))
    except RuntimeError:
        try:
            asyncio.run(safe_emit(project_id, kind, message, payload))
        except Exception:
            pass