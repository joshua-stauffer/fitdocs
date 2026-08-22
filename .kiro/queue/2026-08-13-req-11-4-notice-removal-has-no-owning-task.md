---
id: 2026-08-13-req-11-4-notice-removal-has-no-owning-task
title: The maintainer's Req 11.4 decision — remove the copyright notice text itself — is generator work with no task, and 7.2 is the only chance to do it
status: open
importance: high
importance_why: Task 7.2 is the one-shot, unrepeatable rewrite. A replacement rule that is not in the rule set when it runs can never be applied to history afterwards, and Req 11.4 is a requirement the spec must satisfy to be complete.
effort: M
kind: gap
area: encumbered-content-purge, scripts/purge/replacements.py
created: 2026-08-13
pinned_at: df8910b
resume_command: "do: Add a task to .kiro/specs/encumbered-content-purge/tasks.md, between 6.4 and 7.2, that extends build_rules with copyright-notice and trademark-mark replacement rules per the maintainer's 2026-08-12 Req 11.4 decision, then implement it. Read requirements.md Requirement 11 criterion 4 and criterion 6 first, then scripts/purge/replacements.py's module docstring on case handling."
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - scripts/purge/replacements.py
blocked_by: []
---

## What

Requirement 11 criterion 4 says no file at any commit reachable from any ref
shall contain the third party's copyright notice or trademark notice.

Identity redaction alone does not achieve that: it removes the *name* from
inside the notice, leaving `Copyright (c) <redacted>. <reserved-rights phrase>`
standing. Measured previously at 42 surviving notice sites and 16 surviving
trademark marks.

On **2026-08-12 the maintainer decided the notice text itself must go**, not
merely the name inside it — chosen over the reading that a nameless notice is
no longer "the third party's" notice. That decision is recorded in the shared
agent log (`DECISION`, 2026-08-12T19:12:12Z) and in the session memory, but
**no task owns the work**, and `build_rules` does not generate these rules
today.

## Why it matters

Task 7.2 runs `git filter-repo` once. A replacement rule absent from the rule
set at that moment cannot be applied to history afterwards — the whole reason
task 6.4 exists as a tested generator rather than a hand-written spec file.
Every other Req 11 criterion is carried by a task; this one is not.

## What the work involves

Not merely two more rows. The constraints task 6.4 established apply:

- **`--replace-text` cannot preserve case.** `build_replacement_expressions`
  hard-codes `(?i)`, under which a capitalised rule also matches the lowercase
  form and the first listed rule wins for both. The generator emits
  case-sensitive rules, one per observed case variant; the notice rules must
  follow that, not reintroduce `(?i)`.
- **Req 11.6 still applies** — redact the identity, retain the record, do not
  falsify what the record states. A notice replaced by nothing may leave prose
  asserting a licensing constraint that no longer has a referent. The
  maintainer's chosen framing was a neutral statement recording that redacted
  third-party material was present and withdrawn.
- **Req 11.12** forbids substituting a replacement proper name.
- The six invariants must still hold simultaneously, including invariant 4
  (zero mangled forms) and invariant 6 (the tip no-op). A notice rule that
  matches a partial phrase is a new mangling source.
- Whatever anchoring the notice rules need should be checked against an
  oracle, not against a passing suite — see the adjacency table in
  `tests/purge/test_replacements.py` and why it exists.

## How to pick it up

1. Read `requirements.md` Requirement 11, criteria 4, 6 and 12.
2. Read `scripts/purge/replacements.py`'s module docstring — the case-variant
   rule and the by-construction/measured distinction both bind this work.
3. Measure the current surviving-notice population yourself against the tip
   `7.1` freezes; the 42/16 figures predate several redaction rounds.
4. Write the task into `tasks.md` between 6.4 and 7.2 with its own observable,
   then implement it under the same discrimination gate.

## Done when

`build_rules` emits notice and trademark-mark rules, the six invariants hold
with them in the set, the masked table renders them for maintainer approval,
and a task in `tasks.md` owns the work rather than a queue item.
