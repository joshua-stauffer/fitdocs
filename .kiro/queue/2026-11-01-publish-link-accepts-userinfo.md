---
id: 2026-11-01-publish-link-accepts-userinfo
title: "publish valid_link accepts URLs with userinfo, so a credential-bearing link can reach a public page"
status: open
importance: low
importance_why: Low-medium; needs a misbehaving or compromised target to trigger, but the result is a credential in a public page's published region and no design invariant covers target answers.
effort: S
kind: bug
area: publish-core, src/fitdocs/publish/request.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: make fitdocs.publish.request.valid_link refuse links carrying userinfo (https://user:pw@host/x) and pin it with a test [queue: .kiro/queue/2026-11-01-publish-link-accepts-userinfo.md]"
context:
  - src/fitdocs/publish/request.py
  - tests/publish
  - .kiro/specs/publish-core/design.md
blocked_by: []
---

## What
`fitdocs.publish.request.valid_link` accepts a URL with userinfo
(`https://user:pw@host/x`). A target's answer can therefore put a
credential-bearing URL into the published region of a public page. The design
invariants cover request fields only, not the link a target returns.

## Why it matters
The published region is written into pages that may be shared publicly; a
credential in a link would leak with them.

## Evidence
`valid_link` in `src/fitdocs/publish/request.py` (RequestTypes link rule) has no
userinfo check. Confirm with `valid_link("https://user:pw@host/x")`.

## How to pick it up
1. Read the link rule in `src/fitdocs/publish/request.py`.
2. Refuse any link whose authority contains userinfo (`@`).
3. Add a test pinning the refusal next to the existing link-rule tests.
