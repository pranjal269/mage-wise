import re
from datetime import datetime

TOP_K = 5
HUNK = re.compile(r"^<{7} [^\n]*\n.*?^>{7}[^\n]*\n", re.S | re.M)


def hunks(text: str) -> list[str]:
    """Every conflict hunk in a file, each from its <<<<<<< line through its >>>>>>> line."""
    return HUNK.findall(text)


def parse_conflict(markers: str) -> tuple[str, str, str]:
    """Split one conflict hunk into (ours, base, theirs). base is "" unless git used diff3 style."""
    m = re.search(
        r"^<{7}[^\n]*\n(.*?)^(?:\|{7}[^\n]*\n(.*?))?={7}\n(.*?)^>{7}",
        markers.replace("\r\n", "\n"),
        re.S | re.M,
    )
    if not m:
        raise ValueError("no <<<<<<< / ======= / >>>>>>> conflict hunk found")
    return m.group(1), m.group(2) or "", m.group(3)


def _get(col, ids: list[str]) -> dict:
    # Chroma raises on an empty id list.
    return col.get(ids=ids) if ids else {"ids": [], "documents": [], "metadatas": []}


def _hits(res, side, before: datetime | None = None):
    return [
        {"id": i, "side": side, "content": d, **m}
        for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
        if before is None or datetime.fromisoformat(m["timestamp"]) < before
    ]


def retrieve(
    repo: str,
    pr_number: int | None,
    file_path: str,
    conflict_markers: str,
    before: str | None = None,
    commits: list[dict] | None = None,
) -> list[dict]:
    """F2: history for both sides of the conflict, plus issues they link to.

    commits: the real commits behind each side (githistory.side_commits). When given, they and the PRs
        they reference replace the similarity search, which can only guess which side a document belongs to.
    before: ISO timestamp; drop documents created after it.
    """
    from .indexer import CHROMA_LOCK

    ours, _, theirs = parse_conflict(conflict_markers)
    with CHROMA_LOCK:
        return _retrieve(repo, pr_number, file_path, ours, theirs, before, commits or [])


def _retrieve(repo, pr_number, file_path, ours, theirs, before, commits) -> list[dict]:
    from .indexer import collection

    col = collection(repo)
    cutoff = datetime.fromisoformat(before) if before else None
    ctx = {c["id"]: c for c in commits}
    if not col.count():
        return list(ctx.values())

    ctx.update({h["id"]: h for h in _hits(_get(col, [f"pr-{pr_number}"] if pr_number else []), "theirs (this PR)")})
    if commits:
        # PRs the commits reference (squash merges say "(#123)"), labeled with the commit's side.
        side_of = {f"pr-{n}": c["side"] for c in commits for n in c["linked_ids"].strip("|").split("|") if n}
        for h in _hits(_get(col, sorted(side_of)), "", cutoff):
            ctx.setdefault(h["id"], {**h, "side": side_of[h["id"]]})
    else:
        _similar(col, file_path, ours, theirs, cutoff, ctx)

    linked = {f"issue-{x}" for h in ctx.values() for x in h["linked_ids"].strip("|").split("|") if x}
    for h in _hits(_get(col, sorted(linked)), "linked", cutoff):
        ctx.setdefault(h["id"], h)
    return list(ctx.values())


def _similar(col, file_path, ours, theirs, cutoff, ctx) -> None:
    """Fallback without a local repo: documents near each side's code, preferring ones that touched the file."""
    for side, code in (("ours", ours), ("theirs", theirs)):
        res = col.query(query_texts=[f"{file_path}\n{code}"], n_results=min(50, col.count()))
        hits = _hits({k: res[k][0] for k in ("ids", "documents", "metadatas")}, side, cutoff)
        # ponytail: side is guessed by similarity, and the file filter only sees the top 50 hits.
        on_file = [h for h in hits if f"|{file_path}|" in h["file_paths"]]
        for h in (on_file or hits)[:TOP_K]:
            ctx.setdefault(h["id"], h)


def format_context(ctx: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"[{h['side']}] {h['type']} #{h['source_id']}\n{h['content']}" for h in ctx
    ) or "(no history found)"
