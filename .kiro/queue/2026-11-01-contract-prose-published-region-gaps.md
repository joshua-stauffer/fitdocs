---
id: 2026-11-01-contract-prose-published-region-gaps
title: "Contract prose omits the publish/post regions and misdescribes who refills the published region"
status: open
importance: low
importance_why: Documentation inaccuracy only.
effort: S
kind: docs
area: publish-core, docs/ownership-contract.md, src/fitdocs/contract.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: fix the two prose gaps in docs/ownership-contract.md and src/fitdocs/contract.py described in the item [queue: .kiro/queue/2026-11-01-contract-prose-published-region-gaps.md]"
context:
  - docs/ownership-contract.md
  - src/fitdocs/contract.py
blocked_by: []
---

## What
(a) The training-history paragraph of `docs/ownership-contract.md` (~165-168)
names the notes/workout regions and effort-tag keys a workout document reserves
but omits `publish` (and `post`). Verify the current text first; task 8.1 may
already have fixed it.
(b) The `REFRESHED_REGIONS` docstring in `src/fitdocs/contract.py` (~996-1000)
says each region's "owning pass replaces its content after every page-writing
run". That is false for `published`, which only `fitdocs publish --yes` refills.

## Why it matters
Readers of the contract get a wrong list of reserved names and a wrong refresh rule.

## Evidence
The two line ranges above.

## How to pick it up
Re-read both passages, fix what is still wrong, and keep any existing docs pins green.
