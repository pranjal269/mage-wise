"""Replay real historical merge conflicts through Magewise and score against what the maintainer committed.

    python eval/harness.py <path-to-local-clone> [--repo owner/name] [--max-hunks 40] [--workers 4] [--history git|semantic|none]

For each merge commit in the clone's history (newest first) whose parents conflict in a .py file,
the conflict is recreated with diff3 markers, each hunk goes through Magewise with history limited
to documents older than the merge, and the result is compared to the maintainer's resolved hunk.
Model calls are cached in eval/results-<history>.json, so reruns only pay for new hunks.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magewise import core, githistory, resolver  # noqa: E402
from magewise.retriever import HUNK, hunks, parse_conflict  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_BUMP = re.compile(r"__version__|^\s*version\s*=", re.M)
MAX_HUNK_LINES = 120
MAX_HUNKS_PER_FILE = 6


def git(repo_dir: str, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", "-C", repo_dir, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=check
    ).stdout


def reproduce(repo_dir: str, merge_sha: str) -> tuple[dict[str, str], dict[str, str]]:
    """Recreate the merge from its parents. Returns ({file: text with conflict markers}, {file: maintainer's resolved text})."""
    p1, p2 = git(repo_dir, "rev-list", "--parents", "-n1", merge_sha).split()[1:3]
    git(repo_dir, "checkout", "-q", "--detach", p1)
    try:
        git(repo_dir, "-c", "merge.conflictstyle=diff3", "merge", "--no-commit", "--no-ff", p2, check=False)
        files = git(repo_dir, "diff", "--name-only", "--diff-filter=U").split()
        paths = {f: os.path.join(repo_dir, f) for f in files}
        # Modify/delete conflicts leave no file in the worktree: nothing to resolve hunk-by-hunk.
        conflicted = {f: open(p, encoding="utf-8", errors="replace").read() for f, p in paths.items() if os.path.isfile(p)}
    finally:
        git(repo_dir, "merge", "--abort", check=False)
        git(repo_dir, "reset", "-q", "--hard", check=False)  # some old merges leave an index --abort can't undo
    return conflicted, {f: git(repo_dir, "show", f"{merge_sha}:{f}", check=False) for f in files}


def maintainer_hunks(conflicted: str, resolved: str) -> list[str] | None:
    """What the maintainer put in place of each hunk, assuming they left the rest of the file as Git merged it.

    None if the file was also edited outside the hunks (an "evil merge"), since then there's no per-hunk truth.
    """
    segments = HUNK.split(conflicted)
    pattern = "(.*?)".join(re.escape(s) for s in segments)
    m = re.fullmatch(pattern, resolved, re.S)
    return list(m.groups()) if m else None


def norm(code: str | None) -> str | None:
    """Ignore trailing whitespace and leading/trailing blank lines."""
    return None if code is None else "\n".join(line.rstrip() for line in code.strip("\n").splitlines())


def conflicted_py_files(repo_dir: str, merge_sha: str) -> list[str]:
    p1, p2 = git(repo_dir, "rev-list", "--parents", "-n1", merge_sha).split()[1:3]
    out = subprocess.run(
        ["git", "-C", repo_dir, "merge-tree", "--write-tree", "--name-only", p1, p2],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 1:  # 0 = clean merge, >1 = error
        return []
    files = out.stdout.split("\n\n")[0].splitlines()[1:]
    return [f for f in files if f.endswith(".py")]


def collect(repo_dir: str, max_hunks: int) -> list[dict]:
    """Walk merges newest-first and gather scorable .py conflict hunks."""
    cases = []
    # reproduce() moves HEAD, so walk from the default branch, not from wherever HEAD was left.
    ref = git(repo_dir, "rev-parse", "--abbrev-ref", "origin/HEAD", check=False).strip() or "HEAD"
    for sha in git(repo_dir, "log", "--merges", "--format=%H", ref).split():
        if len(cases) >= max_hunks:
            break
        if not conflicted_py_files(repo_dir, sha):
            continue
        try:
            conflicted, resolved = reproduce(repo_dir, sha)
        except subprocess.CalledProcessError:  # e.g. a path this OS can't check out (":" on Windows)
            continue
        merged_at = datetime.fromisoformat(git(repo_dir, "log", "-1", "--format=%cI", sha).strip())
        for f, text in conflicted.items():
            hs = hunks(text)
            truths = maintainer_hunks(text, resolved[f]) if f.endswith(".py") and len(hs) <= MAX_HUNKS_PER_FILE else None
            if truths is None or len(truths) != len(hs):
                continue
            for i, (h, truth) in enumerate(zip(hs, truths)):
                if VERSION_BUMP.search(h) or h.count("\n") > MAX_HUNK_LINES:
                    continue
                ours, base, theirs = parse_conflict(h)
                p1, p2 = git(repo_dir, "rev-list", "--parents", "-n1", sha).split()[1:3]
                cases.append({
                    "commits": githistory.side_commits(repo_dir, p1, p2, f, ours, theirs, base),
                    "id": f"{sha[:10]}:{f}:{i}",
                    "merge": sha,
                    "file": f,
                    "before": merged_at.astimezone(timezone.utc).isoformat(),
                    "hunk": h,
                    "truth": truth,
                    "ours": ours,
                    "theirs": theirs,
                    "maintainer_took": "ours" if norm(truth) == norm(ours)
                    else "theirs" if norm(truth) == norm(theirs)
                    else "base" if norm(truth) == norm(base)
                    else "combined",
                })
    git(repo_dir, "checkout", "-q", "--detach", ref)
    return cases[:max_hunks]


def run_case(case: dict, repo: str, history: str) -> dict:
    try:
        if history in ("git", "git-shallow"):
            commits = case["commits"]
            if history == "git-shallow":  # the earlier behavior: only commits since the merge base
                commits = [c for c in commits if c["side"] != "base history"]
            out = core.resolve(repo, case["file"], case["hunk"], before=case["before"], commits=commits)
        elif history == "semantic":
            out = core.resolve(repo, case["file"], case["hunk"], before=case["before"])
        else:
            v = resolver.resolve_hunk(case["file"], case["hunk"], [])
            out = {"classification": v["label"], "resolution": v["resolution"], "reasoning": v.get("reason", ""),
                   "sources": [], "model": v.get("model")}
    except Exception as e:  # one bad call shouldn't sink a 40-hunk run; it's recorded and retried next run
        return {"error": f"{type(e).__name__}: {e}"}
    return out


def score(cases: list[dict], results: dict) -> dict:
    rows = []
    for c in cases:
        r = results.get(c["id"])
        if not r or "error" in r:
            continue
        resolved = r["classification"] == "textual-only"
        rows.append({
            **c,
            **r,
            "outcome": ("match" if norm(r["resolution"]) == norm(c["truth"]) else "mismatch") if resolved else "deferred",
        })
    n = len(rows)
    count = lambda pred: sum(1 for x in rows if pred(x))
    resolved = count(lambda x: x["outcome"] != "deferred")
    return {
        "rows": rows,
        "total": n,
        "resolved": resolved,
        "match": count(lambda x: x["outcome"] == "match"),
        "mismatch": count(lambda x: x["outcome"] == "mismatch"),
        "deferred": n - resolved,
        "take_ours": count(lambda x: x["maintainer_took"] == "ours"),
        "take_theirs": count(lambda x: x["maintainer_took"] == "theirs"),
        "combined": count(lambda x: x["maintainer_took"] == "combined"),
    }


HISTORY_MODES = {
    "git": "history from the commits behind each side and behind the base (git log -L), and the PRs they reference",
    "git-shallow": "history from the commits behind each side since the merge base (git log -L) and their PRs",
    "semantic": "history from similarity search over the index",
    "none": "no history (ablation)",
}


def report(s: dict, repo: str, history: str) -> str:
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"
    lines = [
        f"# Magewise eval: {repo}, {HISTORY_MODES[history]}",
        "",
        f"Real merge conflicts from {repo}'s history, recreated from each merge's parents and scored against the maintainer's resolution.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Conflict hunks evaluated | {s['total']} |",
        f"| Resolved automatically (textual-only) | {s['resolved']} ({pct(s['resolved'], s['total'])}) |",
        f"| ...matching the maintainer exactly | **{s['match']} / {s['resolved']} ({pct(s['match'], s['resolved'])})** |",
        f"| ...not matching | {s['mismatch']} |",
        f"| Deferred to a human (semantic) | {s['deferred']} |",
        f"| Baseline \"always take ours\" | {s['take_ours']} / {s['total']} ({pct(s['take_ours'], s['total'])}) |",
        f"| Baseline \"always take theirs\" | {s['take_theirs']} / {s['total']} ({pct(s['take_theirs'], s['total'])}) |",
        f"| Maintainer combined both sides | {s['combined']} / {s['total']} |",
        "",
        "Matching ignores trailing whitespace and leading/trailing blank lines. History is limited to what existed before each merge.",
        "",
        "| Hunk | Maintainer took | Magewise | Outcome |",
        "|---|---|---|---|",
    ]
    for r in s["rows"]:
        lines.append(f"| `{r['id']}` | {r['maintainer_took']} | {r['classification']} | {r['outcome']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clone", help="path to a local clone of the repo")
    ap.add_argument("--repo", default=os.environ.get("DEMO_REPO"), help="owner/name of the indexed repo")
    ap.add_argument("--max-hunks", type=int, default=40)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--history", choices=HISTORY_MODES, default="git", help="where resolution context comes from")
    ap.add_argument("--label", default="", help="cache/report name suffix, e.g. the model (set LLM_PROVIDERS to pin it)")
    args = ap.parse_args()
    history = args.history
    suffix = f"-{history}" + (f"-{args.label}" if args.label else "")
    cache_path = os.path.join(HERE, f"results{suffix}.json")

    cases = collect(args.clone, args.max_hunks)
    print(f"{len(cases)} scorable hunks", flush=True)
    results = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [c for c in cases if c["id"] not in results or "error" in results[c["id"]]]
    lock = threading.Lock()

    def work(case):
        r = run_case(case, args.repo, history)
        with lock:
            results[case["id"]] = r
            json.dump(results, open(cache_path, "w"), indent=1)
            print(f"[{sum(1 for c in cases if c['id'] in results)}/{len(cases)}] {case['id']}: {r.get('classification', r.get('error'))}", flush=True)

    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(work, todo))

    s = score(cases, results)
    md = report(s, args.repo, history)
    open(os.path.join(HERE, f"results{suffix}.md"), "w", encoding="utf-8").write(md)
    print(md)


if __name__ == "__main__":
    main()
