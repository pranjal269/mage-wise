# Magewise

Intent-aware merge conflict resolver. When Git flags a conflict, Magewise retrieves why each side changed the code (PR descriptions, commits, issues, review comments), classifies the conflict, and either proposes a merged hunk that keeps both intents or tells you a human has to decide.

Ships as an **MCP server** (for agents such as Alan) and a REST API.

## Problem

Git merges text, not intent. Resolving a conflict means reconstructing why two changes were made, and agents now open PRs faster than humans can read the history behind them.

## Approach

`index` (GitHub history into ChromaDB) → `retrieve` → `classify` (textual-only vs semantic) → `propose`.

- **textual-only** (both sides changed independent things): returns the merged hunk.
- **semantic** (both sides changed the same behavior differently): returns no resolution, only both intents. A human decides.

Magewise only returns a proposal. The caller applies it and runs the tests.

## Install

```bash
pip install -e .          # or: uvx --from git+https://github.com/pranjal269/mage-wise magewise-mcp
cp .env.example .env      # GITHUB_TOKEN, NVIDIA_API_KEY
```

## Use as an MCP server

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

Tools: `index_repo(repo)` once per repo, then `resolve_conflict(repo, file_path, conflict_markers)` per conflict hunk. Run `git config merge.conflictstyle diff3` first: the common-ancestor section makes classification much more accurate.

## Use as a REST API

```bash
uvicorn magewise.main:app --env-file .env
curl -X POST localhost:8000/index -H "Content-Type: application/json" -d '{"repo": "pallets/flask", "limit": 300}'
```

## Alan skill

`alan_skill/SKILL.md` tells an Alan agent when and how to call Magewise.

## Eval

`python eval/harness.py` replays historical Flask merge conflicts and scores against the maintainer's real resolution. Result: _TBD_.
