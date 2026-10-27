"""Find the commits that actually produced each side of a conflict, from a local repo.

For each side, `git log -L` (blame across history) lists the commits since the merge base that
touched exactly that side's lines; for the base, the commits before the merge base that made those
lines what they were. Their messages are the real "why", and their #123 references point at the
PRs to pull from the index. Needs a local checkout; hosted mode falls back to similarity search.
"""
import re
import subprocess

LIMIT = 5
BASE_LIMIT = 3


def _git(repo_dir: str, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", repo_dir, *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return out.stdout if out.returncode == 0 else ""


def _line_range(repo_dir: str, ref: str, file_path: str, side_text: str) -> tuple[int, int] | None:
    """1-based line range of this side's hunk text in the file as it is at `ref`, if it can be located."""
    if not side_text.strip():
        return None
    content = _git(repo_dir, "show", f"{ref}:{file_path}").replace("\r\n", "\n")
    i = content.find(side_text)
    if i < 0 or content.find(side_text, i + 1) >= 0:  # missing or ambiguous
        return None
    start = content.count("\n", 0, i) + 1
    return start, start + side_text.count("\n") - 1


def side_commits(
    repo_dir: str,
    ours_ref: str,
    theirs_ref: str,
    file_path: str,
    ours: str,
    theirs: str,
    base_text: str = "",
    base_limit: int = BASE_LIMIT,
) -> list[dict]:
    """Context documents for one hunk, newest first:

    - "ours" / "theirs": commits since the merge base that touched that side's lines (LIMIT per side).
    - "base history": commits before the merge base that shaped the base version of those lines
      (base_limit of them), i.e. why the code looked the way it did before either side changed it.
      Needs the base text (diff3 markers); 0 turns it off.
    """
    base = _git(repo_dir, "merge-base", ours_ref, theirs_ref).strip()
    if not base:
        return []
    fmt = ["log", "--no-patch", "--format=%H%x00%cI%x00%B%x1e"]
    docs = []
    for side, ref, text in (("ours", ours_ref, ours), ("theirs", theirs_ref, theirs)):
        rng = _line_range(repo_dir, ref, file_path, text)
        if rng:
            log = _git(repo_dir, *fmt, f"-n{LIMIT}", f"-L{rng[0]},{rng[1]}:{file_path}", f"{base}..{ref}")
        else:  # deleted lines or text not found: every commit on this side that touched the file
            log = _git(repo_dir, *fmt, f"-n{LIMIT}", f"{base}..{ref}", "--", file_path)
        docs += _docs(repo_dir, log, side, ref, file_path)
    # No file-level fallback here: the whole file's history before the merge base would be noise.
    if base_limit and (rng := _line_range(repo_dir, base, file_path, base_text)):
        log = _git(repo_dir, *fmt, f"-n{base_limit}", f"-L{rng[0]},{rng[1]}:{file_path}", base)
        docs += _docs(repo_dir, log, "base history", base, file_path)
    return docs


def _docs(repo_dir: str, log: str, side: str, ref: str, file_path: str) -> list[dict]:
    docs = []
    for record in filter(str.strip, log.split("\x1e")):
        sha, date, body = record.strip("\n").split("\x00", 2)
        refs = set(re.findall(r"#(\d+)", body)) | set(_pr_merges(repo_dir, sha, ref))
        docs.append({
            "id": f"commit-{sha[:10]}",
            "side": side,
            "type": "commit",
            "source_id": sha[:10],
            "content": body.strip()[:2000],
            "timestamp": date,
            "file_paths": f"|{file_path}|",
            "linked_ids": "|" + "|".join(sorted(refs)) + "|",
        })
    return docs


def _pr_merges(repo_dir: str, sha: str, ref: str) -> list[str]:
    """PR number of the first "Merge pull request #N" merge that brought `sha` into `ref`, if any."""
    subjects = _git(repo_dir, "log", "--ancestry-path", "--merges", "--reverse", "--format=%s", f"{sha}..{ref}")
    m = re.search(r"^Merge pull request #(\d+)", subjects, re.M)
    return [m.group(1)] if m else []


def merge_refs(repo_dir: str) -> tuple[str, str] | None:
    """(ours, theirs) refs if a merge is in progress in repo_dir."""
    theirs = _git(repo_dir, "rev-parse", "-q", "--verify", "MERGE_HEAD").strip()
    return ("HEAD", theirs) if theirs else None
