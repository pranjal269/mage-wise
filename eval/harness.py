"""Replay historical merge-conflict resolutions through /resolve and score against the maintainer's commit.

1. Find merge commits in DEMO_REPO whose resolution diff is non-trivial.
2. Reproduce each conflict from the two parents.
3. POST /resolve, diff the result against the real resolution, run the tests at that commit.
4. Print per-conflict scores and the headline "X / Y matched or passed".
"""
import os
import re
import subprocess

HUNK = re.compile(r"^<{7} [^\n]*\n.*?^>{7}[^\n]*\n", re.S | re.M)


def git(repo_dir: str, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", "-C", repo_dir, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=check
    ).stdout


def reproduce(repo_dir: str, merge_sha: str) -> tuple[dict[str, str], dict[str, str]]:
    """Recreate the merge from its parents. Returns ({file: text with conflict markers}, {file: maintainer's resolved text})."""
    p1, p2 = git(repo_dir, "rev-list", "--parents", "-n1", merge_sha).split()[1:3]
    git(repo_dir, "checkout", "-q", "--detach", p1)
    git(repo_dir, "-c", "merge.conflictstyle=diff3", "merge", "--no-commit", "--no-ff", p2, check=False)
    files = git(repo_dir, "diff", "--name-only", "--diff-filter=U").split()
    conflicted = {f: open(os.path.join(repo_dir, f), encoding="utf-8", errors="replace").read() for f in files}
    git(repo_dir, "merge", "--abort", check=False)
    return conflicted, {f: git(repo_dir, "show", f"{merge_sha}:{f}", check=False) for f in files}


def hunks(text: str) -> list[str]:
    return HUNK.findall(text)


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
