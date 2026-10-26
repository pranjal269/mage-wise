"""Replay historical merge-conflict resolutions through /resolve and score against the maintainer's commit.

1. Find merge commits in DEMO_REPO whose resolution diff is non-trivial.
2. Reproduce each conflict from the two parents.
3. POST /resolve, diff the result against the real resolution, run the tests at that commit.
4. Print per-conflict scores and the headline "X / Y matched or passed".
"""


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
