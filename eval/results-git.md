# Magewise eval: pallets/flask, history from the commits behind each side and behind the base (git log -L), and the PRs they reference

Real merge conflicts from pallets/flask's history, recreated from each merge's parents and scored against the maintainer's resolution.

| Metric | Value |
|---|---|
| Conflict hunks evaluated | 40 |
| Resolved automatically (textual-only) | 29 (72%) |
| ...matching the maintainer exactly | **21 / 29 (72%)** |
| ...not matching | 8 |
| Deferred to a human (semantic) | 11 |
| Baseline "always take ours" | 6 / 40 (15%) |
| Baseline "always take theirs" | 5 / 40 (12%) |
| Maintainer combined both sides | 29 / 40 |

Matching ignores trailing whitespace and leading/trailing blank lines. History is limited to what existed before each merge.

| Hunk | Maintainer took | Magewise | Outcome |
|---|---|---|---|
| `6a2f545bfd:src/flask/cli.py:0` | theirs | semantic | deferred |
| `258d68b6ff:tests/test_reqctx.py:0` | theirs | semantic | deferred |
| `daca74d93a:src/flask/templating.py:0` | combined | semantic | deferred |
| `5880befcd2:src/flask/app.py:0` | combined | textual-only | match |
| `97c830190f:src/flask/testing.py:0` | ours | semantic | deferred |
| `7ee9ceb71e:src/flask/app.py:0` | combined | textual-only | match |
| `48fe96588c:src/flask/templating.py:0` | ours | textual-only | mismatch |
| `48fe96588c:src/flask/templating.py:1` | ours | semantic | deferred |
| `7a2d5fb6df:src/flask/blueprints.py:0` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/scaffold.py:0` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/scaffold.py:1` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/scaffold.py:2` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/scaffold.py:3` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/scaffold.py:4` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/scaffold.py:5` | combined | textual-only | match |
| `7a2d5fb6df:src/flask/typing.py:0` | ours | textual-only | match |
| `9e2e1de2fc:src/flask/blueprints.py:0` | combined | textual-only | match |
| `9e2e1de2fc:src/flask/blueprints.py:1` | combined | textual-only | match |
| `9e2e1de2fc:src/flask/blueprints.py:2` | combined | textual-only | match |
| `9e2e1de2fc:src/flask/blueprints.py:3` | combined | textual-only | match |
| `9e2e1de2fc:src/flask/scaffold.py:0` | combined | semantic | deferred |
| `1ce0f774c9:setup.py:0` | combined | textual-only | match |
| `7d2ba3e1fc:src/flask/json/__init__.py:0` | combined | semantic | deferred |
| `ef27c1b749:setup.py:0` | ours | semantic | deferred |
| `9b424e9da9:setup.py:0` | ours | semantic | deferred |
| `7fdd0df6ec:docs/conf.py:0` | theirs | textual-only | match |
| `563ef469f7:docs/conf.py:0` | theirs | textual-only | mismatch |
| `2844fdb82e:src/flask/cli.py:0` | combined | textual-only | mismatch |
| `b05a685a03:examples/tutorial/tests/test_db.py:0` | combined | textual-only | match |
| `b05a685a03:tests/test_helpers.py:0` | combined | textual-only | match |
| `afd6250bab:src/flask/helpers.py:0` | combined | semantic | deferred |
| `afd6250bab:tests/test_helpers.py:0` | combined | textual-only | match |
| `29111a3259:tests/test_reqctx.py:0` | combined | semantic | deferred |
| `05a4e15ee4:flask/cli.py:0` | theirs | textual-only | mismatch |
| `05a4e15ee4:flask/json/__init__.py:0` | combined | textual-only | mismatch |
| `05a4e15ee4:flask/json/__init__.py:1` | combined | textual-only | mismatch |
| `05a4e15ee4:flask/json/__init__.py:2` | combined | textual-only | mismatch |
| `05a4e15ee4:flask/json/__init__.py:3` | combined | textual-only | mismatch |
| `05a4e15ee4:flask/json/__init__.py:4` | combined | textual-only | match |
| `05a4e15ee4:flask/json/__init__.py:5` | combined | textual-only | match |
