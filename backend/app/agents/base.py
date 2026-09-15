from __future__ import annotations

from typing import Any

from ..llm.base import LLMProvider
from ..memory import AgentMemory
from ..workflow.events import broker
from ..workflow.state import DevState


class BaseAgent:
    role = "agent"

    def __init__(self, memory_store: AgentMemory) -> None:
        self.memory = memory_store

    async def emit(self, state: DevState, kind: str, message: str, payload: Any = None) -> None:
        await broker.publish(
            state["project_id"],
            {"type": kind, "stage": self.role, "message": message, "payload": payload},
        )

    async def remember(self, state: DevState, kind: str, content: Any) -> None:
        await self.memory.remember(state["project_id"], self.role, kind, content)

    async def log(self, state: DevState, message: str) -> None:
        state.setdefault("logs", []).append(message)


def prepare(state: DevState, provider: LLMProvider) -> None:
    state["status"] = "planning"