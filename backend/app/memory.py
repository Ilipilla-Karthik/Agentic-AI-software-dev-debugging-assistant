"""Agent memory. Uses Redis when REDIS_URL is set, otherwise an in-process store.

The memory layer lets agents share context across workflow stages: each entry is
a small JSON document (agent, kind, content, ts) keyed by project id.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

from .config import settings


class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, list[dict[str, Any]]] = {}

    async def append(self, project_id: str, entry: dict[str, Any]) -> None:
        self._data.setdefault(project_id, []).append(entry)

    async def get(self, project_id: str) -> list[dict[str, Any]]:
        return list(self._data.get(project_id, []))

    async def clear(self, project_id: str) -> None:
        self._data.pop(project_id, None)


class RedisStore:
    def __init__(self, url: str) -> None:
        self._client = aioredis.from_url(url, decode_responses=True)
        self._prefix = "mem:"

    def _key(self, project_id: str) -> str:
        return f"{self._prefix}{project_id}"

    async def append(self, project_id: str, entry: dict[str, Any]) -> None:
        await self._client.rpush(self._key(project_id), json.dumps(entry, default=str))

    async def get(self, project_id: str) -> list[dict[str, Any]]:
        raw = await self._client.lrange(self._key(project_id), 0, -1)
        return [json.loads(r) for r in raw]

    async def clear(self, project_id: str) -> None:
        await self._client.delete(self._key(project_id))


class AgentMemory:
    """Facade over Redis or in-memory storage. Never raises on Redis failure."""

    def __init__(self) -> None:
        self._store: Any = InMemoryStore()
        self._redis_ok = False
        if settings.redis_url:
            try:
                self._store = RedisStore(settings.redis_url)
                self._redis_ok = True
            except Exception:
                self._store = InMemoryStore()

    @property
    def backend(self) -> str:
        return "redis" if self._redis_ok else "in-memory"

    async def remember(
        self, project_id: str, agent: str, kind: str, content: Any, ttl_hours: int = 24
    ) -> None:
        entry = {
            "id": uuid.uuid4().hex,
            "agent": agent,
            "kind": kind,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self._store.append(project_id, entry)
        except Exception:
            pass

    async def recall(self, project_id: str, agent: str | None = None) -> list[dict[str, Any]]:
        try:
            entries = await self._store.get(project_id)
        except Exception:
            return []
        if agent:
            entries = [e for e in entries if e.get("agent") == agent]
        return entries

    async def recall_last(self, project_id: str, agent: str, kind: str | None = None) -> Optional[dict[str, Any]]:
        entries = await self.recall(project_id, agent)
        if kind:
            entries = [e for e in entries if e.get("kind") == kind]
        return entries[-1] if entries else None

    async def clear(self, project_id: str) -> None:
        try:
            await self._store.clear(project_id)
        except Exception:
            pass


memory = AgentMemory()