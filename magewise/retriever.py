import re

TOP_K = 5


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


def _hits(res, side):
    return [
        {"id": i, "side": side, "content": d, **m}
        for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
    ]


def retrieve(repo: str, pr_number: int | None, file_path: str, conflict_markers: str) -> list[dict]:
    """F2: history for both sides of the conflict, plus issues they link to."""
    from .indexer import collection

    ours, _, theirs = parse_conflict(conflict_markers)
    col = collection(repo)
    if not col.count():
        return []

    ctx = {h["id"]: h for h in _hits(_get(col, [f"pr-{pr_number}"] if pr_number else []), "theirs (this PR)")}
    for side, code in (("ours", ours), ("theirs", theirs)):
        res = col.query(query_texts=[f"{file_path}\n{code}"], n_results=min(50, col.count()))
        hits = _hits({k: res[k][0] for k in ("ids", "documents", "metadatas")}, side)
        # ponytail: side is guessed by similarity, and the file filter only sees the top 50 hits.
        # Use git blame on each side's lines if retrieval misses the right PRs.
        on_file = [h for h in hits if f"|{file_path}|" in h["file_paths"]]
        for h in (on_file or hits)[:TOP_K]:
            ctx.setdefault(h["id"], h)

    linked = {f"issue-{x}" for h in ctx.values() for x in h["linked_ids"].strip("|").split("|") if x}
    for h in _hits(_get(col, sorted(linked)), "linked"):
        ctx.setdefault(h["id"], h)
    return list(ctx.values())


def format_context(ctx: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"[{h['side']}] {h['type']} #{h['source_id']}\n{h['content']}" for h in ctx
    ) or "(no history found)"


if __name__ == "__main__":
    two = "<<<<<<< HEAD\na = 1\n=======\na = 2\n>>>>>>> feat\n"
    assert parse_conflict(two) == ("a = 1\n", "", "a = 2\n")
    diff3 = "x\r\n<<<<<<< HEAD\na = 1\n||||||| base\na = 0\n=======\n>>>>>>> feat\n"
    assert parse_conflict(diff3) == ("a = 1\n", "a = 0\n", "")
    try:
        parse_conflict("no markers")
        raise AssertionError
    except ValueError:
        pass
    print("ok")
