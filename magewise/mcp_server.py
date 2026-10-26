from mcp.server.mcpserver import MCPServer

from . import core, indexer

mcp = MCPServer(
    "magewise",
    instructions=(
        "Resolves Git merge conflicts using the repo's PR/issue history. When a merge or rebase leaves "
        "conflict markers, call resolve_conflict once per hunk. It returns a proposed hunk (or says a "
        "human must decide); you apply it and run the tests yourself."
    ),
)


@mcp.tool()
def resolve_conflict(repo: str, file_path: str, conflict_markers: str, pr_number: int | None = None) -> dict:
    """Propose a resolution for ONE merge-conflict hunk.

    repo: "owner/name" on GitHub (must be indexed with index_repo first).
    conflict_markers: one hunk, from <<<<<<< to >>>>>>>. Use `git config merge.conflictstyle diff3`
        so the common ancestor (||||||| section) is included; accuracy is much better with it.
    pr_number: the PR being merged, if any.

    Returns classification ("textual-only" or "semantic"), resolution (the code that replaces the
    whole hunk, or null when a human must decide), reasoning, and the history documents used (sources).
    Never commit a resolution for a "semantic" classification.
    """
    return core.resolve(repo, file_path, conflict_markers, pr_number)


@mcp.tool()
def index_repo(repo: str, since: str | None = None, limit: int = 300) -> dict:
    """Index a GitHub repo's merged PRs, review comments and issues so resolve_conflict can look up
    why code changed. since: ISO date (YYYY-MM-DD). Slow: allow several minutes for a few hundred PRs."""
    return {"documents_count": indexer.index_repo(repo, since, limit)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
