import os
import re
from concurrent.futures import ThreadPoolExecutor

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
    # Sides changed different lines (or only one side changed anything): no judgment needed, so skip
    # history (no index/GitHub) and the model.
    if verdict := resolver.deterministic(conflict_markers):
        ctx = []
    else:
        if commits is None and repo_path and (refs := githistory.merge_refs(repo_path)):
            ours, base, theirs = retriever.parse_conflict(conflict_markers)
            commits = githistory.side_commits(repo_path, *refs, file_path, ours, theirs, base)
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
        "model": verdict.get("model"),  # "provider/model" that answered; None when no model was needed
    }


def conflicted_files(repo_path: str, paths: list[str] | None = None) -> dict[str, str]:
    """{repo-relative path: text with conflict markers} for the files Git reports as unmerged."""
    paths = paths or githistory._git(repo_path, "diff", "--name-only", "--diff-filter=U").split()
    out = {}
    for p in paths:
        full = os.path.join(repo_path, p)
        if os.path.isfile(full):  # modify/delete conflicts leave no file to resolve hunk by hunk
            with open(full, encoding="utf-8", newline="") as fh:  # newline="": keep CRLF as-is
                out[p] = fh.read()
    return out


def resolve_files(
    repo: str,
    files: dict[str, str],
    pr_number: int | None = None,
    repo_path: str | None = None,
    workers: int = 4,
) -> dict:
    """Resolve every conflict hunk in a whole PR's worth of files, in parallel.

    files: {path: full text with conflict markers}. Returns per file the new content (textual-only hunks
    replaced, every other hunk left as its conflict markers) and each hunk's result, plus totals.
    A hunk that fails (model or provider error) counts as needing a human; it never sinks the batch.
    """
    jobs = [(path, h) for path, text in files.items() for h in retriever.hunks(text)]

    def one(job):
        path, hunk = job
        try:
            return resolve(repo, path, hunk, pr_number, repo_path=repo_path)
        except Exception as e:
            return {"classification": "error", "resolution": None, "reasoning": f"{type(e).__name__}: {e}",
                    "sources": [], "model": None}

    with ThreadPoolExecutor(max(1, workers)) as ex:
        results = list(ex.map(one, jobs))

    out = []
    for path, text in files.items():
        content, file_hunks = text, []
        for (p, hunk), r in zip(jobs, results):
            if p != path:
                continue
            if r["classification"] == "textual-only":
                merged = r["resolution"].replace("\r\n", "\n")
                if "\r\n" in hunk:  # model output is LF; match the file's line endings
                    merged = merged.replace("\n", "\r\n")
                content = content.replace(hunk, merged, 1)
            # conflict_markers lets an agent swap just this hunk with a small edit instead of rewriting the file.
            file_hunks.append({"index": len(file_hunks), "conflict_markers": hunk, **r})
        resolved = sum(h["classification"] == "textual-only" for h in file_hunks)
        out.append({"path": path, "content": content, "hunks": file_hunks,
                    "resolved": resolved, "needs_human": len(file_hunks) - resolved})
    return {
        "files": out,
        "resolved": sum(f["resolved"] for f in out),
        "needs_human": sum(f["needs_human"] for f in out),
    }
