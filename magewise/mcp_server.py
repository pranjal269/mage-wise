import argparse
import hmac
import os
import sys
from functools import partial

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import core, indexer

mcp = MCPServer(
    "magewise",
    instructions=(
        "Resolves Git merge conflicts using the repo's PR/issue history. When a merge or rebase leaves "
        "conflict markers, call resolve_conflict once per hunk. It returns a proposed hunk (or says a "
        "human must decide); you apply it and run the tests yourself."
    ),
)


async def _with_heartbeat(ctx: Context, fn):
    """Run a slow blocking call in a thread, reporting progress every 10s so clients don't time out."""
    result, error = {}, {}

    async def work():
        try:
            result["value"] = await anyio.to_thread.run_sync(fn)
        except Exception as e:  # re-raised below so the client sees the real error, not an ExceptionGroup
            error["value"] = e
        tg.cancel_scope.cancel()

    async with anyio.create_task_group() as tg:
        tg.start_soon(work)
        for tick in range(10_000):
            await ctx.report_progress(tick, message="working (model calls can take 1-2 minutes)")
            await anyio.sleep(10)
    if error:
        raise error["value"]
    return result["value"]


@mcp.tool()
async def resolve_conflict(
    repo: str,
    file_path: str,
    conflict_markers: str,
    ctx: Context,
    pr_number: int | None = None,
    repo_path: str | None = None,
) -> dict:
    """Propose a resolution for ONE merge-conflict hunk.

    repo: "owner/name" on GitHub (index it once with index_repo first).
    conflict_markers: one hunk, from <<<<<<< to >>>>>>>. Use `git config merge.conflictstyle diff3`
        so the common ancestor (||||||| section) is included; accuracy is much better with it.
    pr_number: the PR being merged, if any.
    repo_path: absolute path of the local checkout where the merge is in progress (local servers only).
        Lets Magewise find the exact commits behind each side instead of guessing from similarity.

    Returns classification ("textual-only" or "semantic"), resolution (the code that replaces the
    whole hunk, or null when a human must decide), reasoning, and the history documents used (sources).
    Never commit a resolution for a "semantic" classification. Takes 30s to 2 minutes.
    """
    return await _with_heartbeat(
        ctx, partial(core.resolve, repo, file_path, conflict_markers, pr_number, repo_path=repo_path)
    )


@mcp.tool()
async def index_repo(repo: str, ctx: Context, since: str | None = None, limit: int = 300) -> dict:
    """Index a GitHub repo's merged PRs, review comments and issues so resolve_conflict can look up
    why code changed. since: ISO date (YYYY-MM-DD). Slow: several minutes for a few hundred PRs."""
    count = await _with_heartbeat(ctx, partial(indexer.index_repo, repo, since, limit))
    return {"documents_count": count}


def _require_token(app, token: str):
    """ASGI wrapper: every HTTP request must carry `Authorization: Bearer <token>`."""
    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        got = dict(scope["headers"]).get(b"authorization", b"") if scope["type"] == "http" else expected
        if not hmac.compare_digest(got, expected):
            # Say why, never the token itself, so a misconfigured client is diagnosable from the server log.
            if not got:
                why = "no Authorization header"
            elif b"${" in got:
                why = "placeholder ${...} was sent literally, not substituted"
            elif not got.startswith(b"Bearer "):
                why = f"scheme is not Bearer (starts with {got.split(b' ')[0][:12]!r})"
            else:
                why = f"token mismatch (got {len(got) - 7} chars, expected {len(expected) - 7})"
            print(f"401 {scope['method']} {scope['path']}: {why}", file=sys.stderr, flush=True)
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"missing or wrong bearer token"})
            return
        await app(scope, receive, send)

    return guarded


def _root_alias(app):
    """Some MCP clients post to the bare host URL; serve it at /mcp too."""

    async def aliased(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/":
            scope = {**scope, "path": "/mcp", "raw_path": b"/mcp"}
        await app(scope, receive, send)

    return aliased


def main() -> None:
    p = argparse.ArgumentParser(prog="magewise-mcp", description="Magewise MCP server (stdio by default).")
    p.add_argument("--http", action="store_true", help="serve streamable HTTP at /mcp instead of stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = p.parse_args()

    if not args.http:
        mcp.run()
        return

    import uvicorn

    token = os.environ.get("MAGEWISE_TOKEN")
    if not token and args.host not in ("127.0.0.1", "localhost"):
        # The tools spend the server's GitHub and model credits; never expose them unauthenticated.
        sys.exit("refusing to listen on a public interface without MAGEWISE_TOKEN set")
    # The SDK's Host-header check only allows localhost, which rejects tunnels and real domains (421).
    # With a bearer token set, requests are already authenticated, so the check is redundant.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False) if token else None
    app = _root_alias(mcp.streamable_http_app(host=args.host, stateless_http=True, transport_security=security))
    uvicorn.run(_require_token(app, token) if token else app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
