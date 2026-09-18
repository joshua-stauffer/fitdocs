---
id: 2026-09-18-test-types-docstring-helper-unanchored-slide-forward-regex
title: tests/load/qa/test_types.py's _docstring_for still uses the unanchored regex that slides into the next constant's docstring when the named one is missing; only test_sources.py's copy was anchored
status: open
importance: low
importance_why: Harmless today only because all seven DEFAULT_* constants carry docstrings and their expected substrings differ; the helper would silently pass a provenance assertion against a neighbour's docstring if one were ever deleted.
effort: S
kind: gap
area: activity-qa-flags, tests/load/qa/test_types.py
created: 2026-09-18
surfaced_by: /kiro-validate-impl activity-qa-flags (post-merge pass, 2026-09-18; cross-task integration reviewer, confirmed by the controller)
pinned_at: e16acc3
resume_command: "do: rewrite _docstring_for at tests/load/qa/test_types.py:245-248 to use the anchored pattern tests/load/qa/test_sources.py:80-82 already uses (line-start anchor, re.escape(name) followed by a colon, the rest of that line, a newline, then the triple-quoted docstring; flags re.DOTALL | re.MULTILINE) and port test_sources.py:89-118 test_docstring_helper_rejects_a_constant_with_no_docstring_of_its_own so a deleted docstring is its own failure"
context:
  - tests/load/qa/test_types.py
  - tests/load/qa/test_sources.py
  - .kiro/specs/activity-qa-flags/tasks.md
blocked_by: []
---

## What

`tests/load/qa/test_types.py:245-248`:

```python
def _docstring_for(name: str) -> str:
    match = re.search(rf"{name}[^\"]*\"\"\"(.*?)\"\"\"", _MODULE_SOURCE, re.DOTALL)
    assert match is not None, f"{name} has no docstring in source"
    return match.group(1)
```

`[^\"]*` runs forward across the constant's own line and any following
lines that contain no double quote until the *next* `"""` — which, if the
named constant has no docstring, is the next constant's. The
`assert match is not None` then passes and the caller asserts provenance
markers against the wrong docstring.

tasks.md's Implementation Notes ("1.1 → 1.2") recorded exactly this trap
and task 1.2 anchored its own copy in `test_sources.py:79-83` with a
regression guard (:89-118). The 1.1 copy was never revisited.

## Why it matters

Every `test_types.py` provenance assertion (Req 6.10: "in code at the point
of definition") is only as strong as this helper. A deleted docstring on
one constant would be reported as present.

## Evidence

- `sed -n '245,248p' tests/load/qa/test_types.py` — unanchored.
- `sed -n '79,83p' tests/load/qa/test_sources.py` — anchored form.
- `.kiro/specs/activity-qa-flags/tasks.md` Implementation Notes, "1.1 → 1.2".

## How to pick it up

1. Copy the anchored pattern and the regression guard from
   `test_sources.py`; adapt the guard's stand-in source to a `DEFAULT_*`
   constant without a docstring.
2. Verify by temporarily deleting one constant's docstring in a scratch copy
   and confirming the new guard reds. Done means the helper fails loudly on
   a missing docstring.
