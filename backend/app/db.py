from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings


def _default_db_url() -> str:
    if settings.database_url:
        return settings.database_url
    db_path = settings.workspace_dir / "agent_dev.db"
    return f"sqlite+aiosqlite:///{db_path}"


engine = create_async_engine(
    _default_db_url(),
    connect_args={"timeout": 30} if _default_db_url().startswith("sqlite") else {},
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    requirement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=lambda: _now_iso())
    completed_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_project(requirement: str) -> ProjectRecord:
    rec = ProjectRecord(requirement=requirement, status="queued")
    async with SessionLocal() as session:
        session.add(rec)
        await session.commit()
        await session.refresh(rec)
        return rec


async def get_project(project_id: str) -> Optional[ProjectRecord]:
    async with SessionLocal() as session:
        return await session.get(ProjectRecord, project_id)


async def update_project(
    project_id: str, status: str, data: dict[str, Any], completed_at: Optional[str] = None
) -> None:
    async with SessionLocal() as session:
        rec = await session.get(ProjectRecord, project_id)
        if rec is None:
            return
        rec.status = status
        rec.data = json.loads(json.dumps(data, default=str))
        if completed_at:
            rec.completed_at = completed_at
        await session.commit()


async def list_projects(limit: int = 50) -> list[ProjectRecord]:
    from sqlalchemy import select

    async with SessionLocal() as session:
        result = await session.execute(
            select(ProjectRecord).order_by(ProjectRecord.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())