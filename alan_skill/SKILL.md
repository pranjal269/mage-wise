---
name: magewise-resolve-conflict
description: Resolve a Git merge or rebase conflict using the repo's PR, commit, issue and review history. Use whenever a merge or rebase leaves conflict markers (<<<<<<<, =======, >>>>>>>) instead of stopping to ask a human.
---

# Magewise: resolve a merge conflict

Magewise looks up why each side changed the code, then proposes a resolution. It only rewrites the conflicted hunk.

## When

A merge or rebase leaves conflict markers in a file.

## How

For each conflicted file, send the conflict markers to the Magewise server (`MAGEWISE_URL`, default `http://localhost:8000`):

```bash
curl -s -X POST "${MAGEWISE_URL:-http://localhost:8000}/resolve" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "owner/name",
    "pr_number": 482,
    "file_path": "src/auth/session.py",
    "conflict_markers": "<<<<<<< HEAD\n...\n=======\n...\n>>>>>>> feature-branch"
  }'
```

## Reading the response

| `action_taken` | What happened | What you do |
|---|---|---|
| `auto_committed` | Textual-only conflict, tests passed, Magewise committed the resolved hunk. | Pull and continue. |
| `posted_for_review` | Semantic conflict, or tests failed. Magewise commented on the PR with both intents. No commit. | Stop on this file and surface `reasoning`. Do not guess a merge. |

`classification` is `textual-only` or `semantic`. `resolution` is the merged hunk, or `null` for semantic conflicts. `test_result` is `passed`, `failed` or `not_run`.

## Rules

- Never hand-merge a conflict Magewise marked `semantic`. A human has to choose.
- Magewise never auto-merges the PR. It only commits the resolved hunk.
