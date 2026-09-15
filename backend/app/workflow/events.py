"""In-process event broker for server-sent events to the dashboard.

The workflow publishes stage transitions + payloads here; FastAPI SSE endpoints
relay them to connected browsers for a live Development Status view.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional


class EventBroker:
    def __init__(self) -> None:
        self._pub: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, project_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        async with self._lock:
            self._pub.setdefault(project_id, []).append(q)
        return q

    async def unsubscribe(self, project_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._pub.get(project_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._pub.pop(project_id, None)

    async def publish(self, project_id: str, event: dict[str, Any]) -> None:
        event.setdefault("ts", datetime.now(timezone.utc).isoformat())
        async with self._lock:
            subs = list(self._pub.get(project_id, []))
        for q in subs:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)


broker = EventBroker()