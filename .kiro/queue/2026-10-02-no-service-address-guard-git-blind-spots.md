---
id: 2026-10-02-no-service-address-guard-git-blind-spots
title: TestNoServiceAddress raises outside a git checkout and does not scan an untracked new file until it is git-added
status: open
importance: low
importance_why: A false error in a non-git copy and a delayed catch for a new file; the guard is otherwise sound and CI runs in a checkout.
effort: S
kind: gap
area: channel-merge, tests/compose/test_boundary.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: make tests/compose/test_boundary.py::_tracked_files skip (not raise) when git is unavailable or the root is not a checkout, and list untracked, non-ignored files too (git ls-files -co --exclude-standard) [queue: .kiro/queue/2026-10-02-no-service-address-guard-git-blind-spots.md]"
context:
  - tests/compose/test_boundary.py
  - tests/test_forbidden_strings.py
  - tests/test_packaging.py
  - .kiro/queue/2026-09-19-shared-git-ls-files-enumeration-helper.md
  - .kiro/queue/2026-09-30-repo-wide-no-stryd-address-guard.md
blocked_by: []
---

## What
`tests/compose/test_boundary.py::TestNoServiceAddress` (channel-merge Req 9.3)
lists the files to scan with `git ls-files -z` and `check=True`. Two blind spots:
1. Outside a git checkout (a source tree with no `.git`, for example a GitHub
   source-archive download), the subprocess exits 128 and the test errors with
   `CalledProcessError` instead of skipping.
2. `git ls-files` without `-o` omits untracked files, so a Stryd address pasted
   into a brand-new, not-yet-added file passes until it is `git add`ed.

## Why it matters
The first is a spurious error for anyone running the suite from a non-git copy.
The second is a delay, not a hole (a commit adds the file, and the change
guard stages before landing), but the guard is the only check on the Stryd
no-address rule and an agent session can write a new file and run the suite
before staging it.

## Evidence
At 5c41759.
- `tests/compose/test_boundary.py:418-422`:
  `subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)`.
- Non-git raise, run in this run in an empty directory outside any repository:
  `subprocess.run(["git","ls-files","-z"], cwd=".", capture_output=True, check=True)`
  raised `CalledProcessError 128 fatal: not a git repository (or any of the
  parent directories): .git`.
- Untracked file, run in this run: a new untracked file under `.kiro/` did not
  appear in `git ls-files -z` (match count 0); the file was removed afterwards.
- The sdist does not ship `tests/` (`pyproject.toml:58-65` `only-include`), so
  an sdist test run is not the scenario; the real ones are a git-less copy of
  the repository or a source-archive download.
- Same `check=True` pattern, not specific to this test:
  `tests/test_forbidden_strings.py:652` and `tests/test_packaging.py:312`.
- Related open items, not duplicated here:
  `2026-09-19-shared-git-ls-files-enumeration-helper` (three private copies of
  the enumeration) and `2026-09-30-repo-wide-no-stryd-address-guard` (asks for
  the guard this test now provides; the picking-up session should check whether
  it can be closed).

## How to pick it up
1. If `2026-09-19-shared-git-ls-files-enumeration-helper` has landed, use its
   helper; otherwise change only `_tracked_files` here.
2. Use `git ls-files -z --cached --others --exclude-standard`, and
   `pytest.skip` when `git` is missing or exits non-zero (a positive control
   that the skip fires is a test beside `test_an_address_is_detected_in_code_docs_and_specs`).
3. Done when a planted address in an untracked file reds the guard.
