import json
import re

from .llm import llm
from .retriever import format_context, parse_conflict

LABELS = ("textual-only", "semantic")
MARKER = re.compile(r"^(<{7}|\|{7}|={7}|>{7})", re.M)

PROMPT = """You are resolving a Git merge conflict in {file_path}. Use the repository history to work out WHY each side changed the code.

The conflict has up to three sections: ours (after <<<<<<<), the common ancestor "base" (after |||||||, when present), and theirs (after =======, up to >>>>>>>). Compare each side to the base to see what that side actually changed. A side identical to the base changed nothing.

Classify the conflict:
- "textual-only": both sides touch overlapping lines but change independent things (e.g. one adds a parameter, the other fixes a typo in the same function). Both changes can be kept.
- "semantic": both sides change the SAME behavior in incompatible ways (e.g. one sets a default to A and the other to B; one adds validation and the other removes it). A human must choose.
If unsure, answer "semantic".

## Conflict
{conflict}

## Repository history (PRs, commits, review comments, issues)
{context}

First output only this JSON object:
{{"ours_intent": "...", "theirs_intent": "...", "label": "textual-only" or "semantic", "reason": "one or two sentences"}}

Then, only if the label is "textual-only", output one fenced code block with the code that replaces the whole conflict hunk (everything from <<<<<<< to >>>>>>>), applying both sides' changes. Keep the original indentation, include no conflict markers, and change nothing outside the hunk."""


def _salvage(text: str) -> dict:
    """Models sometimes emit near-JSON (e.g. an unquoted string); pull out the fields we need."""
    field = lambda k: (re.search(rf'"{k}"\s*:\s*"?([^"\n]*)', text) or [None, ""])[1].strip(' ",')
    return {k: field(k) for k in ("ours_intent", "theirs_intent", "label", "reason")}


def parse(out: str) -> tuple[dict, str | None]:
    """Split model output into (verdict JSON, fenced code or None)."""
    start = out.find("{")
    try:
        verdict, end = json.JSONDecoder().raw_decode(out, start) if start >= 0 else ({}, 0)
    except json.JSONDecodeError:
        verdict, end = _salvage(out), 0
    if not isinstance(verdict, dict):
        verdict = {}
    code = re.search(r"```[^\n]*\n(.*?)```", out[end:], re.S)
    return verdict, code.group(1) if code else None


def _norm(code: str) -> str:
    return "\n".join(line.rstrip() for line in code.strip("\n").splitlines())


def trivial(conflict_markers: str) -> dict | None:
    """Resolve without a model when one side left the region as it was in the base.

    Then only the other side made a real change, so there's no intent to weigh: take it.
    Needs diff3 markers (the base section); returns None when both sides changed the region.
    """
    ours, base, theirs = parse_conflict(conflict_markers)
    if not base:
        return None
    for unchanged, changed, name in ((ours, theirs, "Ours"), (theirs, ours, "Theirs")):
        if _norm(unchanged) == _norm(base) and _norm(changed) != _norm(base):
            other = "theirs" if name == "Ours" else "ours"
            return {
                "label": "textual-only",
                "reason": f"{name} left this region as it was in the common ancestor (ignoring whitespace), "
                f"so only {other} changed it. Took {other} as-is; resolved without a model call.",
                "ours_intent": "no change to this region" if name == "Ours" else "",
                "theirs_intent": "no change to this region" if name == "Theirs" else "",
                "resolution": changed,
            }
    return None


def resolve_hunk(file_path: str, conflict_markers: str, ctx: list[dict]) -> dict:
    """F3+F4 in one model call: classify the hunk and, if textual-only, merge it.

    Returns {"label", "reason", "ours_intent", "theirs_intent", "resolution"}. Anything we can't trust
    (unparseable output, missing code, leftover markers) comes back as "semantic" so it is never auto-applied.
    """
    if verdict := trivial(conflict_markers):
        return verdict
    out = llm(PROMPT.format(file_path=file_path, conflict=conflict_markers, context=format_context(ctx)))
    verdict, code = parse(out)
    if verdict.get("label") not in LABELS:
        return {"label": "semantic", "reason": f"Model output unparseable, needs a human: {out[:300]}", "resolution": None}
    verdict["resolution"] = None
    if verdict["label"] == "textual-only":
        if code is None or MARKER.search(code):
            verdict["label"] = "semantic"
            verdict["reason"] = f"{verdict.get('reason', '')} (No clean merged code was produced, so a human must decide.)"
        else:
            verdict["resolution"] = code
    return verdict
