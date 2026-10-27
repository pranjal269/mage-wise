import json
import re
from difflib import SequenceMatcher

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
Entries marked [base history] are older commits explaining why the code looked as it did before either side changed it.
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


def _edits(base: list[str], side: list[str]) -> list[tuple]:
    """(start, end, new lines) for each run of base lines that one side replaced, deleted or inserted at."""
    sm = SequenceMatcher(None, base, side, autojunk=False)
    return [(i1, i2, tuple(side[j1:j2])) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def merge_lines(ours: str, base: str, theirs: str) -> str | None:
    """Three-way merge of one hunk, line by line. None when both sides changed the same base lines.

    Git also conflicts when the two sides' changes are merely adjacent; those touch different base lines,
    so both can be kept. On 250 real Flask and Jinja conflict hunks, deterministic() resolves 73 and
    matches the maintainer on 68 (93%), better than either model on the same hunks.
    """
    b, o, t = (s.splitlines(keepends=True) for s in (base, ours, theirs))
    eo, et = _edits(b, o), _edits(b, t)
    only_o, only_t = set(eo) - set(et), set(et) - set(eo)  # identical edits on both sides are taken once
    for x1, x2, _ in only_o:
        for y1, y2, _ in only_t:
            if x1 < y2 and y1 < x2 or x1 == x2 == y1 == y2:  # same base lines, or two inserts at one spot
                return None
    # A line one side added that the other side also added or removed is a move or a duplicate, not
    # independent work (e.g. both sides adding the same import in different places).
    added = lambda es: {s for *_, new in es for line in new if (s := line.strip())}
    removed = lambda es: {s for i1, i2, _ in es for line in b[i1:i2] if (s := line.strip())}
    if added(only_o) & (added(only_t) | removed(et)) or added(only_t) & removed(eo):
        return None
    out, pos = [], 0
    for i1, i2, new in sorted(set(eo) | set(et)):
        out += b[pos:i1] + list(new)
        pos = i2
    return "".join(out + b[pos:])


def deterministic(conflict_markers: str) -> dict | None:
    """Resolve without a model (or history) when the hunk needs no judgment. None when it does.

    Exact comparisons on purpose: ignoring whitespace would silently drop a side's whitespace-only change.
    Needs diff3 markers (the base section), except when both sides are identical.
    """
    ours, base, theirs = parse_conflict(conflict_markers)  # line endings already normalized
    verdict = lambda reason, code, oi="", ti="": {
        "label": "textual-only", "reason": reason + " Resolved without a model call.",
        "ours_intent": oi, "theirs_intent": ti, "resolution": code}
    if ours == theirs:
        return verdict("Both sides made the identical change; took it once.", ours)
    if not base:
        return None
    if ours == base:
        return verdict("Ours left this region as it was in the common ancestor, so only theirs changed it. "
                       "Took theirs as-is.", theirs, oi="no change to this region")
    if theirs == base:
        return verdict("Theirs left this region as it was in the common ancestor, so only ours changed it. "
                       "Took ours as-is.", ours, ti="no change to this region")
    if (merged := merge_lines(ours, base, theirs)) is not None:
        return verdict("Ours and theirs changed different lines of the common ancestor (Git conflicts on "
                       "adjacent changes too); kept both with a line-level three-way merge.", merged)
    return None


def resolve_hunk(file_path: str, conflict_markers: str, ctx: list[dict]) -> dict:
    """F3+F4 in one model call: classify the hunk and, if textual-only, merge it.

    Returns {"label", "reason", "ours_intent", "theirs_intent", "resolution", "model"}. Anything we can't
    trust (unparseable output, missing code, leftover markers) comes back as "semantic" so it is never auto-applied.
    """
    if verdict := deterministic(conflict_markers):
        return {**verdict, "model": None}
    out, model = llm(PROMPT.format(file_path=file_path, conflict=conflict_markers, context=format_context(ctx)))
    verdict, code = parse(out)
    if verdict.get("label") not in LABELS:
        return {"label": "semantic", "reason": f"Model output unparseable, needs a human: {out[:300]}",
                "resolution": None, "model": model}
    verdict["resolution"] = None
    verdict["model"] = model
    if verdict["label"] == "textual-only":
        if code is None or MARKER.search(code):
            verdict["label"] = "semantic"
            verdict["reason"] = f"{verdict.get('reason', '')} (No clean merged code was produced, so a human must decide.)"
        else:
            verdict["resolution"] = code
    return verdict
