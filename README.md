# Magewise

Intent-aware merge conflict resolver. When Git flags a conflict, Magewise retrieves why each side changed the code (PR descriptions, commits, issues, review comments), proposes a resolution that honors both, tests it, and either commits it or explains the tradeoff for a human.

## Problem

Git merges text, not intent. Resolving a conflict means reconstructing why two changes were made, and agents now open PRs faster than humans can read the history behind them.

## Approach

`index` (GitHub history into ChromaDB) → `retrieve` → `classify` (textual-only vs semantic) → `propose` → `test` → `commit` or `comment`.

Textual-only and tests pass: commit the resolved hunk. Semantic or tests fail: post both intents on the PR, no commit.

## Run

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
uvicorn server.main:app --env-file .env

curl -X POST localhost:8000/index -H "Content-Type: application/json" -d '{"repo": "owner/name"}'
```

## Alan skill

`alan_skill/SKILL.md` tells an Alan agent to call `/resolve` when it hits a conflict.

## Eval

`python eval/harness.py` replays historical conflicts and scores against the maintainer's real resolution. Result: _TBD_.
