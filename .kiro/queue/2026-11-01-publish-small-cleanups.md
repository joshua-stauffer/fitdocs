---
id: 2026-11-01-publish-small-cleanups
title: "Small publish-core cleanups and wording amendments from validation"
status: open
importance: low
importance_why: Dead fields, one missing test and wording drift; no defect on a normal path.
effort: S
kind: chore
area: publish-core, src/fitdocs/publish, .kiro/specs/publish-core
created: 2026-11-01
surfaced_by: "/kiro-validate-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: work through the six cleanups (a)-(f) in the item [queue: .kiro/queue/2026-11-01-publish-small-cleanups.md]"
context:
  - src/fitdocs/publish/engine.py
  - src/fitdocs/publish/pages.py
  - src/fitdocs/publish/links.py
  - src/fitdocs/publish/targets.py
  - .kiro/specs/publish-core/requirements.md
  - .kiro/specs/publish-core/design.md
  - .kiro/steering/structure.md
blocked_by: []
---

## What
(a) `PublishReport.configured` is set and pinned but never read; the CLI
re-derives it from `by_name`.
(b) `links.read_published` has no production caller.
(c) No engine/CLI unit test catches a report that silently drops an UNCHANGED
row when two pages are unchanged; only `tests/test_publish_e2e.py` does.
(d) When the last `sources` ref is foreign, `source_shas` drops it and a new
record is keyed by an extra's digest (`engine.py` ~345), while
`completed_activity` treats `refs[-1]` as the base (`pages.py` ~241); hand-damaged
sources only.
(e) Requirements Req 4.1 says the built-in default composes a post for every
current page whatever values it lacks, but the default title is bare `{title}`,
so a page with no usable title is refused (`value_missing`); amend the wording.
(f) design/structure.md say `publish.targets` imports the connectors published
surface; it imports `connectors.errors/http/protocol/secrets` by module path
(all names on `__all__`); clarify.

## Why it matters
Dead code and spec wording that disagree with the implementation mislead the next reader.

## Evidence
The cited files and lines.

## How to pick it up
Take each in turn: remove or use (a)/(b), add the unit test for (c), decide (d)
with the maintainer, and amend the prose for (e)/(f).
