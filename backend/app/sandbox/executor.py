"""Isolated code-execution sandbox.

Generated projects run inside their own workspace folder with a dedicated
virtualenv. Every stage that touches generated code (tests, retests) goes
through here so untrusted code never runs in the assistant's process.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from ..config import settings
from ..schemas import ExecutionResult, TestCaseResult

VENV_DIRNAME = ".venv"
REQUIREMENTS_FILE = "requirements.txt"
JUNIT_FILE = "junit.xml"


def _py(project_dir: Path, *args: str) -> list[str]:
    if os.name == "nt":
        return [str(project_dir / VENV_DIRNAME / "Scripts" / "python.exe"), *args]
    return [str(project_dir / VENV_DIRNAME / "bin" / "python"), *args]


_INVALID_FNAME_CHARS = {chr(c) for c in range(32)} | {'"', "*", "<", ">", "?", "|"}
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_rel_path(rel: str) -> str | None:
    """Normalize a model-supplied relative path into a safe, writable one.
    Returns None if the path cannot be salvaged (empty, traversal, invalid)."""
    if not isinstance(rel, str):
        return None
    cleaned = rel.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")
    if cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    segments = [seg for seg in cleaned.split("/") if seg not in ("", ".")]
    if not segments:
        return None
    out: list[str] = []
    for seg in segments:
        if seg in ("..", "."):
            return None
        seg = seg.strip().rstrip(".")
        seg = "".join(ch for ch in seg if ch not in _INVALID_FNAME_CHARS)
        seg = seg.strip()
        # reject suspicious extensionless names with embedded whitespace (LLM junk)
        if any(ch.isspace() for ch in seg) and "." not in seg:
            return None
        if not seg or len(seg) > 200 or seg.upper() in _RESERVED_NAMES:
            return None
        out.append(seg)
    return "/".join(out)


async def _run_subprocess(
    cmd: list[str], cwd: Path, timeout: int
) -> tuple[int, str, bool]:
    loop = asyncio.get_event_loop()

    def _exec() -> tuple[int, str, bool]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            return proc.returncode, output, False
        except subprocess.TimeoutExpired:
            return -1, f"[sandbox] command timed out after {timeout}s", True

    return await loop.run_in_executor(None, _exec)


def write_project_files(project_dir: Path, files: dict[str, str]) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        safe = sanitize_rel_path(rel) or rel.strip()
        if not safe:
            continue
        target = project_dir / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def ensure_venv(project_dir: Path) -> tuple[int, str]:
    venv = project_dir / VENV_DIRNAME
    if venv.exists():
        marker = project_dir / ".venv_ready"
        if marker.exists():
            return 0, "[sandbox] venv already prepared"
    # create a fresh venv (isolated from system site-packages)
    proc = subprocess.run(
        [sys.executable, "-m", "venv", VENV_DIRNAME],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    return 0, ""


def parse_junit(junit_path: Path) -> list[TestCaseResult]:
    cases: list[TestCaseResult] = []
    if not junit_path.exists():
        return cases
    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError:
        return cases
    for tc in root.iter("testcase"):
        name = tc.get("name", "unknown")
        classname = tc.get("classname", "")
        full = f"{classname}::{name}" if classname else name
        time_ms = None
        t = tc.get("time")
        if t:
            try:
                time_ms = round(float(t) * 1000, 1)
            except ValueError:
                time_ms = None
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")
        msg = ""
        if failure is not None:
            outcome = "failed"
            msg = (failure.get("message") or "").splitlines()[0][:500]
        elif error is not None:
            outcome = "error"
            msg = (error.get("message") or "").splitlines()[0][:500]
        elif skipped is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        cases.append(
            TestCaseResult(name=full, outcome=outcome, duration_ms=time_ms, description=msg)
        )
    return cases


async def run_pytest(project_dir: Path, timeout: int | None = None) -> ExecutionResult:
    timeout = timeout or settings.execution_timeout
    result = ExecutionResult()
    junit_path = project_dir / JUNIT_FILE
    if junit_path.exists():
        junit_path.unlink()

    cmd = _py(
        project_dir,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "--junitxml=report.xml",
        "-p",
        "no:cacheprovider",
        "tests",
    )
    start = time.perf_counter()
    returncode, output, timed_out = await _run_subprocess(cmd, project_dir, timeout)
    result.duration_ms = round((time.perf_counter() - start) * 1000, 1)
    result.returncode = returncode
    result.output = output[-6000:]
    result.timeout = timed_out

    junit = project_dir / "report.xml"
    result.cases = parse_junit(junit)
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for c in result.cases:
        counts[c.outcome] = counts.get(c.outcome, 0) + 1
    result.passed = counts["passed"]
    result.failed = counts["failed"]
    result.error = counts["error"]
    result.skipped = counts["skipped"]
    # If junit missing (e.g. collection error), fall back to summary parsing
    if not result.cases and output:
        for line in output.splitlines():
            s = line.strip()
            if s.startswith("1 failed") or ("failed" in s and s.split()[-1] in ("failed", "passed", "error")):
                parts = s.replace(",", "").split()
                for i, part in enumerate(parts[:-1]):
                    if part == "failed":
                        result.failed = int(parts[i + 1])
                    elif part == "passed":
                        result.passed = int(parts[i + 1])
                    elif part == "error":
                        result.error = int(parts[i + 1])
    # A non-zero exit with no collected tests means the suite is broken
    # (import/collection errors, missing fixtures) -> surface it so the
    # debug loop triggers instead of silently treating it as passing.
    if returncode != 0 and not result.cases and result.passed == 0 and result.failed == 0 and result.error == 0:
        result.error = 1
    return result


async def prepare_and_install(project_dir: Path, files: dict[str, str]) -> tuple[int, str]:
    """Write files, create venv, install deps. Returns (code, output)."""
    write_project_files(project_dir, files)

    code, out = ensure_venv(project_dir)
    if code != 0:
        return code, "[sandbox] venv creation failed:\n" + out

    req = project_dir / REQUIREMENTS_FILE
    if not req.exists():
        return 0, "[sandbox] no requirements.txt; skipping install"

    marker = project_dir / ".venv_ready"
    if marker.exists():
        return 0, "[sandbox] dependencies already installed"

    _, out, _ = await _run_subprocess(
        _py(
            project_dir,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-q",
            "-r",
            REQUIREMENTS_FILE,
            "pytest",
            "pytest-asyncio",
        ),
        project_dir,
        timeout=300,
    )
    # Python 3.13 compat: LLMs sometimes pin EOL fastapi/pydantic (v1) which
    # crash under 3.13. Unpin them so the sandbox runs.
    await _run_subprocess(
        _py(
            project_dir,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-q",
            "-U",
            "fastapi",
            "pydantic",
        ),
        project_dir,
        timeout=300,
    )
    # Level marker checked best-effort: even on partial failure we let tests
    # decide the truth via the reporter.
    marker.write_text("ok", encoding="utf-8")
    if "Successfully installed" in out:
        return 0, "[sandbox] dependencies installed"
    return 0, "[sandbox] dependency install finished (best-effort)"