---
id: 2026-08-03-docedit-observable-cannot-evidence-its-redaction
title: Task 3.5's value-matcher observable was already true before the edit it was meant to evidence
status: open
importance: low
importance_why: The redaction is correct and landed; the defect is that the stated observable proves nothing, and later tasks inherit the same pattern.
effort: S
kind: inconsistency
area: encumbered-content-purge, src/fitdocs/load/docedit.py
created: 2026-08-03
surfaced_by: /kiro-impl encumbered-content-purge (task 3.5 review)
pinned_at: c3d2201
resume_command: "do: correct task 3.5's observable in tasks.md to name a check that can actually fail for src/fitdocs/load/docedit.py -- the erased zone label's presence in the pre-deletion writeup and extracted table -- and sweep the other Major 3 tasks for observables whose probe returns the same answer before and after the edit"
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - src/fitdocs/load/docedit.py
  - tests/_content_oracle.py
  - tests/_content_fingerprints.py
blocked_by: []
---

## What

Task 3.5's bullet for `src/fitdocs/load/docedit.py` says the zone-table row in
its docstring "is a **value reproduction, not a token** — the file matches zero
on a token scan and is reachable only by the value matcher". The observable
then requires that "none of these files matches the forbidden-string matcher
**and** none matches the value matcher".

The second half cannot evidence the redaction, because **the value matcher
returns `False` on the pre-edit blob too**. "None matches the value matcher"
was already true before the edit, so the stated observable holds identically
whether or not the work was done.

The redaction itself is correct and has landed (`9d8ef1c`). It is justified by
a different route: the erased zone label occurs in the writeup and in one of
the extracted tables deleted at `a705490`, which makes it a genuine Req 1.2
zone-table row reproduction. That is a check that can fail. The one the task
names is not.

## Why it matters

This is the pre-satisfied-fixture anti-pattern at the level of a task
observable rather than a test assertion, and the spec's own execution rules
warn about the adjacent form ("an observable naming one matcher is vacuous for
the other's work"). An implementer following the letter of this observable
would run the value matcher, see `False`, and report the requirement satisfied
without having verified anything.

The pattern is likely to recur: seven `(P)` redaction tasks in Major 3 state
observables in terms of a matcher reporting zero, and a matcher reports zero
both for "the reproduction was removed" and for "there was never a
reproduction this matcher could see". Task 3.4's Implementation Notes already
record the general form of this hazard — "a pass that finds nothing and a pass
that never ran are indistinguishable in the artifact" — and the remedy there
was to prove the negative by running the same probe against pre-deletion blobs
from history, where it fires.

## Evidence

Measured directly in this run at `9d8ef1c`, comparing the pre-edit blob against
the shipped file through the real fingerprint set:

    $ git show HEAD~1:src/fitdocs/load/docedit.py > /tmp/pre_docedit.py
    $ uv run python -c "
    import sys; sys.path.insert(0,'tests')
    import _content_oracle as o, _content_fingerprints as f
    pre=open('/tmp/pre_docedit.py').read()
    post=open('src/fitdocs/load/docedit.py').read()
    print('pre-edit blob scan :', o.scan(pre, f.FINGERPRINTS, f.WINDOW_LENGTHS, f.SALT))
    print('post-edit scan     :', o.scan(post, f.FINGERPRINTS, f.WINDOW_LENGTHS, f.SALT))
    "
    pre-edit blob scan : False
    post-edit scan     : False

The probe is not vacuous — the same fingerprint set returns `True` against the
pre-deletion blobs of the material removed at `a705490`, which is how task 3.4
established its own true-negative.

The task text is at `.kiro/specs/encumbered-content-purge/tasks.md`, task 3.5,
the `docedit` bullet and the Observable bullet beneath it.

Reviewer-reported and not re-derived here: the erased zone label occurs at least
once in the writeup and once in an extracted table among the blobs deleted at
`a705490`, which is the basis on which the redaction is genuinely required.

## How to pick it up

1. Confirm the measurement above still reproduces (it needs
   `FITDOCS_FORBIDDEN_STRINGS` exported only for the suite, not for this probe).
2. Correct task 3.5's observable in `tasks.md` to name a check that can fail —
   the erased label's presence in the pre-deletion blobs is the honest basis.
   Task 3.5 is already `[x]`; amend the bullet in place with a dated note rather
   than reopening it, matching the **Corrected in place** idiom the same file
   already uses for task 3.4.
3. **Sweep the other Major 3 observables for the same shape.** For each task
   that states "matches zero on <matcher>", ask whether the matcher would have
   returned zero before the edit. Where it would, either name a different check
   or require the implementer to prove the negative against pre-deletion blobs
   from history, as task 3.4's Implementation Notes prescribe.
4. This must happen **before Major 7**. After the history rewrite the
   pre-deletion blobs are unreachable and the honest check becomes impossible
   to run.

Done means no Major 3 observable can be satisfied by a probe that returns the
same answer before and after the work it is meant to evidence.

## Open questions

None.
