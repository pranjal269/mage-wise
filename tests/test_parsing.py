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
    monkeypatch.setattr(resolver, "llm", lambda prompt: out)
    v = resolver.resolve_hunk("f.py", TWO_WAY, [])
    assert v["label"] == "semantic" and v["resolution"] is None


def test_resolve_hunk_unparseable_is_semantic(monkeypatch):
    monkeypatch.setattr(resolver, "llm", lambda prompt: "I am not sure.")
    assert resolver.resolve_hunk("f.py", TWO_WAY, [])["label"] == "semantic"


def test_maintainer_hunks_extracts_each_resolution():
    conflicted = "top\n" + TWO_WAY + "middle\n" + DIFF3 + "end\n"
    assert hunks(conflicted) == [TWO_WAY, DIFF3]
    assert maintainer_hunks(conflicted, "top\na = 3\nmiddle\nend\n") == ["a = 3\n", ""]


def test_maintainer_hunks_detects_edits_outside_hunks():
    assert maintainer_hunks("top\n" + TWO_WAY + "end\n", "TOP\na = 1\nend\n") is None


def test_norm_ignores_trailing_whitespace_and_blank_edges():
    assert norm("\n\nx = 1   \n\n") == norm("x = 1")
    assert norm(None) is None
