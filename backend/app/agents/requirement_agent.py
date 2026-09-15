from __future__ import annotations

from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..workflow.state import DevState
from .base import BaseAgent


class RequirementAnalysisAgent(BaseAgent):
    """Understands the request and converts it into a technical specification + plan."""

    role = "requirement-analysis"

    def __init__(self, memory_store: AgentMemory) -> None:
        super().__init__(memory_store)

    async def run(self, state: DevState, provider: LLMProvider) -> DevState:
        state["status"] = "planning"
        await self.emit(
            state,
            "stage",
            "Requirement Analysis Agent: parsing the request into a technical specification.",
        )
        analysis = await provider.analyze(state["requirement"])
        state["analysis"] = analysis
        await self.remember(state, "analysis", analysis)
        await self.emit(state, "analysis", "Requirement analysis drafted.", {"analysis": analysis})

        plan = await provider.plan(state["requirement"], analysis)
        state["plan"] = plan
        await self.remember(state, "plan", plan)
        await self.emit(state, "plan", "Development plan drafted.", {"plan": plan})
        await self.log(state, f"[requirement-analysis] analysis + {len(plan)}-step plan ready")
        return state