# Brief: inbox

## Problem

The plugin story says "fitdocs defines an inbox where `.fit` files land to
be processed" — a standing interface the user's export/sync tooling
(HealthFit → iCloud, watch sync, manual drops) plugs into. Today ingestion
is a CLI argument: `fitdocs sync SOURCE` walks whatever path it is handed.
The demo wiki already uses an `inbox/` directory by convention, but the
tool has no notion of it: no configured path, no drain semantics, and none
of the safeguards watch-folder tools have converged on. Files mid-copy from
cloud sync, `.syncthing.*`/`.DS_Store` droppings, and known-bad real-world
files (16/22 real HealthFit files once crashed the parser) are all handled
by luck or not at all.

## Current State

- `fitdocs sync SOURCE` walks recursively for `*.fit`, strictly read-only
  on the source dir; content-hash dedupe against `fit-archive/` makes
  re-runs idempotent and no-op (`sync.py`).
- Per-file failures are isolated (`FileFailure`) with warn-and-continue and
  a separate additive warnings channel (route-maps work); exit codes
  0/1/2 defined in `cli.py`.
- No configured inbox path, no stability/quiet-period check, no ignore
  patterns, no quarantine disposition for repeatedly-failing files, no
  post-consumption disposition policy.

## Desired Outcome

- `fitdocs.toml` declares the inbox (data-root-relative by default,
  `inbox/`); bare `fitdocs sync` drains it. Explicit `SOURCE` arg keeps
  working and overrides.
- The standard watch-folder safeguards (paperless-ngx consume-dir is the
  reference): stability check for partially-written files, default ignore
  patterns (dotfiles, `.tmp`/`.part`, `.syncthing.*`, `.DS_Store`),
  content-hash dedupe (exists), and an explicit, documented disposition
  policy for processed files.
- Failing files get a quarantine channel (reported, not looping, not
  silently skipped) consistent with the existing warn-and-continue report.
- The inbox contract is documented as a public interface: "get files here,
  however you like; fitdocs does the rest."

## Approach

Layer a thin, configured interface over the existing sync engine's
read-only, idempotent, warn-and-continue contract. One-shot drain (beets
`import` style), no daemon/watcher — a CLI that the user or their scheduler
invokes sidesteps FSEvents-on-cloud-storage unreliability. Key design
decision to settle in requirements: disposition — keep today's
leave-in-place read-only semantics (archive copy is already the processed
marker) vs. move-to-processed; ecosystem experience (Calibre delete
complaints) argues never delete/move silently.

## Scope

- **In**: inbox config key + resolution; no-arg `sync` drain; stability
  check; ignore patterns; quarantine/disposition policy + reporting;
  interface documentation.
- **Out**: filesystem watchers/daemons; automated acquisition from
  devices/platforms (still deferred); non-`.fit` formats; scheduling
  (user's cron/agent invokes the CLI).

## Boundary Candidates

- Inbox resolution + file-selection policy (new, thin) vs. per-file
  processing pipeline (existing engine, unchanged).
- Disposition/quarantine reporting vs. the existing SyncReport channels.

## Out of Boundary

- What the docs look like or who owns them (wiki-contract).
- Load calculators (plugin-api).

## Upstream / Downstream

- **Upstream**: fit-ingest (parser robustness feeds quarantine policy),
  workout-docs/route-maps sync engine and report channels.
- **Downstream**: distribution (documents the interface); LLM-wiki agents
  and user automation that drop files and invoke `sync`.

## Existing Spec Touchpoints

- **Extends**: the sync/report behavior established in workout-docs and
  route-maps (adds channels/config, must not change existing semantics).
- **Adjacent**: fit-ingest error taxonomy (quarantine reasons).

## Constraints

- Source/inbox directory remains strictly read-only unless a disposition
  policy explicitly configured by the user says otherwise; never delete.
- Idempotency and byte-identical re-run guarantees must hold.
- Inbox often lives on iCloud/Dropbox/Syncthing storage — no reliance on
  filesystem event APIs; polling/one-shot semantics only.
