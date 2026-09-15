"""OpenAI-compatible LLM provider with tool calling.

The agent loop stays the same as mock mode, but generation, patching, and
review come from real model calls. During debugging the model gets *function
calls*: read_file / write_file / list_files / run_tests bound to the isolated
workspace, so the fix is driven by actual test output (tool calling).

Requires OPENAI_API_KEY. Without it the app uses MockProvider automatically.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from ..schemas import ExecutionResult, ReviewResult
from .base import LLMProvider, ToolCall, ToolDef, extract_json, parse_fixed_files

_SYSTEM_DEV = (
    "You are a senior software engineer inside an autonomous development pipeline. "
    "You produce complete, correct, modern Python files. "
    "When asked for file sets, ALWAYS answer with a single raw JSON object mapping "
    "relative file paths (e.g. \"app/main.py\") to file contents as strings. "
    "Do not wrap it in code fences. No commentary outside the JSON when files are requested. "
    "Use CURRENT, Python 3.13-compatible package versions (fastapi>=0.110, pydantic v2). "
    "Never pin EOL versions like fastapi==0.95 or pydantic==1.10. "
    "Implement EXACTLY what the requirement asks: a CLI stays a CLI, a web API stays a web API, "
    "a library stays a library. Never substitute a different application type."
)

_FIX_SYSTEM = (
    "You are a debugging agent. A generated project has failing tests. "
    "Use the provided tools to inspect files and run the test suite, then return a "
    "single raw JSON object of patched file paths -> new contents that makes all "
    "tests pass. Fix root causes, not symptoms. Return ONLY the JSON."
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove a leading ```lang / trailing ``` wrapper if present."""
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines(keepends=True)
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "".join(lines).strip()
        return stripped

    def __init__(self, model: str | None = None) -> None:
        from openai import AsyncOpenAI

        from ..config import settings

        self._settings = settings
        kwargs: dict = {}
        if self._settings.openai_base_url.strip():
            kwargs["base_url"] = self._settings.openai_base_url
        self.client = AsyncOpenAI(api_key=self._settings.openai_api_key, **kwargs)
        self.model = model or self._settings.openai_model

    async def complete(
        self, system: str, user: str, json_mode: bool = False, temperature: float = 0.4,
        max_tokens: int | None = None
    ) -> str:
        # Note: we intentionally do NOT send response_format={"type": "json_object"}.
        # Aggregator gateways (xKiro, AIMLAPI, Gemini) apply strict-schema guardrails
        # that reject arbitrary JSON payloads. Prompting for raw JSON and cleaning up
        # with extract_json() is robust across all OpenAI-compatible backends.
        if json_mode:
            system = system + " Always reply with raw JSON only: no markdown, no code fences, no commentary."
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        last_exc: Exception | None = None
        retryable = {408, 429, 500, 502, 503, 504}
        for attempt in range(3):
            try:
                resp = await self.client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 - transient rate/faults from aggregators
                import openai

                status = getattr(exc, "status_code", None)
                if not isinstance(exc, (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError)):
                    raise
                if status is not None and status not in retryable:
                    raise  # 400/401/403/404 are not transient
                if status == 429 and _is_quota_error(exc):
                    raise  # daily token quota exhausted - sleeping does not help
                if attempt >= 2:
                    raise
                delay = 2 ** attempt * 2  # 2, 4s - short backoff for burst throttling
                await asyncio.sleep(delay)
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("generation failed after retries")

    # ---- typed workflows ----

    async def analyze(self, requirement: str) -> str:
        prompt = (
            "Analyze the following software requirement and produce a technical "
            "requirements report (markdown) with: goals, functional requirements, "
            "non-functional requirements, derived acceptance criteria, and risks. "
            "No code fences, plain markdown only.\n\n"
            f"REQUIREMENT:\n{requirement}"
        )
        report = await self.complete(
            "You are a requirements analyst. Be precise and structured.", prompt,
            temperature=0.3, max_tokens=8000,
        )
        return self._strip_fences(report)

    async def plan(self, requirement: str, analysis: str) -> list[str]:
        prompt = (
            "Break this project into an ordered development plan of concrete steps "
            "(requirement analysis, architecture, coding, testing, debugging, review, "
            "documentation). Return a JSON array of strings only.\n\n"
            f"REQUIREMENT:\n{requirement}\n\nANALYSIS:\n{analysis}"
        )
        raw = await self.complete(_SYSTEM_DEV, prompt, json_mode=True, temperature=0.3, max_tokens=3000)
        data = extract_json(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
        if isinstance(data, dict):
            for key in ("plan", "steps", "items"):
                if isinstance(data.get(key), list):
                    return [str(x) for x in data[key]]
        return ["Analyze requirements", "Design architecture", "Implement code", "Write and run tests", "Debug until green", "Review", "Document"]

    async def architect(self, requirement: str, analysis: str, plan: list[str]) -> dict[str, Any]:
        prompt = (
            "Design the application architecture. Return JSON with keys: name, stack "
            "(list), modules (dict path->purpose), apis (list of {method, path, purpose, auth}), "
            "data_models (list of {name, fields}), dependencies (dict), rationale (string).\n\n"
            f"REQUIREMENT:\n{requirement}\n\nANALYSIS:\n{analysis}\n\nPLAN:\n{json.dumps(plan)}"
        )
        raw = await self.complete(_SYSTEM_DEV, prompt, json_mode=True, temperature=0.3, max_tokens=4000)
        data = extract_json(raw)
        if not isinstance(data, dict) or not data.get("modules"):
            retry = await self.complete(
                _SYSTEM_DEV,
                "Answer with EXACTLY ONE JSON object, all values complete. Template: "
                '{"name":"<title>", "stack":["<tech1>","<tech2>"], "modules":{"<path>":"<purpose>"}, '
                '"apis":[{"method":"<GET>","path":"<route>","purpose":"<text>","auth":"<none|jwt>"}], '
                '"data_models":[{"name":"<Model>","fields":"<f1, f2>"}], '
                '"dependencies":{"<package>":"<why>"}, "rationale":"<why this design>"}. '
                f"Do not leave any key empty.\n\nREQUIREMENT:\n{requirement}",
                json_mode=True,
                temperature=0.3,
                max_tokens=4000,
            )
            data = extract_json(retry)
        return _coerce_architecture(data, requirement, analysis)

    async def generate_project(
        self, requirement: str, analysis: str, architecture: dict[str, Any]
    ) -> dict[str, str]:
        prompt = (
            "Generate the complete application source for this requirement. Include "
            "requirements.txt, README.md, and all application modules. Return ONE raw "
            "JSON object: {relative_path: file_contents}.\n\n"
            f"REQUIREMENT:\n{requirement}\n\nANALYSIS:\n{analysis}\n\n"
            f"ARCHITECTURE:\n{json.dumps(architecture, indent=2)}"
        )
        raw = await self.complete(_SYSTEM_DEV, prompt, json_mode=True, temperature=0.4, max_tokens=30000)
        return parse_fixed_files(raw)

    async def generate_tests(self, project_files: dict[str, str]) -> dict[str, str]:
        if not project_files:
            return {}
        strategy = _detect_test_strategy(list(project_files.keys()))
        prompt = (
            "Generate a thorough pytest suite (tests/ directory) that validates the "
            "existing application: happy paths, error cases, and validation.\n\n"
            "IMPORTANT: import ONLY from modules that exist in EXISTING FILES below. "
            "If a module lives at the project root (e.g. converter.py) and you import it, "
            "also generate tests/conftest.py that inserts the project root into sys.path "
            "(dirname(dirname(abspath(__file__)))).\n\n"
            f"TESTING STRATEGY FOR THIS PROJECT:\n{strategy}\n\n"
            "Return ONE raw JSON object of file paths -> contents (e.g. "
            "\"tests/test_app.py\").\n\n"
            f"EXISTING FILES:\n{json.dumps(project_files, indent=2, default=str)[:12000]}"
        )
        raw = await self.complete(_SYSTEM_DEV, prompt, json_mode=True, temperature=0.3, max_tokens=20000)
        tests = parse_fixed_files(raw)
        if not tests:
            return {}
        unresolved = _unresolved_imports(tests, list(project_files))
        if unresolved:
            roots = _importable_roots(list(project_files))
            fix_prompt = (
                "Your previous test files have imports that do not exist in this project:\n"
                + "\n".join(f"- {u}" for u in unresolved[:12])
                + "\n\nAVAILABLE IMPORT ROOTS (import exactly these module paths):\n"
                + roots
                + "\n\nRewrite the whole test suite so EVERY local import resolves to one "
                "AVAILABLE IMPORT ROOT. Flat root modules (e.g. converter.py) need a "
                "tests/conftest.py that inserts the project root into sys.path. Never "
                "invent packages that are not listed.\n"
                'Return ONE raw JSON object of test file paths -> contents.'
            )
            retry = await self.complete(_SYSTEM_DEV, fix_prompt, json_mode=True, temperature=0.2, max_tokens=20000)
            fixed = parse_fixed_files(retry)
            if fixed:
                tests = fixed
        return tests

    async def generate_fix(
        self,
        project_files: dict[str, str],
        test_result: ExecutionResult,
        attempt: int,
        project_dir=None,
    ) -> tuple[dict[str, str], str]:
        from pathlib import Path

        from .tools import build_tools

        if project_dir is None:
            project_dir = self._settings.workspace_dir
        project_dir = Path(project_dir)
        failure_report = _failure_report(test_result)
        files_block = json.dumps(project_files, indent=2, default=str)
        user = (
            f"Attempt #{attempt}. Fix all test failures.\n\n"
            f"TEST REPORT:\n{failure_report}\n\nCURRENT FILES:\n{files_block[:12000]}"
        )
        tools, execute_tool = build_tools(project_dir)
        final_text = await self._tool_chat(_FIX_SYSTEM, user, tools, execute_tool)

        files = parse_fixed_files(final_text)
        explanation = final_text
        if files:
            explanation = (
                f"Debugging agent produced a patch via tool calling.\n"
                f"{list(files.keys())}\n\nRaw response (first 400 chars):\n{final_text[:400]}"
            )
        if not files:
            explanation += "\n\n[warning] no parseable file set returned by model; loop will retry."
        return files, explanation

    async def review(
        self, requirement: str, project_files: dict[str, str], test_result: ExecutionResult
    ) -> ReviewResult:
        result = _ensure_exec(test_result)
        prompt = (
            "Perform a code review of this generated project. Return JSON with keys: "
            "score (int 0-100), passed (bool), summary (string), comments (array of "
            "{severity: 'critical'|'warning'|'info', file, line (nullable int), message}).\n\n"
            f"REQUIREMENT:\n{requirement[:2000]}\n\n"
            f"TEST RESULTS: {result.passed} passed, {result.failed} failed, "
            f"{result.error} errors.\n\n"
            f"FILES:\n{json.dumps(project_files, default=str)[:14000]}"
        )
        _review_system = (
            "You are a strict code reviewer focusing on correctness, security, "
            "maintainability, and requirement coverage. If all tests pass and the "
            "implementation matches the requirement type (CLI vs API vs library), "
            "set passed = true unless there is a critical defect."
        )
        raw = await self.complete(
            _review_system,
            prompt,
            json_mode=True,
            temperature=0.2,
            max_tokens=8000,
        )
        data = extract_json(raw) or {}
        if "score" not in data or "summary" not in data:
            retry = await self.complete(
                "You are a strict code reviewer. Reply with EXACTLY this JSON shape and "
                'nothing else: {"score": <0-100>, "passed": <true|false>, '
                '"summary": "<one paragraph>", "comments": [{"severity": <"critical"|"warning"|"info">, '
                '"file": "<path>", "line": <int|null>, "message": "<text>"}]}',
                prompt,
                json_mode=True,
                temperature=0.2,
                max_tokens=8000,
            )
            data = extract_json(retry) or {}
        data = _fallback_review(data, result, requirement)
        comments = data.get("comments") if isinstance(data.get("comments"), list) else []
        score = data.get("score")
        try:
            score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = 0
        return ReviewResult(
            score=score,
            passed=bool(data.get("passed", score >= 60)),
            summary=str(data.get("summary", "")),
            comments=comments,
        )

    # ---- tool calling loop (bound to an isolated workspace) ----

    async def _tool_chat(
        self,
        system: str,
        user: str,
        tools: list[ToolDef],
        execute_tool: Callable[[ToolCall], asyncio.Future],
        max_steps: int = 8,
    ) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        tool_defs = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        for step in range(max_steps):
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tool_defs or None,
                tool_choice="auto" if tool_defs else None,
                temperature=0.2,
                max_tokens=16000,
            )
            msg = resp.choices[0].message
            if not (msg.tool_calls or []):
                return msg.content or ""
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                call = ToolCall(name=tc.function.name, arguments=args)
                output = await execute_tool(call)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": output[:8000]}
                )
        return messages[-1]["content"] or "Max tool steps reached without a final answer."


def _detect_test_strategy(paths: list[str]) -> str:
    """Choose the right test approach from the filenames so CLIs/libraries don't get
    forced through a web TestClient (which causes collection errors and 'no tests')."""
    joined = "\n".join(paths).lower()
    has_app = any(k in joined for k in ("fastapi", "flask", "app.py", "main.py", "django"))
    is_cli = any(k in joined for k in ("cli", "argparse", "click", "typer", "/cli", "cli.py"))
    if has_app and not is_cli:
        return (
            "The project exposes a web application (FastAPI/Flask). Import the app object "
            "and exercise its routes with starlette.testclient.TestClient (FastAPI) or "
            "app.test_client() (Flask). Include happy paths, validation errors, and auth."
        )
    if is_cli:
        return (
            "The project is a command-line tool. Import its command functions and call them "
            "directly, OR drive the entrypoint via subprocess([sys.executable, '<main>.py', ...]) "
            "and assert on stdout/exit codes. Do NOT use a web TestClient."
        )
    return (
        "The project is a library. Import the public modules and unit-test their functions "
        "directly (normalize inputs, edge cases, errors). No web TestClient needed."
    )


def _fallback_review(data: Any, result: ExecutionResult, requirement: str) -> dict[str, Any]:
    """Guarantee the review is never shown empty to the user."""
    if not isinstance(data, dict):
        data = {}
    score = data.get("score")
    has_score = isinstance(score, (int, float)) and not isinstance(score, bool)
    if not has_score:
        if result.failed == 0 and result.passed > 0:
            score = max(60, min(95, 60 + result.passed * 5))
        elif result.failed == 0 and result.passed == 0:
            score = 50  # completed but no tests exercised
        else:
            score = max(0, 100 - (result.failed + result.error) * 15)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        if result.failed == 0 and result.passed > 0:
            summary = (
                f"The build completed with {result.passed} passing test(s) and no failures. "
                "The implementation covers the core requirements; a few polish items may remain "
                "(edge cases, docs, type hints)."
            )
        elif result.failed > 0 or result.error > 0:
            summary = (
                f"The build completed but the test run reported {result.failed} failure(s) and "
                f"{result.error} error(s) out of {result.failed + result.passed + result.error} "
                f"cases. Requirement: {requirement[:160]}"
            )
        else:
            summary = (
                "The build completed. No test results were captured, so review is based on the "
                "generated code structure. Re-run to get an automated verdict."
            )
    comments = data.get("comments")
    if not isinstance(comments, list):
        comments = []
    passed = bool(data.get("passed", score >= 60))
    return {"score": score, "passed": passed, "summary": summary, "comments": comments}


def _unresolved_imports(test_files: dict[str, str], project_files: list[str]) -> list[str]:
    """Find test-file imports that reference modules not present in the project.

    Returns e.g. ['tests/test_converter.py: imports app.converter (no module)'] so the
    generator can correct the paths instead of the debug loop burning attempts.
    """
    import re
    import sys

    stdlib = frozenset(sys.stdlib_module_names)
    known_external = frozenset(
        "fastapi flask django requests httpx aiohttp pytest pytest_asyncio sqlalchemy pydantic "
        "jwt redis aiosqlite uvicorn starlette numpy pandas scipy matplotlib plotly openai "
        "click typer PIL pillow dotenv yaml bs4 celery asyncpg pdfkit reportlab xlsxwriter "
        "openpyxl lxml tqdm jinja2 markdown textblob nltk sklearn torch tensorflow".split()
    )
    roots = _top_level_roots(project_files)
    unresolved: list[str] = []
    for path, content in test_files.items():
        for m in re.finditer(r"^\s*from\s+(\S+)\s+import\s+\S+.*$|^\s*import\s+(\S+)", content, re.M):
            mod = (m.group(1) or m.group(2) or "").split(".")[0]
            if mod and mod not in stdlib and mod not in known_external and mod not in roots:
                unresolved.append(f"{path}: imports '{mod}' but no module/dir '{mod}' exists")
    return unresolved


def _top_level_roots(paths: list[str]) -> set[str]:
    """First path segment of each file -> importable root, e.g. ['app/converter.py'] -> {'app'}."""
    roots: set[str] = set()
    for p in paths:
        if not p.endswith(".py"):
            continue
        first = p.split("/", 1)[0]
        roots.add(first.removesuffix(".py"))
    return roots


def _importable_roots(paths: list[str]) -> str:
    lines = []
    for p in sorted(paths):
        if not p.endswith((".py", "/")):
            continue
        if p.lower().startswith("tests/"):
            continue
        if p.endswith("/"):
            lines.append(f"{p} -> package")
            continue
        mod = p[:-3].replace("/", ".")
        lines.append(f"{p} -> module: {mod}")
    return "\n".join(lines) if lines else "(no python modules found)"


def _coerce_architecture(data: Any, requirement: str, analysis: str = "") -> dict[str, Any]:
    """Return a complete, non-empty architecture dict, filling gaps from the requirement."""
    req = requirement.lower()
    if not isinstance(data, dict) or not data:
        data = {}
    stack = data.get("stack")
    if not isinstance(stack, list) or not stack:
        candidates = []
        if any(k in req for k in ("cli", "command line", "command-line", "terminal")):
            candidates.append("python-cli")
        elif any(k in req for k in ("api", "fastapi", "flask", "rest", "web", "http", "microservice")):
            candidates.append("fastapi")
        elif "django" in req:
            candidates.append("django")
        else:
            candidates.append("python")
        if any(k in req for k in ("database", "postgres", "sqlite", "sql", "db")):
            candidates.append("datastore")
        if any(k in req for k in ("test", "pytest")):
            candidates.append("pytest")
        stack = candidates
    modules = data.get("modules")
    if not isinstance(modules, dict) or not modules:
        modules = {"app/": f"Core application package (implied by: {requirement[:80]})"}
    apis = data.get("apis")
    if not isinstance(apis, list):
        apis = []
    models = data.get("data_models")
    if not isinstance(models, list):
        models = []
    deps = data.get("dependencies")
    if not isinstance(deps, dict):
        deps = {}
    if not deps and stack:
        deps = {s: "core stack dependency" for s in (stack[:2] or ["python"])}
    rationale = str(data.get("rationale") or "").strip()
    if not rationale:
        rationale = f"Solution built for: {requirement[:160]}"
        if analysis:
            rationale += " | " + analysis.strip()[:200]
    return {
        "name": str(data.get("name") or "project"),
        "stack": stack,
        "modules": modules,
        "apis": apis,
        "data_models": models,
        "dependencies": deps,
        "rationale": rationale,
    }


def _ensure_exec(test_result: Any) -> ExecutionResult:
    """Coerce an ExecutionResult object or its dict dump into ExecutionResult."""
    if isinstance(test_result, ExecutionResult):
        return test_result
    if isinstance(test_result, dict):
        fields = set(ExecutionResult.model_fields)
        return ExecutionResult(**{k: v for k, v in test_result.items() if k in fields})
    return ExecutionResult()


def _is_quota_error(exc: Exception) -> bool:
    """True when a 429 means 'daily token quota exhausted' rather than a transient burst.

    xKiro/AIMLAPI return messages like "You've reached today's free-model token quota
    ... wait for the daily reset" with code rate_limit_exceeded. Sleeping would just
    waste time - surface it immediately so the pipeline fails fast with a clear reason.
    """
    text = str(getattr(exc, "body", "") or exc).lower()
    return any(k in text for k in ("quota", "daily", "reset", "exhausted", "insufficient", "allowance"))


def _failure_report(result: Any) -> str:
    result = _ensure_exec(result)
    lines = [
        f"returncode={result.returncode} passed={result.passed} failed={result.failed} "
        f"error={result.error} skipped={result.skipped}",
    ]
    for case in result.cases:
        if case.outcome in ("failed", "error"):
            lines.append(f"- [{case.outcome}] {case.name}: {case.description}")
    tail = (result.output or "")[-3500:]
    lines.append("--- console tail ---")
    lines.append(tail)
    return "\n".join(lines)