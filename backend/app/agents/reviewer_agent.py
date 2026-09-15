from __future__ import annotations

from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..schemas import ReviewResult
from ..workflow.state import DevState
from .base import BaseAgent


class CodeReviewerAgent(BaseAgent):
    """Reviews quality, security, maintainability, and requirement coverage."""

    role = "review"

    def __init__(self, memory_store: AgentMemory) -> None:
        super().__init__(memory_store)

    async def run(self, state: DevState, provider: LLMProvider) -> DevState:
        state["status"] = "reviewing"
        await self.emit(
            state,
            "stage",
            "Code Reviewer Agent: checking quality, security, and requirement coverage.",
        )
        result: ReviewResult = await provider.review(
            state["requirement"], state.get("files", {}), state.get("test_results", {})
        )
        state["review"] = result.model_dump()
        await self.memory.remember(state["project_id"], self.role, "review", result.model_dump())
        await self.emit(
            state,
            "review",
            f"Review complete: {result.score}/100 {'PASSED' if result.passed else 'NEEDS WORK'}.",
            result.model_dump(),
        )
        await self.log(state, f"[review] score={result.score} passed={result.passed}")
        return state