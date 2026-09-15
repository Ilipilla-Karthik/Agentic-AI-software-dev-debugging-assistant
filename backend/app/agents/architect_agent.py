from __future__ import annotations

from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..workflow.state import DevState
from .base import BaseAgent


class ArchitectAgent(BaseAgent):
    """Creates the application architecture: modules, APIs, data models, dependencies."""

    role = "architect"

    def __init__(self, memory_store: AgentMemory) -> None:
        super().__init__(memory_store)

    async def run(self, state: DevState, provider: LLMProvider) -> DevState:
        state["status"] = "planning"
        await self.emit(
            state,
            "stage",
            "Architect Agent: designing modules, API contracts, and data models.",
        )
        architecture = await provider.architect(
            state["requirement"], state["analysis"], state.get("plan", [])
        )
        state["architecture"] = architecture
        await self.remember(state, "architecture", architecture)
        await self.emit(state, "architecture", "Architecture plan ready.", {"architecture": architecture})
        await self.log(state, "[architect] architecture ready")
        return state