import subprocess

from magewise import githistory


def git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def commit(d, text, msg):
    (d / "a.py").write_text(text)
    git(d, "commit", "-qam", msg)


def test_side_commits_finds_the_commits_behind_each_side(tmp_path):
    d = tmp_path
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "a.py").write_text("one\ntwo\nthree\nfour\nfive\n")
    git(d, "add", "a.py")
    git(d, "commit", "-qm", "base")
    git(d, "branch", "other")

    commit(d, "one\nTWO-ours\nthree\nfour\nfive\n", "ours: change two (#10)")
    commit(d, "one\nTWO-ours\nthree\nfour\nFIVE\n", "ours: unrelated change to five (#11)")
    git(d, "checkout", "-q", "other")
    commit(d, "one\nTWO-theirs\nthree\nfour\nfive\n", "theirs: change two (#20)")

    docs = githistory.side_commits(str(d), "main", "other", "a.py", "TWO-ours\n", "TWO-theirs\n")
    by_side = {s: [x["content"] for x in docs if x["side"] == s] for s in ("ours", "theirs")}
    assert by_side == {"ours": ["ours: change two (#10)"], "theirs": ["theirs: change two (#20)"]}
    assert [x["linked_ids"] for x in docs] == ["|10|", "|20|"]


def test_base_history_explains_the_lines_before_either_side(tmp_path):
    d = tmp_path
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "a.py").write_text("one\ntwo\nthree\n")
    git(d, "add", "a.py")
    git(d, "commit", "-qm", "initial")
    commit(d, "one\ntwo = 2  # why: issue #7\nthree\n", "explain two (#7)")
    commit(d, "ONE\ntwo = 2  # why: issue #7\nthree\n", "unrelated: one")
    git(d, "branch", "other")
    commit(d, "ONE\ntwo = 3  # why: issue #7\nthree\n", "ours: bump two")
    git(d, "checkout", "-q", "other")
    commit(d, "ONE\ntwo = 4  # why: issue #7\nthree\n", "theirs: bump two")

    base = "two = 2  # why: issue #7\n"
    docs = githistory.side_commits(str(d), "main", "other", "a.py", "two = 3  # why: issue #7\n",
                                   "two = 4  # why: issue #7\n", base)
    history = [x["content"] for x in docs if x["side"] == "base history"]
    assert history[0] == "explain two (#7)"  # the commit that made the base line what it was
    assert "unrelated: one" not in history  # touched the file, not these lines
    assert githistory.side_commits(str(d), "main", "other", "a.py", "x\n", "y\n", base, base_limit=0) == [
        x for x in githistory.side_commits(str(d), "main", "other", "a.py", "x\n", "y\n", base)
        if x["side"] != "base history"
    ]


def test_deleted_side_falls_back_to_file_history(tmp_path):
    d = tmp_path
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "a.py").write_text("one\ntwo\n")
    git(d, "add", "a.py")
    git(d, "commit", "-qm", "base")
    git(d, "branch", "other")
    commit(d, "one\n", "ours: delete two")
    git(d, "checkout", "-q", "other")
    commit(d, "one\nTWO\n", "theirs: change two")

    docs = githistory.side_commits(str(d), "main", "other", "a.py", "", "TWO\n")
    assert [(x["side"], x["content"]) for x in docs] == [("ours", "ours: delete two"), ("theirs", "theirs: change two")]
