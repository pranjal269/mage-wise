import pytest

from magewise import core, mcp_server

H1 = "<<<<<<< HEAD\na = 1\n=======\na = 2\n>>>>>>> feat\n"
H2 = "<<<<<<< HEAD\nb = 1\n=======\nb = 2\n>>>>>>> feat\n"
H3 = "<<<<<<< HEAD\nc = 1\n=======\nc = 2\n>>>>>>> feat\n"


def fake_resolve(repo, path, hunk, pr_number=None, **_):
    if "a = 1" in hunk:
        return {"classification": "textual-only", "resolution": "a = 3\n", "reasoning": "r", "sources": [], "model": "m"}
    if "b = 1" in hunk:
        return {"classification": "semantic", "resolution": None, "reasoning": "r", "sources": [], "model": "m"}
    raise RuntimeError("all model providers failed")


def test_resolves_every_hunk_across_files_and_keeps_the_rest(monkeypatch):
    monkeypatch.setattr(core, "resolve", fake_resolve)
    files = {"x.py": "top\n" + H1 + "mid\n" + H2, "y.py": H3, "clean.py": "no conflicts\n"}
    out = core.resolve_files("o/r", files)

    by_path = {f["path"]: f for f in out["files"]}
    assert by_path["x.py"]["content"] == "top\na = 3\nmid\n" + H2  # resolved hunk applied, semantic kept
    assert [h["classification"] for h in by_path["x.py"]["hunks"]] == ["textual-only", "semantic"]
    assert by_path["y.py"]["content"] == H3  # a provider error never loses the hunk
    assert by_path["y.py"]["hunks"][0]["classification"] == "error"
    assert by_path["clean.py"]["hunks"] == []
    assert (out["resolved"], out["needs_human"]) == (1, 2)
    assert [h["conflict_markers"] for h in by_path["x.py"]["hunks"]] == [H1, H2]  # for targeted edits


def test_hunks_only_input_works(monkeypatch):
    monkeypatch.setattr(core, "resolve", fake_resolve)
    out = core.resolve_files("o/r", {"x.py": H1 + H2})  # what an agent sends instead of the whole file
    assert [(h["classification"], h["resolution"]) for h in out["files"][0]["hunks"]] == [
        ("textual-only", "a = 3\n"), ("semantic", None)]


def test_keeps_crlf_line_endings(monkeypatch):
    monkeypatch.setattr(core, "resolve", fake_resolve)
    crlf = "top\r\n" + H1.replace("\n", "\r\n")
    out = core.resolve_files("o/r", {"x.py": crlf})
    assert out["files"][0]["content"] == "top\r\na = 3\r\n"


def test_hosted_server_refuses_repo_path(monkeypatch):
    monkeypatch.setattr(mcp_server, "_HOSTED", True)
    with pytest.raises(ValueError, match="local"):
        mcp_server._local_path("/srv/some/repo")
    assert mcp_server._local_path(None) is None
