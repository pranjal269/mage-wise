import os
import re
from datetime import datetime, timezone

import chromadb
from github import Auth, Github

# ponytail: truncate instead of chunking; Chroma's default embedder only reads ~256 tokens anyway.
MAX_CHARS = 4000


def collection(repo: str):
    # Not ./chroma: when run as an MCP server the cwd is the user's own repo.
    default = os.path.join(os.path.expanduser("~"), ".magewise", "chroma")
    client = chromadb.PersistentClient(path=os.environ.get("CHROMA_PERSIST_DIR", default))
    return client.get_or_create_collection(repo.replace("/", "__"))


def _pipe(items) -> str:
    """Chroma metadata can't hold lists, so store "|a|b|" and match with f"|{x}|" in ..."""
    return "|" + "|".join(str(i) for i in items) + "|"


def _refs(text: str | None) -> list[str]:
    return sorted(set(re.findall(r"#(\d+)", text or "")))


def index_repo(repo: str, since: str | None, limit: int = 500) -> int:
    """F1: merged PRs (with files + commit messages), their review comments, and issues into ChromaDB."""
    r = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"])).get_repo(repo)
    cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    ids, docs, metas = [], [], []

    def add(doc_id, kind, source_id, text, files, linked, ts, user):
        ids.append(doc_id)
        docs.append(text[:MAX_CHARS])
        metas.append({
            "type": kind,
            "source_id": source_id,
            "file_paths": _pipe(files),
            "linked_ids": _pipe(linked),
            "timestamp": ts.isoformat(),
            "author": user.login if user else "",
        })

    prs = 0
    for pr in r.get_pulls(state="closed", sort="updated", direction="desc"):
        if prs >= limit or (cutoff and pr.updated_at < cutoff):
            break
        if not pr.merged_at:
            continue
        prs += 1
        files = [f.filename for f in pr.get_files()]
        commits = "\n".join(f"- {c.commit.message.splitlines()[0]}" for c in pr.get_commits())
        text = f"PR #{pr.number}: {pr.title}\nFiles: {', '.join(files)}\nCommits:\n{commits}\n\n{pr.body or ''}"
        add(f"pr-{pr.number}", "pr", pr.number, text, files, _refs(pr.body), pr.merged_at, pr.user)
        for c in pr.get_review_comments():
            text = f"Review on PR #{pr.number} ({c.path}):\n{c.body}\n\n{c.diff_hunk}"
            add(f"rc-{c.id}", "review_comment", pr.number, text, [c.path], [pr.number], c.created_at, c.user)

    issues = 0
    for issue in r.get_issues(state="all", **({"since": cutoff} if cutoff else {})):
        if issues >= limit:
            break
        if issue.pull_request:
            continue
        issues += 1
        text = f"Issue #{issue.number}: {issue.title}\n\n{issue.body or ''}"
        add(f"issue-{issue.number}", "issue", issue.number, text, [], _refs(issue.body), issue.created_at, issue.user)

    col = collection(repo)
    for i in range(0, len(ids), 500):
        col.upsert(ids=ids[i:i + 500], documents=docs[i:i + 500], metadatas=metas[i:i + 500])
    return len(ids)
