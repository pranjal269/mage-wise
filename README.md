# Magewise

**Intent-aware merge conflict resolution for coding agents.**

Git merges text. It has no idea *why* two branches changed the same lines, so every conflict sends someone digging through PRs, commits and issues to reconstruct intent. Agents now open PRs faster than humans can do that.

Magewise does the digging. For each conflict hunk it retrieves the history behind both sides (PR descriptions, commit messages, review comments, linked issues), works out what each side was trying to do, and then either:

- **textual-only**: both sides changed independent things → returns a merged hunk that keeps both, or
- **semantic**: both sides changed the same behavior differently → returns no merge, only both intents, so a human decides.

It never writes to your repo by itself, and anything it can't trust (unparseable model output, leftover markers) is treated as *semantic*.

Ships as an **MCP server** (stdio or streamable HTTP), a **CLI**, a **REST API**, and an **Alan skill**.

## Results

Replayed against **40 real conflict hunks from 20 merge commits** in [pallets/flask](https://github.com/pallets/flask)'s history, scored against what the maintainer actually committed. Same 40 hunks, three sources of history:

| | Git history (default with a checkout) | Similarity search (hosted) | No history |
|---|---|---|---|
| Resolved automatically | **29 / 40 (72%)** | 23 / 40 (58%) | 28 / 40 (70%) |
| Identical to the maintainer | **22** | 18 | 20 |
| Resolved but different | 7 | **5** | 8 |
| Precision (identical / resolved) | 76% | **78%** | 71% |
| Deferred to a human | 11 | 17 | 12 |

Baselines on the same hunks: always take "ours" 15%, always take "theirs" 12%. The maintainer had to combine both sides in 29 of 40 (73%), which is why picking a side rarely works.

What this shows, and doesn't:

- **Magewise beats picking a side by a wide margin in every mode**, and most of that is there even without history, so it comes from the model reading the conflict with its common ancestor (diff3 markers).
- **Git history gets the most hunks right** (22 vs 20 without history) by finding the actual commits behind each side; for example, it learns that one side of a merge was "Reformat with black". **Similarity search is the most cautious**: fewest wrong answers, but it defers the most.
- The differences between modes are a few hunks on a small, clustered sample (several hunks share a merge), and run-to-run model variance wasn't measured, so none of them is statistically established.
- "Resolved but different" includes formatting-only differences (quote style, trailing commas) and real errors. In git mode, 1 of the 7 is formatting-only by an automatic check, and at least one more is only a line break. The rest are wrong, which is why the CLI can gate resolutions on your tests (`--test`) and the MCP skill tells agents to run tests before committing.

Matching is whitespace-insensitive, otherwise exact. The 40 hunks are all the scorable ones found walking Flask's merges newest-first, not a hand-picked set. History is limited to what existed before each merge.

Per-hunk tables: [git](eval/results-git.md), [similarity](eval/results-semantic.md), [none](eval/results-none.md).

## Install

```bash
pip install git+https://github.com/pranjal269/mage-wise    # or, from a clone: pip install -e .
```

Set `GITHUB_TOKEN` (read access) and `NVIDIA_API_KEY` (open-weights Nemotron via build.nvidia.com; any OpenAI-compatible endpoint works with `LLM_BASE_URL` and `LLM_MODEL`). See [.env.example](.env.example).

Index a repo's history once (a few minutes for 300 PRs):

```bash
magewise index pallets/flask
```

Use diff3 conflict markers so Magewise can see the common ancestor; it is far more accurate with them:

```bash
git config merge.conflictstyle diff3
```

## Use it

### MCP server (agents)

Local (stdio):

```json
{
  "mcpServers": {
    "magewise": {
      "command": "magewise-mcp",
      "env": { "GITHUB_TOKEN": "...", "NVIDIA_API_KEY": "..." }
    }
  }
}
```

**Claude Code:** this repo ships a project-scoped [.mcp.json](.mcp.json). After `pip install`, open the repo in `claude` with `GITHUB_TOKEN` and `NVIDIA_API_KEY` set in your shell, approve the `magewise` server when prompted, and the tools are available.

Hosted (streamable HTTP at `/mcp`, bearer-token auth required on any non-local interface):

```bash
MAGEWISE_TOKEN=<secret> magewise-mcp --http --host 0.0.0.0 --port 8000
# or: docker build -t magewise . && docker run -p 8000:8000 -v magewise-data:/data \
#       -e MAGEWISE_TOKEN=... -e GITHUB_TOKEN=... -e NVIDIA_API_KEY=... magewise
```

Connect clients to `https://<host>/mcp` with header `Authorization: Bearer <secret>`.

Tools:

| Tool | Does |
|---|---|
| `index_repo(repo, since?, limit?)` | Index a GitHub repo's merged PRs, review comments and issues. |
| `resolve_conflict(repo, file_path, conflict_markers, pr_number?)` | Classify one hunk; return `classification`, `resolution` (or `null`), `reasoning`, `sources`. |

Calls take 30s to 2 minutes; the server sends progress notifications every 10s so clients don't time out.

### CLI (humans)

After a merge stops on conflicts:

```bash
magewise resolve                                # dry run: shows what it would do for every hunk
magewise resolve --write                        # writes textual-only resolutions; semantic hunks keep their markers
magewise resolve --write --test "pytest -q"     # keeps the resolutions only if the tests pass
magewise resolve --test "pytest -q"             # preview: apply, test, always roll back
```

With `--test`, a failing run rolls every file back to its conflict markers, so you never end up with a merge that breaks the build (`--keep-on-fail` keeps it for inspection). Exits 1 if any hunk still needs a human or the tests failed.

### REST API

```bash
uvicorn magewise.main:app
curl -X POST localhost:8000/resolve -H "Content-Type: application/json" \
  -d '{"repo": "pallets/flask", "file_path": "src/flask/app.py", "conflict_markers": "<<<<<<< HEAD\n..."}'
```

### Alan

[skills/magewise-resolve-conflict/SKILL.md](skills/magewise-resolve-conflict/SKILL.md) tells an Alan agent when to call Magewise and how to act on the answer. Import it in Alan via **Skills → Import → From GitHub** with this repo's URL, and add the MCP server under **Settings → Plugins → MCP → Add custom connector**.

## How it works

```
GitHub (PRs, commits, reviews, issues) --index--> ChromaDB
                                                     |
conflict hunk --> one side unchanged from base? --yes--> take the other side (no model, no index)
              --> retrieve history for both sides ---+
              --> one model call: intents + label (+ merged hunk if textual-only)
              --> validate (parseable, no leftover markers) --> response
```

- **Retrieval**, with a local checkout (CLI, stdio MCP with `repo_path`): `git log -L` finds the commits since the merge base that touched exactly each side's lines, then the PRs that merged them ("Merge pull request #N" or "(#N)") and the issues those link to. Without a checkout (hosted): similarity search over the index, preferring documents that touched the conflicted file.
- **Free fast path**: with diff3 markers, if one side left the region exactly as it was in the common ancestor, only the other side really changed it, so Magewise takes that side without calling the model or touching the index. It fires on 2 of the 40 eval hunks (both match the maintainer); small, but free and safe.
- **Model**: NVIDIA Nemotron (open weights) through an OpenAI-compatible API, behind one function in [magewise/llm.py](magewise/llm.py).
- **Safety default**: anything ambiguous is classified *semantic*. Magewise proposes, the caller applies and tests.

## Evaluation

[eval/harness.py](eval/harness.py) replays real merge conflicts from a repo's history:

1. Walk the repo's merge commits (newest first) whose parents conflict in a `.py` file.
2. Recreate each conflict from the merge's two parents with diff3 markers.
3. Resolve every hunk with history limited to documents created **before** the merge (no leakage).
4. Compare to the hunk the maintainer actually committed; also report "always take ours/theirs" baselines.

```bash
git clone https://github.com/pallets/flask /tmp/flask
python eval/harness.py /tmp/flask --repo pallets/flask --max-hunks 40
python eval/harness.py /tmp/flask --repo pallets/flask --max-hunks 40 --history semantic   # similarity search only
python eval/harness.py /tmp/flask --repo pallets/flask --max-hunks 40 --history none       # ablation
```

## Development

```bash
pip install -e ".[dev]"
pytest -q tests
```

## License

[MIT](LICENSE)

## Limitations

- Hosted mode has no checkout, so it attributes history to each side by similarity, which is much weaker than the git-based lookup.
- The index holds a repo's most recent PRs (300 by default); older conflicts get commit messages but not their PR discussion.
- MCP: one hunk per call, and the calling agent applies and tests the result. CLI: `--test` rolls back the whole run on failure; it doesn't yet isolate which hunk broke the tests.
- Hosted Nemotron latency varies from seconds to ~2 minutes per call.
