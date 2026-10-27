import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eval"))
from harness import hunks, maintainer_hunks, norm  # noqa: E402

from magewise import core, resolver  # noqa: E402
from magewise.retriever import parse_conflict  # noqa: E402

TWO_WAY = "<<<<<<< HEAD\na = 1\n=======\na = 2\n>>>>>>> feat\n"
DIFF3 = "<<<<<<< HEAD\na = 1\n||||||| base\na = 0\n=======\n>>>>>>> feat\n"


def test_parse_two_way():
    assert parse_conflict(TWO_WAY) == ("a = 1\n", "", "a = 2\n")


def test_parse_diff3_with_crlf_and_empty_side():
    assert parse_conflict("x\r\n" + DIFF3) == ("a = 1\n", "a = 0\n", "")


def test_parse_rejects_missing_markers():
    with pytest.raises(ValueError):
        parse_conflict("no markers")


def test_core_rejects_multiple_hunks():
    with pytest.raises(ValueError, match="one conflict hunk"):
        core.resolve("o/r", "f.py", TWO_WAY + TWO_WAY)


def test_model_output_json_then_code():
    out = 'Sure.\n{"label": "textual-only", "reason": "independent {braces} ok"}\n```python\nx = {1: 2}\n```'
    verdict, code = resolver.parse(out)
    assert verdict["label"] == "textual-only"
    assert code == "x = {1: 2}\n"


def test_model_output_near_json_is_salvaged():
    verdict, code = resolver.parse('{"label": "semantic", "reason": unquoted text}')
    assert verdict["label"] == "semantic"
    assert code is None


def test_resolve_hunk_never_trusts_code_with_markers(monkeypatch):
    out = '{"label": "textual-only", "reason": "r"}\n```\n<<<<<<< HEAD\nx\n```'
    monkeypatch.setattr(resolver, "llm", lambda prompt: (out, "fake/model"))
    v = resolver.resolve_hunk("f.py", TWO_WAY, [])
    assert v["label"] == "semantic" and v["resolution"] is None


def test_resolve_hunk_unparseable_is_semantic(monkeypatch):
    monkeypatch.setattr(resolver, "llm", lambda prompt: ("I am not sure.", "fake/model"))
    assert resolver.resolve_hunk("f.py", TWO_WAY, [])["label"] == "semantic"


def _no_model(*_):
    raise AssertionError("model must not be called")


def _hunk(ours, base, theirs):
    return f"<<<<<<< HEAD\n{ours}||||||| base\n{base}=======\n{theirs}>>>>>>> feat\n"


def test_deterministic_takes_the_only_side_that_changed(monkeypatch):
    monkeypatch.setattr(resolver, "llm", _no_model)
    monkeypatch.setattr(core.retriever, "retrieve", _no_model)  # no index / GitHub either
    out = core.resolve("o/r", "f.py", _hunk("a = 0\n", "a = 0\n", "a = 2\n"))
    assert out["classification"] == "textual-only"
    assert out["resolution"] == "a = 2\n"
    assert (out["sources"], out["model"]) == ([], None)
    assert resolver.deterministic(_hunk("a = 1\n", "a = 0\n", "a = 0\n"))["resolution"] == "a = 1\n"
    assert resolver.deterministic(TWO_WAY.replace("a = 2", "a = 1"))["resolution"] == "a = 1\n"  # same change


def test_deterministic_keeps_both_sides_of_adjacent_changes():
    # Git conflicts here because the edits touch; they change different lines, so both are kept.
    hunk = _hunk("def f(x, y):\n    return x\n", "def f(x):\n    return x\n", "def f(x):\n    return x + 1\n")
    assert resolver.deterministic(hunk)["resolution"] == "def f(x, y):\n    return x + 1\n"
    # A whitespace-only change is a change too: ours' blank-line deletion survives the merge.
    hunk = _hunk("\nx  # pragma\n", "\nx\n", "x\n")
    assert resolver.deterministic(hunk)["resolution"] == "x  # pragma\n"


def test_deterministic_defers_when_judgment_is_needed():
    assert resolver.deterministic(TWO_WAY) is None  # no base section: can't tell who changed what
    assert resolver.deterministic(_hunk("a = 1\n", "a = 0\n", "a = 2\n")) is None  # same line, both changed
    assert resolver.deterministic(_hunk("x\nb\n", "x\n", "x\nc\n")) is None  # two inserts at one spot
    # Ours adds the import theirs added elsewhere: merging would duplicate it.
    dup = _hunk("import a\nimport json\n", "import a\n", "import json\nimport a\n")
    assert resolver.deterministic(dup) is None
    # Ours moves a line that theirs deleted: merging would resurrect it.
    moved = _hunk("import c\nimport b\n", "import b\nimport c\n", "import b\n")
    assert resolver.deterministic(moved) is None


def test_maintainer_hunks_extracts_each_resolution():
    conflicted = "top\n" + TWO_WAY + "middle\n" + DIFF3 + "end\n"
    assert hunks(conflicted) == [TWO_WAY, DIFF3]
    assert maintainer_hunks(conflicted, "top\na = 3\nmiddle\nend\n") == ["a = 3\n", ""]


def test_maintainer_hunks_detects_edits_outside_hunks():
    assert maintainer_hunks("top\n" + TWO_WAY + "end\n", "TOP\na = 1\nend\n") is None


def test_norm_ignores_trailing_whitespace_and_blank_edges():
    assert norm("\n\nx = 1   \n\n") == norm("x = 1")
    assert norm(None) is None
