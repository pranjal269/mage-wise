# Magewise

**Intent-aware merge conflict resolution for coding agents.**

Git merges text. It has no idea *why* two branches changed the same lines, so every conflict sends someone digging through PRs, commits and issues to reconstruct intent. Agents now open PRs faster than humans can do that.

Magewise does the digging. For each conflict hunk it retrieves the history behind both sides (PR descriptions, commit messages, review comments, linked issues), works out what each side was trying to do, and then either:

- **textual-only**: both sides changed independent things → returns a merged hunk that keeps both, or
- **semantic**: both sides changed the same behavior differently → returns no merge, only both intents, so a human decides.

It never writes to your repo by itself, and anything it can't trust (unparseable model output, leftover markers) is treated as *semantic*.

Ships as an **MCP server** (stdio or streamable HTTP), a **CLI**, a **REST API**, and an **Alan skill**.

## Results

Replayed against **40 real conflict hunks from 20 merge commits** in [pallets/flask](https://github.com/pallets/flask)'s history, scored against what the maintainer actually committed:

| | |
|---|---|
| Hunks Magewise resolved automatically | **23 / 40 (58%)** |
| ...of those, identical to the maintainer's resolution | **18 / 23 (78%)** |
| Deferred to a human as semantic | 17 / 40 |
| Baseline: always take "ours" / always take "theirs" | 15% / 12% |
| Maintainer needed to combine both sides | 29 / 40 (73%) |

Taking either side wins 12–15% of the time because in most real conflicts the maintainer had to keep both sides' changes. Of the 5 resolved hunks that didn't match exactly, 3 differ only in formatting (quote style, trailing comma) and 2 are genuine errors. Matching is strict: whitespace-insensitive, otherwise exact. The 40 hunks are all the scorable ones found, not a hand-picked set, but several come from the same merge, so they are not independent samples.

**Does the history lookup help?** We re-ran the same 40 hunks with no retrieved history (`--no-history`):

| | With history | Without |
|---|---|---|
| Resolved automatically | 23 | 28 |
| Identical to the maintainer | 18 | 20 |
| Resolved but wrong | **5** | 8 |
| Precision (identical / resolved) | **78%** | 71% |

History did not increase the number of correct resolutions. It made Magewise more cautious: it deferred 5 more hunks to a human and made fewer wrong auto-resolutions. On a sample this small, treat that as a modest safety benefit, not a proven accuracy gain. Most of the lift over the "take a side" baselines is present even without history, so it comes from the model reading the conflict itself (with the common-ancestor section from diff3 markers), not from retrieval.

Full per-hunk table: [eval/results.md](eval/results.md).

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
magewise resolve            # dry run: shows what it would do for every hunk
magewise resolve --write    # writes textual-only resolutions; semantic hunks keep their markers
```

Exits 1 if any hunk still needs a human.

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
conflict hunk --> retrieve history for both sides ---+
              --> one model call: intents + label (+ merged hunk if textual-only)
              --> validate (parseable, no leftover markers) --> response
```

- **Retrieval** prefers documents that touched the conflicted file and are semantically close to each side's code, plus issues they link to.
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
python eval/harness.py /tmp/flask --repo pallets/flask --max-hunks 40 --no-history   # ablation
```

## Development

```bash
pip install -e ".[dev]"
pytest -q tests
```

## Limitations

- History attribution is approximate: documents are matched to each side by similarity, not `git blame`.
- One hunk per call; hunk quality depends on the model. Always run tests before committing a resolution.
- Hosted Nemotron latency varies from seconds to ~2 minutes per call.
