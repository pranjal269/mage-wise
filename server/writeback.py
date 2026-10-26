def apply(
    repo: str,
    pr_number: int,
    file_path: str,
    resolution: str | None,
    reasoning: str,
    test_result: str,
    test_output: str,
) -> str:
    """F6: commit if resolution and test_result == "passed", else comment on the PR.

    Returns "auto_committed" | "posted_for_review".
    """
    raise NotImplementedError
