import re

from . import resolver, retriever


def resolve(
    repo: str,
    file_path: str,
    conflict_markers: str,
    pr_number: int | None = None,
    before: str | None = None,
) -> dict:
    """Retrieve history, then classify and (if textual-only) merge ONE conflict hunk.

    Proposes only; the caller applies the resolution and runs the tests.
    before: ISO timestamp; ignore history written after it (used by the eval to avoid leakage).
    Raises ValueError on bad markers.
    """
    if len(re.findall(r"^<{7}", conflict_markers, re.M)) > 1:
        raise ValueError("pass one conflict hunk per call (from <<<<<<< to >>>>>>>)")
    ctx = retriever.retrieve(repo, pr_number, file_path, conflict_markers, before)
    verdict = resolver.resolve_hunk(file_path, conflict_markers, ctx)
    return {
        "classification": verdict["label"],
        "resolution": verdict["resolution"],
        "reasoning": (
            f"Ours: {verdict.get('ours_intent') or '?'}\n"
            f"Theirs: {verdict.get('theirs_intent') or '?'}\n"
            f"{verdict.get('reason', '')}"
        ),
        "sources": [h["id"] for h in ctx],
    }
