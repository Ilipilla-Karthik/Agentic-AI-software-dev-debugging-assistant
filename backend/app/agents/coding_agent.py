from __future__ import annotations

from pathlib import Path

from ..config import settings
from ..gitrepo import commit, init_repo
from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..sandbox.executor import write_project_files
from ..workflow.state import DevState
from .base import BaseAgent


class CodingAgent(BaseAgent):
    """Generates the source code and scaffolds the isolated workspace + git repo."""

    role = "coding"

    def __init__(self, memory_store: AgentMemory) -> None:
        super().__init__(memory_store)

    def project_dir(self, state: DevState) -> Path:
        pid = state["project_id"]
        path = settings.workspace_dir / pid
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def run(self, state: DevState, provider: LLMProvider) -> DevState:
        state["status"] = "coding"
        await self.emit(
            state,
            "stage",
            "Coding Agent: generating application source code.",
        )
        files = await provider.generate_project(
            state["requirement"], state["analysis"], state.get("architecture", {})
        )
        if not files:
            state["errors"].append("Coding agent produced an empty file set.")
            raise RuntimeError("Coding agent produced an empty file set.")

        project_dir = self.project_dir(state)
        state["project_dir"] = str(project_dir)
        write_project_files(project_dir, files)
        await init_repo(project_dir)
        msg = await commit(project_dir, "feat: scaffold application source")
        if msg:
            state.setdefault("commits", []).append(msg if isinstance(msg, str) else str(msg))

        state["files"] = files
        await self.remember(state, "files", files)
        await self.emit(state, "files", f"Generated {len(files)} files.", {"files": list(files)})
        await self.log(state, f"[coding] generated {len(files)} files -> {project_dir}")
        return state