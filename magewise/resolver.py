import re

from .llm import llm
from .retriever import format_context

PROMPT = """Resolve this Git merge conflict in {file_path} so that BOTH intents are kept.

Ours intended: {ours_intent}
Theirs intended: {theirs_intent}

## Conflict
The sections are: ours (<<<<<<< to |||||||), the common ancestor base (||||||| to =======, when present), theirs (======= to >>>>>>>). Apply the changes each side made relative to the base.
{conflict}

## Repository history
{context}

Output only the code that replaces the whole conflict hunk (from <<<<<<< to >>>>>>>), in one fenced code block.
Keep the original indentation. No conflict markers. Do not change anything outside the hunk."""


def propose(file_path: str, conflict_markers: str, ctx: list[dict], verdict: dict) -> str | None:
    """F4: merged hunk for a textual-only conflict, or None if the model returned something unusable."""
    out = llm(PROMPT.format(
        file_path=file_path,
        ours_intent=verdict.get("ours_intent", "unknown"),
        theirs_intent=verdict.get("theirs_intent", "unknown"),
        conflict=conflict_markers,
        context=format_context(ctx),
    ))
    m = re.search(r"```[^\n]*\n(.*?)```", out, re.S)
    code = m.group(1) if m else None
    if code is None or re.search(r"^(<{7}|={7}|>{7})", code, re.M):
        return None
    return code
