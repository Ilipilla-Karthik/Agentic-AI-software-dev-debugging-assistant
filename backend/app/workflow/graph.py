"""LangGraph agent pipeline: plan -> code -> test -> (debug -> retest)* -> review.

The debug->test edge is the *real* loop: failing tests feed the debugging agent,
which patches source in the sandbox, then tests re-execute against the patch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..agents.architect_agent import ArchitectAgent
from ..agents.coding_agent import CodingAgent
from ..agents.debugging_agent import DebuggingAgent
from ..agents.requirement_agent import RequirementAnalysisAgent
from ..agents.reviewer_agent import CodeReviewerAgent
from ..agents.testing_agent import TestingAgent
from ..config import settings
from ..events_facade import safe_emit
from ..llm import get_provider
from ..memory import AgentMemory
from .state import DevState, new_state


def _decide(state: DevState) -> str:
    tr = state.get("test_results", {})
    failed = tr.get("failed", 0) or 0
    errors = tr.get("error", 0) or 0
    if failed + errors == 0:
        return "review"
    if state.get("attempts", 0) >= settings.max_debug_attempts:
        return "failed"
    return "debug"


def _finalize(state: DevState) -> DevState:
    tr = state.get("test_results", {})
    review = state.get("review", {})
    state["summary"] = (
        f"Development completed for: {state['requirement']}\n"
        f"- Files generated: {len(state.get('files', {}))}\n"
        f"- Test runs: passed={tr.get('passed', 0)}, failed={tr.get('failed', 0)}, errors={tr.get('error', 0)}\n"
        f"- Debug attempts: {state.get('attempts', 0)}\n"
        f"- Review score: {review.get('score', '-')}/100 "
        f"({'PASSED' if review.get('passed') else 'NEEDS WORK'})\n"
        f"- Commits: {len(state.get('commits', []))}\n"
        f"Finished at {datetime.now(timezone.utc).isoformat()}"
    )
    state["status"] = "completed"
    return state


def _failed(state: DevState) -> DevState:
    state["status"] = "failed"
    tr = state.get("test_results", {})
    state["summary"] = (
        f"Pipeline stopped after {state.get('attempts', 0)} debug attempts; "
        f"tests still failing ({tr.get('failed', 0)} failures, {tr.get('error', 0)} errors). "
        "Open the Tests tab to see the exact failure - re-run from the project to retry."
    )
    return state


def build_graph(memory: AgentMemory):
    provider = get_provider()

    requester = RequirementAnalysisAgent(memory)
    architect = ArchitectAgent(memory)
    coder = CodingAgent(memory)
    tester = TestingAgent(memory)
    debugger = DebuggingAgent(memory)
    reviewer = CodeReviewerAgent(memory)

    async def node_analyze(s: DevState) -> DevState:
        return await requester.run(s, provider)

    async def node_architect(s: DevState) -> DevState:
        return await architect.run(s, provider)

    async def node_code(s: DevState) -> DevState:
        return await coder.run(s, provider)

    async def node_test(s: DevState) -> DevState:
        return await tester.run(s, provider)

    async def node_debug(s: DevState) -> DevState:
        return await debugger.run(s, provider)

    async def node_review(s: DevState) -> DevState:
        return await reviewer.run(s, provider)

    graph = StateGraph(DevState)
    graph.add_node("analyze", node_analyze)
    graph.add_node("architect", node_architect)
    graph.add_node("code", node_code)
    graph.add_node("test", node_test)
    graph.add_node("debug", node_debug)
    graph.add_node("review", node_review)
    graph.add_node("finalize", lambda s: _finalize(s))
    graph.add_node("failed", lambda s: _failed(s))

    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "architect")
    graph.add_edge("architect", "code")
    graph.add_edge("code", "test")
    graph.add_conditional_edges("test", _decide, {"debug": "debug", "review": "review", "failed": "failed"})
    graph.add_edge("debug", "test")
    graph.add_edge("review", "finalize")
    graph.add_edge("finalize", END)
    graph.add_edge("failed", END)
    return graph.compile(), provider


def _provider_name() -> str:
    return get_provider().name


# node name -> UI status label persisted to the database at each step
_NODE_STATUS = {
    "analyze": "planning",
    "architect": "planning",
    "code": "coding",
    "test": "testing",
    "debug": "debugging",
    "review": "reviewing",
    "finalize": "completed",
    "failed": "failed",
}


async def run_workflow(project_id: str, requirement: str, memory: AgentMemory) -> dict[str, Any]:
    from ..db import update_project

    state = new_state(project_id, requirement)
    graph, provider = build_graph(memory)
    await safe_emit(project_id, "lifecycle", f"Workflow started with provider={provider.name}", {"provider": provider.name})
    await update_project(project_id, "running", state)

    try:
        last_status = "running"
        async for chunk in graph.astream(state, stream_mode="updates"):
            for node_name, node_state in chunk.items():
                if not isinstance(node_state, dict):
                    continue
                state.update(node_state)
                status = _NODE_STATUS.get(node_name, last_status)
                last_status = status
                # persist every stage so the API never reports a stale state
                await update_project(project_id, status, state)
        final = state
        if final.get("status") != "failed":
            final["status"] = last_status if last_status != "running" else "failed"
    except Exception as exc:  # keep the pipeline honest: surface failures
        state["status"] = "failed"
        state["errors"].append(f"pipeline error: {exc}")
        state["summary"] = f"Pipeline crashed: {exc}"
        final = state
        await safe_emit(project_id, "error", f"Pipeline error: {exc}", {})

    await update_project(
        project_id,
        final.get("status", "completed"),
        final,
        completed_at=datetime.now(timezone.utc).isoformat()
        if final.get("status") in ("completed", "failed")
        else None,
    )
    await safe_emit(project_id, "final", f"Status: {final.get('status')}", {"status": final.get("status")})
    return final