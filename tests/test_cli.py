import argparse
import subprocess
import sys

import pytest

from magewise import cli

CONFLICT = "x = 0\n<<<<<<< HEAD\na = 1\n=======\na = 2\n>>>>>>> feat\n"
RESOLVED = "x = 0\na = 3\n"
PASS = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAIL = f'"{sys.executable}" -c "raise SystemExit(1)"'


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text(CONFLICT, newline="")
    monkeypatch.chdir(tmp_path)
    resolution = {"classification": "textual-only", "resolution": "a = 3\n", "reasoning": "r", "sources": []}
    monkeypatch.setattr(cli.core, "resolve", lambda *a, **k: resolution)
    return tmp_path


def run(write, test=None, keep_on_fail=False):
    args = argparse.Namespace(files=["a.py"], repo="o/r", write=write, test=test,
                              keep_on_fail=keep_on_fail, test_timeout=60, workers=1)
    return cli.resolve(args)


def test_write_with_passing_tests_keeps_resolution(repo):
    assert run(write=True, test=PASS) == 0
    assert (repo / "a.py").read_text() == RESOLVED


def test_write_with_failing_tests_rolls_back(repo):
    assert run(write=True, test=FAIL) == 1
    assert (repo / "a.py").read_text() == CONFLICT


def test_dry_run_with_tests_always_rolls_back(repo):
    assert run(write=False, test=PASS) == 0
    assert (repo / "a.py").read_text() == CONFLICT


def test_keep_on_fail_keeps_resolution_but_reports_failure(repo):
    assert run(write=True, test=FAIL, keep_on_fail=True) == 1
    assert (repo / "a.py").read_text() == RESOLVED
