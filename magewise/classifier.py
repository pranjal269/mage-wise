import json
import re

from .llm import llm
from .retriever import format_context

PROMPT = """You are reviewing a Git merge conflict. Use the repository history to work out WHY each side changed the code.

Classify the conflict:
- "textual-only": both sides touch overlapping lines but change independent things (e.g. one adds a parameter, the other fixes a typo in the same function). Both can be kept.
- "semantic": both sides change the SAME behavior in incompatible ways (e.g. one sets a default to A and the other to B; one adds validation and the other removes it). A human must choose.
If unsure, answer "semantic".

The conflict has up to three sections: ours (between <<<<<<< and |||||||), the common ancestor "base" (between ||||||| and =======, when present), and theirs (between ======= and >>>>>>>). Compare each side to the base to see what that side actually changed. A side identical to the base changed nothing.

## Conflict in {file_path}
{conflict}

## Repository history (PRs, commits, review comments, issues)
{context}

Reply with only this JSON:
{{"ours_intent": "...", "theirs_intent": "...", "label": "textual-only" | "semantic", "reason": "one or two sentences"}}"""


def classify(file_path: str, conflict_markers: str, ctx: list[dict]) -> dict:
    """F3: return {"label": "textual-only" | "semantic", "reason": str, "ours_intent", "theirs_intent"}."""
    out = llm(PROMPT.format(file_path=file_path, conflict=conflict_markers, context=format_context(ctx)))
    m = re.search(r"\{.*\}", out, re.S)
    try:
        verdict = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        # Models sometimes emit near-JSON (e.g. an unquoted reason); salvage the fields we need.
        field = lambda k: (re.search(rf'"{k}"\s*:\s*"?([^"\n]*)', out) or [None, ""])[1].strip(' ",')
        verdict = {k: field(k) for k in ("ours_intent", "theirs_intent", "label", "reason")}
    if verdict.get("label") not in ("textual-only", "semantic"):
        # Unparseable means not confident, and semantic never auto-commits.
        return {"label": "semantic", "reason": f"Classifier output unparseable: {out[:500]}"}
    return verdict
