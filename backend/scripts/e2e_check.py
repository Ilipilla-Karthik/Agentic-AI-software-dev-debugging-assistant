"""Live end-to-end check: boots the real FastAPI server, drives the pipeline
over HTTP, consumes the SSE stream, and asserts the debug loop turns red->green.

Run:  python scripts/e2e_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PORT = 8001
BASE = f"http://127.0.0.1:{PORT}"
REQ = (
    "Create a FastAPI task-management API with PostgreSQL, JWT authentication, "
    "CRUD operations, validation, and automated tests."
)


def http(method: str, path: str, body: dict | None = None) -> dict:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode() or "{}")


def sse_first_event(path: str, timeout: float = 30.0) -> tuple[dict, str | None]:
    """Read SSE stream until the first non-ping data event. Returns (event, rest_of_stream)."""
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        headers = {}
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = resp.read(1)
            if not data:
                break
            buf += data
            # parse lines
            text = buf.decode("utf-8", "replace")
            if "\n\n" in text:
                head, rest = text.split("\n\n", 1)
                for line in head.splitlines():
                    if line.startswith("event:"):
                        ev = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        raw = line.split(":", 1)[1].strip()
                try:
                    payload = json.loads(raw)
                    return payload, rest
                except Exception:
                    buf = b""
        return {}, None


def main() -> int:
    print("Booting server...")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(HERE),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            try:
                health = http("GET", "/health")
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("server never came up")
            return 1
        print("health:", health)

        created = http("POST", "/api/projects", {"requirement": REQ})
        pid = created["project_id"]
        print("created project:", pid)

        # SSE: connect and watch for the final lifecycle event
        event, rest = sse_first_event(f"/api/projects/{pid}/events")
        print("first sse event:", event.get("type"), "-", event.get("message", "")[:80])

        for _ in range(600):
            st = http("GET", f"/api/projects/{pid}")
            status = st.get("status")
            if status in ("completed", "failed"):
                break
            time.sleep(0.5)
        else:
            print("TIMEOUT waiting for pipeline")
            return 2

        print("final status:", status)
        tr = st.get("test_results", {})
        print(f"test results: passed={tr.get('passed')} failed={tr.get('failed')} error={tr.get('error')}")
        print(f"debug attempts: {st.get('attempts')}  diffs: {len(st.get('diffs', []))}")
        print(f"review score: {st.get('review', {}).get('score')}")

        ok = status == "completed" and tr.get("failed", -1) == 0 and tr.get("error", -1) == 0 and len(st.get("diffs", [])) >= 1
        print("E2E RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 3
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())