---
name: magewise-resolve-conflict
description: Resolve a Git merge or rebase conflict using the repo's PR, commit, issue and review history. Use whenever a merge or rebase leaves conflict markers (<<<<<<<, =======, >>>>>>>) instead of stopping to ask a human.
---

# Magewise: resolve a merge conflict

Magewise looks up why each side changed the code, then proposes a resolution for one conflict hunk. It never writes to your repo: you apply the result and run the tests.

## Setup (once)

1. The `magewise` MCP server must be available (`magewise-mcp`, see the Magewise README).
2. Call `index_repo` with `repo: "owner/name"` once per repo. It can take several minutes.
3. Run `git config merge.conflictstyle diff3` so conflict markers include the common ancestor (`|||||||` section). Magewise is much more accurate with it.

## When

A merge or rebase leaves conflict markers in a file.

## How

For each conflict hunk (from `<<<<<<<` to `>>>>>>>`), call the MCP tool `resolve_conflict`:

- `repo`: `owner/name`
- `file_path`: path of the conflicted file
- `conflict_markers`: that one hunk, verbatim
- `pr_number`: the PR being merged, if there is one

If MCP is unavailable, `POST $MAGEWISE_URL/resolve` (default `http://localhost:8000`) with the same fields.

## Reading the response

| `classification` | Meaning | What you do |
|---|---|---|
| `textual-only` | Both sides changed independent things. `resolution` is the code that replaces the whole hunk. | Replace the hunk, run the tests, commit if they pass. |
| `semantic` | Both sides changed the same behavior differently. `resolution` is `null`. | Stop on this file. Show `reasoning` to a human. Do not guess a merge. |

`reasoning` states what each side was trying to do. `sources` lists the PRs, review comments and issues it relied on.

## Rules

- Never hand-merge a conflict Magewise marked `semantic`. A human has to choose.
- Magewise may be wrong. Always run the tests before committing a `textual-only` resolution.
- One hunk per call. A file with several hunks needs several calls.
