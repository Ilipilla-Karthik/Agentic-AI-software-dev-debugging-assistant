from __future__ import annotations

from pathlib import Path

from ..diff import make_diff_entry
from ..gitrepo import commit
from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..sandbox.executor import write_project_files
from ..workflow.state import DevState
from .base import BaseAgent

_SKIP_PARTS = {".venv", "__pycache__", ".git", ".pytest_cache"}


def _snapshot(project_dir: Path) -> dict[str, str]:
    """Read the current on-disk project state (the source of truth)."""
    files: dict[str, str] = {}
    for p in project_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(project_dir)
        if any(x in _SKIP_PARTS for x in rel.parts):
            continue
        files[str(rel)] = p.read_text(encoding="utf-8", errors="replace")
    return files


class DebuggingAgent(BaseAgent):
    """Analyzes test failures and produces source patches, then requests a retest."""

    role = "debugging"

    def __init__(self, memory_store: AgentMemory) -> None:
        super().__init__(memory_store)

    async def run(self, state: DevState, provider: LLMProvider) -> DevState:
        state["status"] = "debugging"
        attempt = state.get("attempts", 0) + 1
        state["attempts"] = attempt
        await self.emit(
            state,
            "stage",
            f"Debugging Agent (attempt {attempt}): analyzing failures and producing a patch.",
        )

        before = _snapshot(Path(state["project_dir"])) or dict(state.get("files", {}))
        project_dir = Path(state["project_dir"])
        fixed, explanation = await provider.generate_fix(
            before, state.get("test_results", {}), attempt, project_dir=str(project_dir)
        )
        # Apply any parsed patch; the tool loop may already have written fixes
        # directly to disk, so the on-disk snapshot below is authoritative.
        write_project_files(project_dir, fixed)

        after = _snapshot(project_dir)
        all_paths = sorted(set(before) | set(after))
        diffs = [
            make_diff_entry(path, before.get(path, ""), after.get(path, ""), explanation)
            for path in all_paths
            if before.get(path, "") != after.get(path, "")
        ]

        state["files"] = after
        state["diffs"] = state.get("diffs", []) + diffs
        if diffs:
            state["fixes"] = state.get("fixes", []) + [
                {"attempt": attempt, "path": d["path"], "explanation": explanation} for d in diffs
            ]
        else:
            state["errors"].append(f"Debugging attempt {attempt} produced no changes.")

        await self.memory.remember(state["project_id"], self.role, "fix", state.get("fixes", []))
        await self.emit(
            state,
            "fix",
            f"Patch applied ({len(diffs)} file(s) changed)." if diffs else
            f"Attempt {attempt} produced no changes.",
            {"diffs": diffs, "explanation": explanation},
        )
        await self.log(state, f"[debugging] attempt={attempt} changed={len(diffs)} files")
        if diffs:
            msg = await commit(project_dir, f"fix: patch failing tests (attempt {attempt})")
            if msg:
                state.setdefault("commits", []).append(msg)
        return state