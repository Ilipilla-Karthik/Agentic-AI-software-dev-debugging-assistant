"""Git integration for generated projects.

Each generated project lives in its own workspace folder which is also a git
repository. Stages commit incrementally, producing a commit history that mirrors
the plan -> code -> fix -> review pipeline.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

_CREDS = ["-c", "user.name=Agent Dev Assistant", "-c", "user.email=agent@dev.local"]


async def _run(cmd: list[str], cwd: Path) -> str:
    loop = asyncio.get_event_loop()

    def _exec() -> str:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            shell=False,
            timeout=60,
        )
        return (proc.stdout or "").strip() + ("\n" + (proc.stderr or "").strip() if proc.stderr and proc.stderr.strip() else "")

    return await loop.run_in_executor(None, _exec)


async def init_repo(project_dir: Path) -> None:
    if not (project_dir / ".git").exists():
        await _run(["git", "init", "-q"], project_dir)
        await _run(["git", "config", "user.name", "Agent Dev Assistant"], project_dir)
        await _run(["git", "config", "user.email", "agent@dev.local"], project_dir)


async def commit(project_dir: Path, message: str) -> str | None:
    await _run(["git", "add", "-A"], project_dir)
    out = await _run(["git", *_CREDS, "commit", "-q", "-m", message], project_dir)
    return message if "nothing to commit" not in out.lower() else None


async def log(project_dir: Path, max_count: int = 20) -> list[str]:
    out = await _run(["git", "log", "--oneline", f"-{max_count}"], project_dir)
    lines = [l for l in out.splitlines() if l.strip()]
    return [l for l in lines if not l.lower().startswith(("fatal", "error"))]


async def snapshot_status(project_dir: Path) -> str:
    out = await _run(["git", "status", "--short"], project_dir)
    return out or "clean"