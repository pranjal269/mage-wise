---
name: magewise-resolve-conflict
description: Resolve Git merge or rebase conflicts using the repo's PR, commit, issue and review history. Use whenever a merge or rebase leaves conflict markers (<<<<<<<, =======, >>>>>>>) instead of stopping to ask a human.
---

# Magewise: resolve merge conflicts

Magewise looks up why each side changed the code, then resolves the conflict hunks it can merge safely and leaves the rest for a human. It never writes to your repo: you write the result and run the tests.

## Setup (once)

1. Connect the `magewise` MCP server: either the local command `magewise-mcp`, or a hosted URL (`https://<host>/mcp` with header `Authorization: Bearer <MAGEWISE_TOKEN>`). In Alan: Settings → team → Plugins → MCP → Add custom connector.
2. Call `index_repo` with `repo: "owner/name"` once per repo. It can take several minutes.
3. Run `git config merge.conflictstyle diff3` in the repo so conflict markers include the common ancestor (`|||||||` section). Magewise is much more accurate with it.

## When

A merge or rebase leaves conflict markers in one or more files.

## How

Call the MCP tool `resolve_pr` **once** for the whole merge:

- `repo`: `owner/name`
- Either `repo_path`: absolute path of the checkout where the merge is in progress (local `magewise-mcp` over stdio only; Magewise finds the conflicted files and reads the exact commits behind each side),
- or `files`: `{"path/to/file.py": "<full file content with conflict markers>", ...}` for every conflicted file (`git diff --name-only --diff-filter=U` lists them). Use this with a hosted server.
- `pr_number`: the PR being merged, if there is one

It takes seconds to a few minutes, depending on the number of hunks.

For a single hunk you can call `resolve_conflict` (`repo`, `file_path`, `conflict_markers` = that one hunk verbatim). Without MCP, `POST $MAGEWISE_URL/resolve-pr` with `repo` and `files` as JSON.

## Reading the response

For each file in `files`:

- `content`: the file with every safely resolved hunk applied. Hunks that need a human still have their conflict markers. **Write this back to the file.**
- `hunks`: one entry per hunk, in order, with `classification`, `reasoning`, `sources`, `model`.

| `classification` | Meaning | What you do |
|---|---|---|
| `textual-only` | Both sides changed independent things; already merged in `content`. | Nothing extra; run the tests. |
| `semantic` | Both sides changed the same behavior differently, or Magewise isn't confident. | Leave the markers. Show `reasoning` to a human. Do not guess a merge. |
| `error` | The model call failed. | Treat as needing a human. |

`reasoning` states what each side was trying to do. `sources` lists the commits, PRs, review comments and issues it relied on; cite them when you explain the resolution.

## Rules

- Never hand-merge a hunk Magewise left with markers. A human has to choose.
- Magewise can be wrong. Run the tests after writing the files and before committing.
- If the tests fail, restore that file's conflict markers and report it as needing a human.
- Don't `git add` a file that still contains conflict markers.
