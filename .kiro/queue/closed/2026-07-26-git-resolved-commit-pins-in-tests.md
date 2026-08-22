---
id: 2026-07-26-git-resolved-commit-pins-in-tests
title: A test resolves a pinned commit SHA through git, which no shallow clone can satisfy
status: done
importance: medium
importance_why: The suite passes locally but fails on any depth-limited clone, so the first CI workflow added to this now-published repo fails on a green tree — and the failure names a git object, not the behavior under test.
effort: S
kind: bug
area: inbox, tests/test_cli_drain_report.py, tests/load/test_render.py
created: 2026-07-26
surfaced_by: pushing the repo to GitHub after the author-email history rewrite
pinned_at: b58cf81
resume_command: "do: make tests/test_cli_drain_report.py's _report byte-for-byte baseline independent of `git show` -- vendor the pre-task _report source as a fixture (or drop to a behavioral assertion) so the test needs no history beyond the checkout, and give tests/load/test_render.py's prose citation the same treatment [queue: .kiro/queue/2026-07-26-git-resolved-commit-pins-in-tests.md]"
context:
  - tests/test_cli_drain_report.py
  - tests/load/test_render.py
  - .kiro/specs/inbox/tasks.md
  - .kiro/specs/inbox/requirements.md
blocked_by: []
---

## What

`tests/test_cli_drain_report.py` asserts that `_report` was left byte-untouched
by comparing its AST against a baseline it fetches **out of git history at test
time**:

```python
_PRE_TASK_CLI_COMMIT = "faa6d09"                       # line 38
...
["git", "show", f"{_PRE_TASK_CLI_COMMIT}:src/fitdocs/cli.py"],   # line 356
    cwd=repo_root, check=True,
```

The assertion is sound; the *sourcing* is the problem. It makes a unit test
depend on the checkout containing a specific historical commit — something a
working tree does not guarantee. Any clone that does not carry that object
fails the test with `CalledProcessError: exit status 128`, which reports a
missing git object rather than the drift the test exists to catch.

`tests/load/test_render.py:563-573` pins the same way (`6386361`, and
`6386361~1` via `git show`), but only inside a comment, so it misleads a reader
rather than failing a run.

## Why it matters

The repo now lives on GitHub and has no `.github/workflows/` yet. The default
`actions/checkout` is `fetch-depth: 1`. So the *first* CI workflow anyone adds
will fail on a tree that is green locally, and the error will point at git
plumbing rather than at `_report`.

It is also fragile to exactly what just happened: the author-email rewrite
changed every SHA in the repo, orphaning the old pin. It was repinned in
`aa23908`, but the pattern will break again on the next rewrite, and a
`git gc` that drops `refs/original/` removes the ability to even discover what
the old pin meant.

## Evidence

Verified at `b58cf81`, against the pushed remote:

```
$ git clone --depth 1 git@github.com:joshua-stauffer/fitdocs_oss.git /tmp/shallow
$ git -C /tmp/shallow show faa6d09:src/fitdocs/cli.py
  -> FAILS in a depth-1 clone
```

The same check in a full clone succeeds, which is why the suite is green
locally — `uv run pytest -q` → **1765 passed** at `b58cf81`, and 1765 passed in
a full clone of the remote.

The pre-rewrite form of this break was observed directly before it was fixed:
with the old SHA still in the file, a `--no-local --single-branch` clone gave

```
subprocess.CalledProcessError: Command '['git', 'show', 'd7f6c8a:src/fitdocs/cli.py']'
returned non-zero exit status 128.
FAILED tests/test_cli_drain_report.py::test_report_function_is_left_byte_untouched
1 failed, 10 passed
```

Sites: `tests/test_cli_drain_report.py:38` and `:356`;
`tests/load/test_render.py:563`, `:565`, `:568`, `:573`.

## How to pick it up

1. Open `tests/test_cli_drain_report.py` and read the comment at lines 35-38 —
   it explains *why* the pin is deliberate (it must keep naming the pre-task
   state of `_report` even after later commits touch `cli.py`). That intent is
   correct and must survive whatever you do; only the sourcing changes.
2. Check what the test actually needs: it parses the fetched `cli.py`, pulls
   out the `_report` FunctionDef, and compares `ast.dump` against the live one.
   So it needs the *baseline source of one function*, not a commit. Vendor that
   function's pre-task source into `tests/fixtures/` and read it from disk.
3. Confirm `.kiro/specs/inbox/tasks.md:194` — which records the pin as a
   deliberate Req 7.3 decision — still describes what the test does after the
   change, and update it if not.

Done means: no test invokes `git` to obtain a baseline, `uv run pytest -q` is
green in a `--depth 1` clone of the remote, and `test_render.py`'s comment no
longer instructs a reader to run a `git show` that may not resolve.

## Open questions

- Req 7.3's intent is "prove `_report` was not touched". A vendored fixture
  proves it against a *recorded* baseline rather than against history — which
  is weaker if someone edits the fixture. Worth deciding whether that is
  acceptable, or whether this assertion belongs in a pre-commit/CI check with
  full history instead of in the unit suite.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`772ab52`. Baseline vendored to `tests/fixtures/report_baseline_faa6d09.py`; no test invokes git. Verified the vendored AST equals `faa6d09`'s (not current HEAD's, which would be self-referential) and that mutating `_report` still reds. The open question — whether this belongs in a full-history pre-commit check rather than the unit suite — is recorded as accepted-for-now, not resolved.
