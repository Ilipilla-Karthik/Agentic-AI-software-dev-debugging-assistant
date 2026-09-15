from __future__ import annotations

import abc
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..schemas import ReviewResult


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


class LLMProvider(abc.ABC):
    """Agent-facing LLM abstraction. Implementations are OpenAI or Mock."""

    name: str = "base"

    @abc.abstractmethod
    async def complete(
        self, system: str, user: str, json_mode: bool = False, temperature: float = 0.4
    ) -> str:
        ...

    # ---- typed workflows used by agents ----

    @abc.abstractmethod
    async def analyze(self, requirement: str) -> str:
        """Return a technical requirements report (markdown)."""

    @abc.abstractmethod
    async def plan(self, requirement: str, analysis: str) -> list[str]:
        """Return an ordered list of development steps."""

    @abc.abstractmethod
    async def architect(self, requirement: str, analysis: str, plan: list[str]) -> dict[str, Any]:
        """Return architecture JSON: {modules, apis, data_models, dependencies, rationale}."""

    @abc.abstractmethod
    async def generate_project(
        self, requirement: str, analysis: str, architecture: dict[str, Any]
    ) -> dict[str, str]:
        """Generate the full project as {relative_path: content}."""

    @abc.abstractmethod
    async def generate_tests(self, project_files: dict[str, str]) -> dict[str, str]:
        """Generate/overwrite automated test files -> {relative_path: content}."""

    @abc.abstractmethod
    async def generate_fix(
        self,
        project_files: dict[str, str],
        test_result: Any,
        attempt: int,
        project_dir: str = "",
    ) -> tuple[dict[str, str], str]:
        """Given failing tests, return (patched_file_set, explanation)."""

    @abc.abstractmethod
    async def review(
        self, requirement: str, project_files: dict[str, str], test_result: Any
    ) -> ReviewResult:
        ...

    # ---- tool calling loop (optional but recommended) ----

    async def run_tool_loop(
        self,
        system: str,
        user: str,
        tools: list[ToolDef],
        execute_tool,
        max_steps: int = 6,
    ) -> str:
        """Chat with tools until the model stops calling tools. Fallbacks to plain chat."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for _ in range(max_steps):
            calls = await self.chat_with_tools(messages, tools)
            if not calls:
                return messages[-1]["content"] if messages else ""
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})
            for call in calls:
                tool_output = await execute_tool(call)
                messages.append(
                    {"role": "tool", "tool_call_id": call.name, "content": tool_output}
                )
        return messages[-1]["content"] if messages else ""

    async def chat_with_tools(self, messages: list[dict], tools: list[ToolDef]) -> list[ToolCall]:
        return []


def extract_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction from model output. Handles objects,
    arrays, trailing commas, and markdown fences."""
    if not text:
        return None

    def _parse(candidate: str):
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)  # drop trailing commas
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start == -1 or end <= start:
            continue
        data = _parse(text[start : end + 1])
        if data is not None:
            return data
    return None


def parse_fixed_files(raw: str) -> dict[str, str]:
    """Parse a model response into {path: content}. Expects a JSON object of
    files or ```path fence blocks."""
    files: dict[str, str] = {}
    data = extract_json(raw)
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and (k.endswith(".py") or "." in k or k.startswith("app/") or k == "requirements.txt"):
                files[k] = v
        if files:
            return files
    # fence parsing: ```path
    pattern = re.compile(r"```(?:[a-zA-Z0-9]*)\s*([^\n`]+?)\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(raw):
        path, content = m.group(1).strip().lstrip("/"), m.group(2)
        if path and content is not None:
            files[path] = content
    return files