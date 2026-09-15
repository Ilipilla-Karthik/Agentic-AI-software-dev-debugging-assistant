from __future__ import annotations

from pathlib import Path

from ..gitrepo import commit
from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..sandbox.executor import prepare_and_install, run_pytest, write_project_files
from ..schemas import ExecutionResult
from ..workflow.state import DevState
from .base import BaseAgent


class TestingAgent(BaseAgent):
    """Writes automated tests, executes them in the isolated sandbox, reports results."""

    role = "testing"

    def __init__(self, memory_store: AgentMemory) -> None:
        super().__init__(memory_store)

    async def run(self, state: DevState, provider: LLMProvider) -> DevState:
        state["status"] = "testing"
        await self.emit(
            state,
            "stage",
            "Testing Agent: authoring automated tests, then executing them in the sandbox.",
        )
        files = dict(state.get("files", {}))
        tests = state.get("tests") or await provider.generate_tests(files)
        state["tests"] = tests
        files.update(tests)

        project_dir = Path(state["project_dir"])
        if not project_dir.exists():
            project_dir.mkdir(parents=True, exist_ok=True)

        state["files"] = files
        write_project_files(project_dir, files)
        await self.remember(state, "tests", tests)
        state["errors"] = []

        code, out = await prepare_and_install(project_dir, files)
        if code != 0:
            state["errors"].append(out[-2000:])

        result: ExecutionResult = await run_pytest(project_dir)
        payload = result.model_dump()
        state["test_results"] = payload
        await self.remember(state, "test_results", payload)
        await self.emit(
            state,
            "test-results",
            f"Tests executed: {result.passed} passed / {result.failed} failed / {result.error} errors.",
            payload,
        )
        await self.log(
            state,
            f"[testing] py={result.passed} fail={result.failed} err={result.error} "
            f"({result.duration_ms}ms)",
        )
        msg = await commit(project_dir, "test: add automated test suite and run it")
        if msg:
            state.setdefault("commits", []).append(msg)
        return state