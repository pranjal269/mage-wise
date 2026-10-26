def index_repo(repo: str, since: str | None) -> int:
    """F1: pull PRs, commits, issues, review comments via GitHub API; embed into ChromaDB.

    Metadata per doc: type, file_paths, source_id, linked_ids, timestamp. Returns doc count.
    """
    raise NotImplementedError
