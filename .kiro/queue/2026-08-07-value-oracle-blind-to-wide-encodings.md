---
id: 2026-08-07-value-oracle-blind-to-wide-encodings
title: The value oracle matches UTF-8 text only, so a wide-encoding copy of a fingerprinted table evades every value scan
status: open
importance: low
importance_why: Pre-existing and equally true of the guard this spec replaced, but it is the one evasion a reintroduction could use deliberately.
effort: M
kind: gap
area: tests/_content_oracle.py, encumbered-content-purge
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (task 4.1 review)
pinned_at: 7d49c84
resume_command: "do: Decide whether the value oracle should decode candidate blobs from wide encodings before fingerprinting, or whether that evasion is accepted and stated at the oracle site."
context:
  - tests/_content_oracle.py
  - tests/load/test_packaging.py
  - scripts/purge/verify.py
blocked_by: []
---

## What

The value oracle tokenises text decoded as UTF-8. A copy of a fingerprinted
table re-encoded as UTF-16 decodes to something the tokeniser does not
recognise, so no fingerprint matches and every value scan passes it.

## Why it matters

Every value-matching surface in this spec inherits it: the packaging guard, the
redaction plan's content pass, and the verification runner's blob row. A
reintroduction that wanted to evade detection could use it deliberately, and it
is the only evasion class this spec's reviewers found that no guard reaches.

Kept at low importance for two honest reasons. It is **pre-existing** -- the
guard this spec replaced evades identically, verified -- so the purge did not
create it. And a wide-encoded copy of the material is not a shape anything in
this repository has ever produced, so the realistic risk is deliberate evasion
rather than accident.

## Evidence

Task 4.1's reviewer re-encoded the real pre-deletion table as UTF-16LE, placed
it at a neutral sdist path, and observed the guard pass -- then ran the same
plant against the pre-4.1 guard and observed it pass there too, establishing
the gap as inherited rather than introduced. The task 4.1 fix for undecodable
bytes does not reach this case, because a wide-encoded file decodes without
error into text that simply does not tokenise.

## How to pick it up

Read `tests/_content_oracle.py`'s decode-and-tokenise path. Decide between
attempting a small set of candidate encodings before tokenising -- which costs
scan time on every blob in history and risks false positives -- and accepting
the gap with a statement at the oracle site, in the way this spec has stated
its other detection losses. If accepted, the provenance record's given-up-
detection section is where it belongs. Done either way when a reader of the
oracle can find the decision.

## Open questions

Whether the entropy floor still holds for a wide-encoded window if decoding is
added. That is a property of the fingerprint set and would need re-measuring,
not assuming.
