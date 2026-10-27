# Magewise

**Intent-aware merge conflict resolution for coding agents.**

Git merges text. It has no idea *why* two branches changed the same lines, so every conflict sends someone digging through PRs, commits and issues to reconstruct intent. Agents now open PRs faster than humans can do that.

Magewise does the digging. For each conflict hunk it retrieves the history behind both sides (PR descriptions, commit messages, review comments, linked issues), works out what each side was trying to do, and then either:

- **textual-only**: both sides changed independent things → returns a merged hunk that keeps both, or
- **semantic**: both sides changed the same behavior differently → returns no merge, only both intents, so a human decides.

It never writes to your repo by itself, and anything it can't trust (unparseable model output, leftover markers) is treated as *semantic*.

Ships as an **MCP server** (stdio or streamable HTTP), a **CLI**, a **REST API**, and an **Alan skill**.

## Results

Replayed against **40 real conflict hunks from 20 merge commits** in [pallets/flask](https://github.com/pallets/flask)'s history, scored against what the maintainer actually committed. Same 40 hunks, four sources of history:

| | Git, with base history (default with a checkout) | Git, since merge base only | Similarity search (hosted) | No history |
|---|---|---|---|---|
| Resolved automatically | 29 / 40 (72%) | 29 / 40 (72%) | 23 / 40 (58%) | 28 / 40 (70%) |
| Identical to the maintainer | 21 | 22 | 18 | 20 |
| Resolved but different | 8 | 7 | 5 | 8 |
| Precision (identical / resolved) | 72% | 76% | 78% | 71% |
| Deferred to a human | 11 | 11 | 17 | 12 |

Baselines on the same hunks: always take "ours" 15%, always take "theirs" 12%. The maintainer had to combine both sides in 29 of 40 (73%), which is why picking a side rarely works.

What this shows, and doesn't:

- **Magewise beats picking a side by a wide margin in every mode**: 45–55% of all hunks resolved identically to the maintainer, against 12–15% for either baseline. Most of that is there even without history, so it comes from the model reading the conflict with its common ancestor (diff3 markers).
- **The differences between modes are within run-to-run noise.** The two git columns differ only in a few added commit messages, yet 10 of the 40 hunks changed outcome between them, in both directions (wrong → deferred, match → deferred, deferred → wrong). The model's own variance is as large as the gaps between columns, so this eval doesn't show that any history source beats another.
- What history clearly does is make the reasoning explain itself: the git lookup surfaces the real commits behind each side (e.g. one side of a merge was "Reformat with black"), which a reviewer can check.
- "Resolved but different" includes formatting-only differences (quote style, trailing commas) and real errors (6 in each git mode). That is why the CLI can gate resolutions on your tests (`--test`) and the MCP skill tells agents to run tests before committing.

**Model comparison** (same 40 hunks, git history with base history):

| | Resolved automatically | Identical to the maintainer | Resolved but different | Deferred | Speed per call |
|---|---|---|---|---|---|
| Groq `gpt-oss-120b` (default) | 19 | 14 (74% of resolved) | 5 | 21 | 1-5 s |
| NVIDIA Nemotron | 29 | 21 (72%) | 6 | 11 | 8-140 s |

Precision is about the same (74% vs 72%); Groq hands more hunks to a human instead of guessing, and it is much faster. Both get the demo conflicts right. Per-hunk table: [groq](eval/results-git-groq.md).

Matching is whitespace-insensitive, otherwise exact. The 40 hunks are all the scorable ones found walking Flask's merges newest-first, not a hand-picked set. History is limited to what existed before each merge. The base-history run also added one prompt line explaining base-history entries.

Per-hunk tables: [git](eval/results-git.md), [git since merge base](eval/results-git-shallow.md), [similarity](eval/results-semantic.md), [none](eval/results-none.md).

## Install

```bash
pip install git+https://github.com/pranjal269/mage-wise    # or, from a clone: pip install -e .
```

Set `GITHUB_TOKEN` (read access) and at least one model key: `GROQ_API_KEY` (console.groq.com), `NVIDIA_API_KEY` (build.nvidia.com) or `TOGETHER_API_KEY`. All serve open-weights models through OpenAI-compatible APIs. With several keys, Magewise falls back to the next provider when one errors, times out or rate-limits; `LLM_PROVIDERS=groq,nvidia` sets the order, and any other OpenAI-compatible endpoint works via `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. See [.env.example](.env.example).

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
      "env": { "GITHUB_TOKEN": "...", "GROQ_API_KEY": "...", "NVIDIA_API_KEY": "..." }
    }
  }
}
```

**Claude Code:** this repo ships a project-scoped [.mcp.json](.mcp.json). After `pip install`, open the repo in `claude` with `GITHUB_TOKEN` and `GROQ_API_KEY` (or `NVIDIA_API_KEY`) set in your shell, approve the `magewise` server when prompted, and the tools are available.

Hosted (streamable HTTP at `/mcp`, bearer-token auth required on any non-local interface):

```bash
MAGEWISE_TOKEN=<secret> magewise-mcp --http --host 0.0.0.0 --port 8000
# or: docker build -t magewise . && docker run -p 8000:8000 -v magewise-data:/data \
#       -e MAGEWISE_TOKEN=... -e GITHUB_TOKEN=... -e GROQ_API_KEY=... -e NVIDIA_API_KEY=... magewise
```

Connect clients to `https://<host>/mcp` with header `Authorization: Bearer <secret>`.

Tools:

| Tool | Does |
|---|---|
| `index_repo(repo, since?, limit?)` | Index a GitHub repo's merged PRs, review comments and issues. |
| `resolve_pr(repo, files or repo_path, pr_number?)` | Resolve **every** hunk in every conflicted file in one call, in parallel. Returns each file's new `content` (resolved hunks applied, the rest keep their markers) plus per-hunk results. |
| `resolve_conflict(repo, file_path, conflict_markers, pr_number?, repo_path?)` | Classify one hunk; return `classification`, `resolution` (or `null`), `reasoning`, `sources`, `model`. |

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
curl -X POST localhost:8000/resolve-pr -H "Content-Type: application/json" \
  -d '{"repo": "pallets/flask", "files": {"src/flask/app.py": "<file content with conflict markers>"}}'
curl -X POST localhost:8000/resolve -H "Content-Type: application/json" \
  -d '{"repo": "pallets/flask", "file_path": "src/flask/app.py", "conflict_markers": "<<<<<<< HEAD\n..."}'
```

### Alan

[skills/magewise-resolve-conflict/SKILL.md](skills/magewise-resolve-conflict/SKILL.md) tells an Alan agent when to call Magewise and how to act on the answer. Import it in Alan via **Skills → Import → From GitHub** with this repo's URL, and add the MCP server under **Settings → Plugins → MCP → Add custom connector**.

## How it works

```
GitHub (PRs, commits, reviews, issues) --index--> ChromaDB
                                                     |
conflict hunk --> one side byte-identical to base? --yes--> take the other side (no model, no index)
              --> retrieve history for both sides ---+
              --> one model call: intents + label (+ merged hunk if textual-only)
              --> validate (parseable, no leftover markers) --> response
```

- **Retrieval**, with a local checkout (CLI, stdio MCP with `repo_path`): `git log -L` finds the commits since the merge base that touched exactly each side's lines, plus the older commits that made the base version of those lines what it was (why the code looked that way before either side changed it), then the PRs that merged them ("Merge pull request #N" or "(#N)") and the issues those link to. Without a checkout (hosted): similarity search over the index, preferring documents that touched the conflicted file.
- **Free fast path**: with diff3 markers, if one side left the region byte-for-byte as it was in the common ancestor, only the other side changed it, so Magewise takes that side without the model or the index. Git already auto-merges such regions itself, so on Git's own conflicts this rarely fires; it's a lossless safety net. (An earlier version ignored whitespace and could silently drop a side's whitespace-only change, such as a deleted blank line; it now compares exactly.)
- **Model**: open-weights models through OpenAI-compatible APIs, behind one function in [magewise/llm.py](magewise/llm.py). Default order: Groq `gpt-oss-120b` (answers in seconds), then NVIDIA Nemotron if Groq errors or rate-limits (Groq's free tier allows about 8,000 tokens a minute, i.e. 1-2 hunks a minute). The response reports which model answered.
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
python eval/harness.py /tmp/flask --repo pallets/flask --max-hunks 40 --history git-shallow   # no base history
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
- MCP: Magewise returns resolved content; the calling agent writes it and runs the tests. CLI: `--test` rolls back the whole run on failure; it doesn't yet isolate which hunk broke the tests.
- A hosted (HTTP) server refuses `repo_path`, so a remote caller can't make it read repos on the server's own disk; hosted callers send `files` instead and get similarity-search history rather than git history.
- Latency depends on the provider: Groq answers in seconds but its free tier rate-limits after 1-2 hunks a minute (the fallback takes over); NVIDIA's hosted Nemotron varies from seconds to ~2 minutes per call.
