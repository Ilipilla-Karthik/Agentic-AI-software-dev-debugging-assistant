"""Local tools exposed to the LLM as function calls, bound to an isolated
workspace directory. Used by the debugging agent so fixes are derived from
real, executing state (tool calling), not guesses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..schemas import ExecutionResult
from .base import ToolCall, ToolDef


def list_files_tool(project_dir: Path) -> tuple[ToolDef, Callable]:
    def exec(call: ToolCall) -> str:
        root = (project_dir / call.arguments.get("path", ".")).resolve()
        try:
            items = sorted([str(p.relative_to(project_dir)) for p in root.rglob("*") if p.is_file() and ".venv" not in p.parts])
        except Exception:
            items = []
        return json.dumps(items)

    return ToolDef(
        name="list_files",
        description="List all project files (relative paths).",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ), exec


def read_file_tool(project_dir: Path) -> tuple[ToolDef, Callable]:
    def exec(call: ToolCall) -> str:
        rel = call.arguments.get("path", "")
        target = (project_dir / rel).resolve()
        try:
            return target.read_text(encoding="utf-8")[:8000]
        except FileNotFoundError:
            return f"[error] no such file: {rel}"

    return ToolDef(
        name="read_file",
        description="Read a file's contents (max 8000 chars).",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "relative path"}},
            "required": ["path"],
        },
    ), exec


def write_file_tool(project_dir: Path) -> tuple[ToolDef, Callable]:
    def exec(call: ToolCall) -> str:
        rel = call.arguments.get("path", "")
        content = call.arguments.get("content", "")
        if not rel:
            return "[error] missing path"
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"written {rel} ({len(content)} chars)"

    return ToolDef(
        name="write_file",
        description="Write a file (overwrites existing).",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ), exec


def run_tests_tool(project_dir: Path) -> tuple[ToolDef, Callable]:
    async def exec(call: ToolCall) -> str:
        from ..sandbox.executor import run_pytest

        result: ExecutionResult = await run_pytest(project_dir)
        return (
            f"passed={result.passed} failed={result.failed} error={result.error} skipped={result.skipped} "
            f"returncode={result.returncode}\nOutput tail:\n{(result.output or '')[-3000:]}"
        )

    return ToolDef(
        name="run_tests",
        description="Run the pytest suite in the sandbox and return pass/fail counts plus output.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ), exec


def build_tools(project_dir: Path) -> tuple[list[ToolDef], Callable]:
    tools: list[ToolDef] = []
    executors: dict[str, Callable] = {}
    for maker in (list_files_tool, read_file_tool, write_file_tool):
        td, fn = maker(project_dir)
        tools.append(td)
        executors[td.name] = fn
    td, run_tests_fn = run_tests_tool(project_dir)
    tools.append(td)
    executors[td.name] = run_tests_fn

    async def execute_tool(call: ToolCall) -> str:
        fn = executors.get(call.name)
        if fn is None:
            return f"[error] unknown tool {call.name}"
        result = fn(call)
        if isinstance(result, str):
            return result
        return await result

    return tools, execute_tool