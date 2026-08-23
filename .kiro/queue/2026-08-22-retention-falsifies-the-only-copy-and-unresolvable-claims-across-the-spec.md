---
id: 2026-08-22-retention-falsifies-the-only-copy-and-unresolvable-claims-across-the-spec
title: Retaining fitdocs_oss falsifies the "only copy anywhere" and "permanently unresolvable" claims that survive across design.md, research.md and Requirement 9.3
status: open
importance: medium
importance_why: Req 9.3's absolute "every pre-replacement commit identifier is thereafter permanently unresolvable" is written into the shipped provenance record by task 9.2, while a permanently retained fitdocs_oss resolves every one of them — the record would state a falsehood in the same document that records the retention.
effort: M
kind: inconsistency
area: encumbered-content-purge
created: 2026-08-22
surfaced_by: kiro-review of Amendment 3 (chore/retain-old-remote)
pinned_at: c3d2201
resume_command: "do: reconcile Req 9.3's 'permanently unresolvable' claim and the surviving 'archive is the only copy anywhere' sentences with Amendment 3's retention, before task 9.2 writes the provenance record"
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/research.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Amendment 3 retains `fitdocs_oss` permanently. That falsifies two families of
claim that Amendment 3 corrected only where they are *executed*, leaving them
standing where they are *read*.

**(a) "The archive is the only copy of the old history anywhere."** Corrected
on `chore/retain-old-remote` in `scripts/purge/replace.py` (shipped source)
and in `tasks.md` task 8.3 (an open task). Still standing, inside Amendment
3's declared carve-out:

- `design.md` — the archive description, the rollback analysis, and the
  archive-exposure argument (*"one copy, held offline by the maintainer, is
  the smallest exposure that still keeps the operation reversible"*), which
  was never re-derived for a world with two copies
- `research.md` — never carved out by any amendment

**(b) Req 9.3's "permanently unresolvable".** `requirements.md` states that
every pre-replacement commit identifier is *thereafter permanently
unresolvable, there being no mapping by construction*. That is true of the
replaced local repository and false of GitHub: the retained `fitdocs_oss`
resolves every one of those identifiers, indefinitely, to anyone with access.

This one is sharper than (a) because **task 9.2 writes it into the shipped
provenance record** — the same document that, from Amendment 3, also records
the retention in Section 7. As written, §3 and §7 of that record contradict
each other.

## Why it matters

The provenance record is the durable, shipped artifact a future auditor reads.
A record asserting permanent unresolvability beside a record of a permanently
retained copy is not a small inconsistency: it is the audit trail failing at
exactly the claim it exists to support, and Req 8.6's *"which action was
required rather than which was assumed"* is the standard it fails against.

Amendment 3 deliberately did **not** widen its own edit to these, to keep the
pre-8.1 change bounded: what ships in the certified tree and what an executor
acts on were corrected; what is read as the record of a superseded plan was
carved out and named. This item is the record of that boundary, and the work
left on the far side of it.

## How to pick it up

Before task 9.2 runs, decide for Req 9.3 between:

**(a) Scope the criterion textually**, as Amendment 3 did to Requirement 8 —
"permanently unresolvable *in the canonical repository*" — and have 9.2 state
the retained repository's resolvability explicitly alongside it.

**(b) Leave the criterion and constrain the record**, requiring §3 to carry
the scope inline so the two sections cannot be read as contradicting.

(a) is more consistent with what Amendment 3 already did and is probably
right; either way the provenance record must not assert unqualified permanent
unresolvability.

For the "only copy" family, the cheaper fix is a single annotation at each
site rather than a rewrite — they are accurate descriptions of a superseded
plan, and only the *safety* claims (the exposure argument especially) need
re-deriving. Re-derive that one: two copies, one offline and one on GitHub
under a private repository whose privacy is now load-bearing, is a different
exposure calculation than the one the design made.

Related: [[2026-08-22-the-Rm-verification-row-cannot-name-a-remote-url-as-its-subject]].
