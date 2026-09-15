"""Unified-diff generation for code corrections (no external deps)."""

from __future__ import annotations

import difflib
from datetime import datetime, timezone


def unified_diff(before: str, after: str, path: str, context: int = 3) -> str:
    """Return a unified diff string between two file contents."""
    if before == after:
        return ""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=context,
    )
    return "".join(diff)


def make_diff_entry(path: str, before: str, after: str, summary: str) -> dict:
    """Build a serializable diff record for the artifact payload."""
    return {
        "path": path,
        "diff": unified_diff(before, after, path),
        "before": before,
        "after": after,
        "summary": summary,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }