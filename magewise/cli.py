"""magewise resolve: resolve the conflict hunks Git left in the working tree.

Textual-only hunks are replaced with Magewise's merge (with --write); semantic ones are left as
conflict markers for a human. Exits 1 if any hunk still needs a human.
"""
import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from . import core, indexer
from .retriever import hunks


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _github_repo() -> str:
    url = _git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not m:
        sys.exit(f"origin is not a GitHub remote ({url}); pass --repo owner/name")
    return m.group(1)


def _resolve(repo: str, root: str, path: str, hunk: str) -> dict:
    try:
        return core.resolve(repo, path, hunk, repo_path=root)
    except Exception as e:  # a failed hunk is reported as needing a human, never silently dropped
        return {"classification": "error", "resolution": None, "reasoning": f"{type(e).__name__}: {e}", "sources": []}


def resolve(args) -> int:
    root = _git("rev-parse", "--show-toplevel")
    repo = args.repo or _github_repo()
    files = args.files or _git("-C", root, "diff", "--name-only", "--diff-filter=U").split()
    if not files:
        print("No conflicted files.")
        return 0

    jobs = []
    for f in files:
        text = open(os.path.join(root, f), encoding="utf-8", newline="").read()  # keep CRLF as-is
        jobs += [(f, text, h) for h in hunks(text)]
    print(f"Resolving {len(jobs)} hunk(s) in {len(files)} file(s) against {repo} (30s-2min each)...\n")
    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(lambda j: _resolve(repo, root, j[0], j[2]), jobs))

    texts = {f: t for f, t, _ in jobs}
    pending = 0
    for (f, _, hunk), r in zip(jobs, results):
        ok = r["classification"] == "textual-only"
        pending += not ok
        print(f"{'RESOLVED' if ok else 'NEEDS HUMAN'}  {f}  ({r['classification']})")
        print("  " + r["reasoning"].replace("\n", "\n  "))
        if r["sources"]:
            print(f"  sources: {', '.join(r['sources'])}")
        if ok:
            merged = r["resolution"].replace("\r\n", "\n")
            if "\r\n" in hunk:  # model output is LF; match the file's line endings
                merged = merged.replace("\n", "\r\n")
            texts[f] = texts[f].replace(hunk, merged, 1)
            if not args.write:
                print("  proposed:\n    " + r["resolution"].rstrip("\n").replace("\n", "\n    "))
        print()

    if args.write:
        for f, t in texts.items():
            with open(os.path.join(root, f), "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
        print(f"Wrote resolutions. Run your tests before committing.")
    else:
        print("Dry run: nothing written. Re-run with --write to apply the resolved hunks.")
    print(f"{len(jobs) - pending} resolved, {pending} need a human.")
    return 1 if pending else 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="magewise", description="Intent-aware merge conflict resolver.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve conflict hunks in the working tree")
    r.add_argument("files", nargs="*", help="conflicted files (default: all, repo-relative)")
    r.add_argument("--repo", help="owner/name (default: from the origin remote)")
    r.add_argument("--write", action="store_true", help="write resolved hunks to the files")
    r.add_argument("--workers", type=int, default=4)
    i = sub.add_parser("index", help="index a GitHub repo's history")
    i.add_argument("repo", nargs="?", help="owner/name (default: from the origin remote)")
    i.add_argument("--since", help="YYYY-MM-DD")
    i.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()

    if args.cmd == "index":
        print(f"Indexed {indexer.index_repo(args.repo or _github_repo(), args.since, args.limit)} documents.")
    else:
        sys.exit(resolve(args))


if __name__ == "__main__":
    main()
