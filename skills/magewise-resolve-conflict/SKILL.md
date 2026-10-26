---
name: magewise-resolve-conflict
description: Resolve a Git merge or rebase conflict using the repo's PR, commit, issue and review history. Use whenever a merge or rebase leaves conflict markers (<<<<<<<, =======, >>>>>>>) instead of stopping to ask a human.
---

# Magewise: resolve a merge conflict

Magewise looks up why each side changed the code, then proposes a resolution for one conflict hunk. It never writes to your repo: you apply the result and run the tests.

## Setup (once)

1. Connect the `magewise` MCP server: either the local command `magewise-mcp`, or a hosted URL (`https://<host>/mcp` with header `Authorization: Bearer <MAGEWISE_TOKEN>`). In Alan: Settings → team → Plugins → MCP → Add custom connector.
2. Call `index_repo` with `repo: "owner/name"` once per repo. It can take several minutes.
3. Run `git config merge.conflictstyle diff3` in the repo so conflict markers include the common ancestor (`|||||||` section). Magewise is much more accurate with it.

## When

A merge or rebase leaves conflict markers in a file.

## How

For each conflict hunk (from `<<<<<<<` to `>>>>>>>`), call the MCP tool `resolve_conflict`:

- `repo`: `owner/name`
- `file_path`: path of the conflicted file
- `conflict_markers`: that one hunk, verbatim, including the marker lines
- `pr_number`: the PR being merged, if there is one
- `repo_path`: absolute path of the checkout where the merge is in progress, if Magewise runs locally (`magewise-mcp` over stdio). It lets Magewise read the exact commits behind each side. Omit it for a hosted server.

A call takes 30 seconds to 2 minutes. Calls for different hunks can run in parallel.

If the MCP server isn't connected, `POST $MAGEWISE_URL/resolve` with the same fields as JSON.

## Reading the response

| `classification` | Meaning | What you do |
|---|---|---|
| `textual-only` | Both sides changed independent things. `resolution` is the code that replaces the whole hunk. | Replace the hunk (marker lines included) with `resolution`, run the tests, commit if they pass. |
| `semantic` | Both sides changed the same behavior differently, or Magewise isn't confident. `resolution` is `null`. | Leave this hunk. Show `reasoning` to a human. Do not guess a merge. |

`reasoning` states what each side was trying to do. `sources` lists the PRs, review comments and issues it relied on; cite them when you explain the resolution.

## Rules

- Never hand-merge a hunk Magewise marked `semantic`. A human has to choose.
- Magewise can be wrong. Always run the tests before committing a `textual-only` resolution.
- One hunk per call. A file with several hunks needs several calls.
- If a test fails after applying a resolution, revert that hunk to its conflict markers and report it as needing a human.
