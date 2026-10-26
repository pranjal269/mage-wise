import re

from . import classifier, resolver, retriever, test_runner, writeback


def resolve(
    repo: str,
    file_path: str,
    conflict_markers: str,
    pr_number: int | None = None,
    dry_run: bool = True,
) -> dict:
    """F2-F6 for one conflict hunk. Shared by the REST API and the MCP server.

    dry_run=True proposes only: the caller applies and tests it. Raises ValueError on bad markers.
    """
    if len(re.findall(r"^<{7}", conflict_markers, re.M)) > 1:
        raise ValueError("pass one conflict hunk per call (from <<<<<<< to >>>>>>>)")
    ctx = retriever.retrieve(repo, pr_number, file_path, conflict_markers)
    verdict = classifier.classify(file_path, conflict_markers, ctx)
    reasoning = (
        f"Ours: {verdict.get('ours_intent', '?')}\nTheirs: {verdict.get('theirs_intent', '?')}\n{verdict['reason']}"
    )
    resolution = (
        resolver.propose(file_path, conflict_markers, ctx, verdict)
        if verdict["label"] == "textual-only"
        else None
    )

    if dry_run:
        test_result, action = "not_run", "dry_run"
    else:
        test_result, test_output = (
            test_runner.run(repo, pr_number, file_path, resolution) if resolution else ("not_run", "")
        )
        action = writeback.apply(repo, pr_number, file_path, resolution, reasoning, test_result, test_output)
    return {
        "classification": verdict["label"],
        "resolution": resolution,
        "reasoning": reasoning,
        "sources": [h["id"] for h in ctx],
        "test_result": test_result,
        "action_taken": action,
    }
