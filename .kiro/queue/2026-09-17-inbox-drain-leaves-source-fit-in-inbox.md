---
id: 2026-09-17-inbox-drain-leaves-source-fit-in-inbox
title: Draining the inbox leaves the ingested .fit in inbox/ (fit-archive holds the copy) -- intended?
status: open
importance: low
importance_why: If intended nothing to do; if not, every drain re-ingests the same file until the athlete deletes it.
effort: S
kind: research
area: inbox spec, src/fitdocs/sync.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 3.2 round-3 review)
pinned_at: fbba78b
resume_command: "do: read the inbox spec's requirement on what happens to a drained file, confirm against src/fitdocs/sync.py, and close this item as intended or turn it into a bug"
context:
  - src/fitdocs/sync.py
  - .kiro/specs/inbox
blocked_by: []
---

## Evidence
- 3.2 round-3 review scratch run: `inbox/run.fit` still present alongside `fit-archive/<sha>.fit` after `fitdocs sync --out <root> --no-prompt` with `settle_seconds = 0`.

## Update 2026-09-29 (Phase 8 spec batch)

**Pulled files: decided by connectors.** The connectors spec keeps the
drain's LEAVE disposition and adds removal on the connector side: each pull
records its deliveries in the instance's ledger with their content hash, and
the *next* non-dry-run pull removes each earlier delivery whose hash is in
`fit-archive/` and whose file still hashes the same. The drain itself still
never deletes; a delivery that changed, failed, was quarantined or never
reached the archive is never removed; hand-dropped files are untouched.
Under the move disposition deliveries are left to the drain's move.

- `.kiro/specs/connectors/requirements.md` Requirement 8 (`:209-221`;
  criteria 8.5-8.9) and 15.4 (`:300`, the never-delete carve-out wording).
- `.kiro/specs/connectors/research.md` § "Decision: What LEAVE means for
  pulled files" (~:169-195, which cites this item) and the re-hash finding
  (`:25-28`).
- `.kiro/specs/connectors/design.md` Delivery component, `sweep()`
  (~:1147-1152).

**This item stays open, for hand-dropped files.** Its title and evidence are
about draining in general (the evidence run was a hand-dropped `run.fit`),
not about pulled files, so the connectors decision does not close it. What
the Phase 8 reading adds for the remaining question:

- LEAVE is the inbox spec's intended default, not an accident: inbox
  Req 6.1 (`.kiro/specs/inbox/requirements.md:125`) and
  `src/fitdocs/inbox.py:100-104` ("a no-op by construction ... Re-drains
  skip it because its content is already archived").
- The item's worry "every drain re-ingests the same file" is narrower in
  fact: the file is re-read and re-hashed on every drain
  (`src/fitdocs/sync.py:752` `read_bytes`, `:765` `sha256`) and then skipped
  as already archived; no document is rewritten.
- So the open decision is only whether that per-drain re-read cost for a
  large hand-dropped set needs anything (for example, docs steering such
  athletes to the move disposition), or whether to close this item as
  intended.
