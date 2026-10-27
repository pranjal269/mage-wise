import re

from . import githistory, resolver, retriever


def resolve(
    repo: str,
    file_path: str,
    conflict_markers: str,
    pr_number: int | None = None,
    before: str | None = None,
    repo_path: str | None = None,
    commits: list[dict] | None = None,
) -> dict:
    """Retrieve history, then classify and (if textual-only) merge ONE conflict hunk.

    Proposes only; the caller applies the resolution and runs the tests.
    repo_path: local checkout with a merge in progress; enables commit-level history via git.
    commits: precomputed githistory.side_commits (the eval passes these directly).
    before: ISO timestamp; ignore history written after it (used by the eval to avoid leakage).
    Raises ValueError on bad markers.
    """
    if len(re.findall(r"^<{7}", conflict_markers, re.M)) > 1:
        raise ValueError("pass one conflict hunk per call (from <<<<<<< to >>>>>>>)")
    # One side unchanged from the base: no judgment needed, so skip history (no index/GitHub) and the model.
    if verdict := resolver.trivial(conflict_markers):
        ctx = []
    else:
        if commits is None and repo_path and (refs := githistory.merge_refs(repo_path)):
            ours, _, theirs = retriever.parse_conflict(conflict_markers)
            commits = githistory.side_commits(repo_path, *refs, file_path, ours, theirs)
        ctx = retriever.retrieve(repo, pr_number, file_path, conflict_markers, before, commits)
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
