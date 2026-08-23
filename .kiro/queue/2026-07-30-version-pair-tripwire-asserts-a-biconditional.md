---
id: 2026-07-30-version-pair-tripwire-asserts-a-biconditional
title: The load/doc version tripwire's failure message asserts a biconditional that neither requirement states
status: open
importance: medium
importance_why: The message instructs the next editor to bump both versions whenever either moves, but Req 11.5 is one-directional — and following it would orphan every existing document's load payload, since an unrecognised payload version is treated as foreign content.
effort: S
kind: inconsistency
area: training-load, tests/load/test_render.py, src/fitdocs/load/render.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.2 — the tripwire fired as designed and the maintainer ruled on the pair)
pinned_at: c3d2201
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-30-version-pair-tripwire-asserts-a-biconditional.md] Correct the version-pair tripwire's failure message to state Req 11.5's one-directional implication"
context:
  - tests/load/test_render.py
  - src/fitdocs/load/render.py
  - .kiro/specs/training-load/requirements.md
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`test_payload_version_paired_with_doc_version` in `tests/load/test_render.py`
pins `(LOAD_PAYLOAD_VERSION, contract.DOC_VERSION)` as a tuple. Its failure
message reads:

> "if you bumped `LOAD_PAYLOAD_VERSION`, you must also bump
> `contract.DOC_VERSION` **(and vice versa)**, then update the expected pair in
> this assertion."

The "(and vice versa)" asserts a **biconditional**. Neither requirement states
one.

Req 11.5 (`.kiro/specs/training-load/requirements.md:396`) is one-directional:
*"When the **result format** changes, the fitdocs CLI shall change the
document-format version it records in frontmatter, so that documents needing
regeneration are detectable without opening the training-load section."*

That is: load-format change ⟹ doc-version change. Nothing says a doc-version
change implies a load-format change.

## Why it matters

The message is instruction, not commentary — it tells the next editor what to
do, and following it is actively harmful.

`src/fitdocs/load/render.py:178` refuses to parse a payload whose version it
does not recognise, treating it as foreign content:

```python
if int(match.group(1)) != LOAD_PAYLOAD_VERSION:
    return None   # unknown/newer version -> foreign, never misread
```

So bumping `LOAD_PAYLOAD_VERSION` in sympathy with a doc-version advance would
orphan the load payload in **every already-written document**, for a change
that did not alter the load result format at all.

This is not hypothetical. `fit-ingest` Amendment 1 advanced `DOC_VERSION` 3→4
because a *metric value* moved (Req 18.1), with the load result format
untouched. The tripwire fired, the message told the editor to bump both, and
the correct answer was to bump only one. It took a maintainer ruling to
establish that — which is the tripwire working as intended, except that its
own message argued for the wrong outcome.

## Evidence

- `tests/load/test_render.py` — the assertion and its failure message,
  currently expecting `(2, 4)`.
- `.kiro/specs/training-load/requirements.md:396` — Req 11.5, one-directional.
- `.kiro/specs/fit-ingest/requirements.md` Req 18.1 — the criterion that
  actually fired for Amendment 1: *"When Amendment 1 changes the value the
  fit-ingest library reports for a metric of an already-documented activity,
  the fitdocs document-format version shall advance."* It says nothing about
  the load payload version.
- `src/fitdocs/load/render.py:178` — the foreign-content rejection quoted
  above.
- Maintainer ruling, 2026-07-30, recorded in the shared agent log: the pair
  moves to `(2, 4)`; `DOC_VERSION` advances alone.

Related and already closed: `.kiro/queue/closed/2026-07-26-payload-doc-version-pair-unpinned.md`
is the item that *created* this assertion. It does not discuss the
biconditional wording.

## How to pick it up

1. Read Req 11.5 and decide what the tripwire should actually enforce. The
   honest reading is: a `LOAD_PAYLOAD_VERSION` bump **requires** a
   `DOC_VERSION` bump; a `DOC_VERSION` bump does **not** require a
   `LOAD_PAYLOAD_VERSION` bump.
2. Consider whether the exact-tuple assertion is still the right shape. It reds
   on *any* movement of either constant, which is a useful drift tripwire — but
   its message should tell the editor how to decide, not assert a rule that
   does not exist. An alternative is to assert the implication directly
   (`if LOAD_PAYLOAD_VERSION changed: DOC_VERSION must have changed too`)
   against recorded baselines, so the one-directional rule is mechanical rather
   than advisory.
3. Whichever shape is chosen, keep the message's best feature: it names the
   constant the editor forgot. That is why the tripwire worked.
4. Note the fit-ingest side already records the maintainer's ruling in this
   test's docstring — keep those two consistent.

Done looks like: the failure message states Req 11.5's actual implication, and
no reader is instructed toward a bump that would orphan existing payloads.
