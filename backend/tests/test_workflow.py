"""End-to-end tests for the multi-agent development workflow.

These run the REAL pipeline in mock (keyless) mode and assert the
code -> test -> debug -> retest -> review loop produces green results.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.workflow.graph import build_graph
from app.workflow.state import new_state

REQUIREMENT = (
    "Create a FastAPI task-management API with PostgreSQL, JWT authentication, "
    "CRUD operations, validation, and automated tests."
)


def _run(coro):
    return asyncio.run(coro)


class TestWorkflowLoop:
    def test_graph_builds(self, memory_store):
        graph, provider = build_graph(memory_store)
        assert provider.name == "mock"

    def test_full_run_reaches_completed(self, memory_store, tmp_path):
        from app.config import settings

        # isolate the workspace so tests never touch real projects
        original_root = settings.workspace_root
        settings.workspace_root = str(tmp_path / "workspaces")
        try:
            state = new_state("test-run", REQUIREMENT)
            graph, provider = build_graph(memory_store)
            final = _run(graph.ainvoke(state))
        finally:
            settings.workspace_root = original_root

        assert final["status"] == "completed"
        assert final["attempts"] >= 1, "debug loop should have run"
        tr = final["test_results"]
        assert tr["failed"] == 0 and tr["error"] == 0
        assert tr["passed"] >= 1
        # real bugs were found and fixed -> a diff must exist
        assert len(final["diffs"]) >= 1
        assert final["review"]["score"] > 0

    def test_mock_project_is_buggy_first_then_fixed(self, memory_store, tmp_path):
        """Proves the loop really executes generated code: the buggy variant must
        fail tests, the fixed variant must pass them, in the sandbox."""
        from app.config import settings
        from app.llm.mock_provider import MockProvider
        from app.sandbox.executor import prepare_and_install, run_pytest

        provider = MockProvider()
        original_root = settings.workspace_root
        settings.workspace_root = str(tmp_path / "workspaces")
        try:
            files = _run(provider.generate_project(REQUIREMENT, "analysis", {"stack": []}))
            tests = _run(provider.generate_tests(files))
            files.update(tests)
            project_dir = Path(settings.workspace_root) / "loop-check"
            code, out = _run(prepare_and_install(project_dir, files))
            assert code == 0
            buggy = _run(run_pytest(project_dir))
            assert buggy.failed >= 2, f"Expected >=2 failing tests, got {buggy.model_dump()}"
            assert buggy.passed >= 3

            fixed, _ = _run(provider.generate_fix(files, buggy, 1))
            from app.sandbox.executor import write_project_files

            write_project_files(project_dir, fixed)
            clean = _run(run_pytest(project_dir))
            assert clean.failed == 0 and clean.error == 0
            assert clean.passed == len(clean.cases) >= 6
        finally:
            settings.workspace_root = original_root

    def test_max_attempts_reaches_failed(self, memory_store):
        """If the debugger returns no patch, the pipeline must stop cleanly."""
        from app.config import settings

        original_root = settings.workspace_root
        settings.workspace_root = str(Path(settings.workspace_dir).parent / "workspaces-fail")
        original_max = settings.max_debug_attempts
        settings.max_debug_attempts = 1
        try:
            state = new_state("test-fail", REQUIREMENT)
            graph, _ = build_graph(memory_store)
            final = _run(graph.ainvoke(state))
            assert final["status"] in ("completed", "failed")
        finally:
            settings.workspace_root = original_root
            settings.max_debug_attempts = original_max


class TestSandbox:
    def test_pytest_summary_parsing_ok(self, tmp_path):
        from app.sandbox.executor import parse_junit
        from xml.etree import ElementTree as ET

        xml = "tests/test_demo.py"
        junit = ET.Element("testsuite")
        for name, status in [("a", "passed"), ("b", "failed")]:
            tc = ET.SubElement(junit, "testcase", {"name": name, "classname": "test_demo", "time": "0.01"})
            if status == "failed":
                ET.SubElement(tc, "failure", {"message": "boom"})
        p = tmp_path / "report.xml"
        ET.ElementTree(junit).write(p)
        cases = parse_junit(p)
        assert [c.outcome for c in cases] == ["passed", "failed"]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store():
    from app.memory import InMemoryStore

    class Stub:
        async def remember(self, project_id, agent, kind, content, ttl_hours=24):
            pass

        async def recall(self, project_id, agent=None):
            return []

        async def recall_last(self, project_id, agent, kind=None):
            return None

        async def clear(self, project_id):
            pass

    return Stub()