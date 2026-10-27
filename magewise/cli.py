"""magewise resolve: resolve the conflict hunks Git left in the working tree.

Textual-only hunks are replaced with Magewise's merge (with --write); semantic ones are left as
conflict markers for a human. With --test, the resolutions are kept only if the tests pass.
Exits 1 if any hunk still needs a human or the tests failed.
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

    originals = {f: t for f, t, _ in jobs}
    changed = {f: t for f, t in texts.items() if t != originals[f]}
    tests_ok = True
    if changed and (args.write or args.test):
        _write(root, changed)
        if args.test:
            tests_ok = _run_tests(root, args.test, args.test_timeout)
        # Dry runs always roll back; a failed test run rolls back unless asked to keep the result.
        if not args.write or not (tests_ok or args.keep_on_fail):
            _write(root, {f: originals[f] for f in changed})
            print("Rolled back: files are back to their conflict markers.")
        else:
            print("Wrote resolutions." + ("" if args.test else " Run your tests before committing."))
    elif not args.write:
        print("Dry run: nothing written. Re-run with --write to apply the resolved hunks.")
    print(f"{len(jobs) - pending} resolved, {pending} need a human.")
    return 1 if pending or not tests_ok else 0


def _write(root: str, texts: dict[str, str]) -> None:
    for f, t in texts.items():
        with open(os.path.join(root, f), "w", encoding="utf-8", newline="") as fh:
            fh.write(t)


def _run_tests(root: str, command: str, timeout: int) -> bool:
    """Run the user's test command with resolutions applied. True if it exits 0."""
    print(f"Running tests: {command}")
    try:
        out = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"TESTS TIMED OUT after {timeout}s.")
        return False
    tail = "\n".join((out.stdout + out.stderr).strip().splitlines()[-25:])
    print(("TESTS PASSED" if out.returncode == 0 else f"TESTS FAILED (exit {out.returncode})") + "\n  "
          + tail.replace("\n", "\n  "))
    return out.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="magewise", description="Intent-aware merge conflict resolver.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve conflict hunks in the working tree")
    r.add_argument("files", nargs="*", help="conflicted files (default: all, repo-relative)")
    r.add_argument("--repo", help="owner/name (default: from the origin remote)")
    r.add_argument("--write", action="store_true", help="write resolved hunks to the files")
    r.add_argument("--test", metavar="CMD", help='test command run with resolutions applied, e.g. "pytest -q"; '
                   "on failure the files are rolled back (without --write, always rolled back)")
    r.add_argument("--keep-on-fail", action="store_true", help="with --write --test: keep resolutions even if tests fail")
    r.add_argument("--test-timeout", type=int, default=1800, help="seconds before the test run counts as failed")
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
