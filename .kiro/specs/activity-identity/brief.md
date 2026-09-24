# Brief: activity-identity

## Problem

One training session often exists as several `.fit` files:
- the device original (a Garmin Edge ride, a Stryd run file);
- a phone-side re-export (HealthFit's copy of what Apple Health received);
- a partner-API copy (intervals.icu's file for a Garmin-synced ride);
- a hand export from Garmin Connect, whose bytes Connect re-encodes.

fitdocs recognizes a file as belonging to an existing page only by exact
bytes or by HealthFit's session UUID. Any other file of the same session
becomes a second page. On 2026-09-12 this blocked 761 Garmin originals from
replacing their degraded HealthFit copies. The only way through was a script
that hand-edited the managed `sources` key.

Phase 8 makes it the common case. Connectors will deliver device originals
and partner copies of activities the athlete already has. Every one of them
duplicates a page until the engine knows it is the same activity.

## Current State

- **Identity is exact only.**
  - `sync._process_file` (`src/fitdocs/sync.py:1126`) skips a file whose
    `fit-archive/<sha256>.fit` exists.
  - Otherwise `find_document` (236-291) scans `workouts/*.md` frontmatter:
    a `uuid` match first, then membership in the page's `sources` history.
  - `layout.activity_uid` (`layout.py:193-212`) is HealthFit's
    `SESSION UUID` developer field when present, else the sha. `uuid` is
    written only when the field exists (`render/frontmatter.py:121-125`), so
    re-rendering from a Garmin file drops it.
- **`file_id` is never read** (`ingest/__init__.py:56-66`). Two identity
  signals are therefore unavailable:
  - the device serial with `time_created`. Garmin originals carry the Edge's
    serial, and `time_created` equals the session start;
  - the manufacturer and product, which tell a device original
    (`manufacturer=garmin`/`stryd`) from HealthFit (`development`, its own
    serial).
- **Frontmatter cannot reproduce a strict rule.** `distance_km` has 0.01 km
  resolution, and `moving_time` is moving time, not elapsed
  (`frontmatter.py:138-142`). A strict match needs keys the page does not
  have, or a re-parse of the archived base.
- **A matched page keeps its old path while its stem is recomputed**
  (`sync.py:1269-1272`). A corrected start time therefore leaves a stale
  filename and orphaned assets. The 2026-09-12 adoption renamed 243 pages
  and deleted 287 assets by hand. One stem collision was resolved only by
  ordering renames.
- **`sources` models succession** (the last entry is the current file,
  `layout.py:348-355`), not a set of files that each play a role.
- **Contract:** `DOC_VERSION` 5 (`contract.py:174`), `CONTRACT_VERSION` "4"
  (275), `MANAGED_KEYS` (364-387), pinned by `tests/test_contract.py` and
  `tests/test_ownership_contract.py`.

## Desired Outcome

- **One page per session, whatever arrives.** A file that is the same
  session as an existing page joins that page. It never creates a second
  one, however it arrives: hand drop, HealthFit export, or connector.
- **A stated, calibrated match rule.** Same sport, and agreement on session
  start, elapsed time and distance within tolerances derived from the
  measured pairs:
  - Stryd↔HealthFit: start identical to the second; distance equal to
    0.01 m; elapsed differs by 8–9 s.
  - Garmin↔HealthFit: start identical to the second; distance within 5 m;
    elapsed within about 1 s; timer time differs by up to 400 s, so timer
    time is never a key.
  - A second, wider path for re-exports shifted by whole hours (the 2026-09-12
    rule: |Δduration| ≤ 5 s and |Δdistance| ≤ 10 m within ±36 h), assigned
    one-to-one, nearest start first.
  - Device serial plus `time_created` equality as the strongest signal, when
    both files carry it.
  - A counter-example the rule must reject: two similar 10 k runs that a
    90 s / 300 m rule matched.
  - Activities without distance (strength, some indoor sessions) need their
    own stated rule, or none.
- **Ambiguity is reported, never resolved by guessing.** Two candidate pages,
  or two new files for one page, produce a warning naming the files and a
  `check` finding. Nothing merges, and arrival order decides nothing.
- **Roles on the page.**
  - Each page records its files with a role: one **base**, whose file the
    page is rendered from, and zero or more **extras**. `sources` stays the
    archive history.
  - The base is chosen by a configurable source precedence. The default
    ranks a device original above a partner-API or phone-side copy of the
    same session.
  - Source kind is derived from the file itself (`file_id`
    manufacturer/product, writer markers such as HealthFit's developer
    fields), never from which connector delivered it.
  - Without `channel-merge`, extras are recorded but not composed: the page
    renders from its base.
- **Base changes re-render cleanly.**
  - A new base re-renders the page with the user regions carried, as today.
  - The stem is recomputed, the page renamed, and the old stem's assets
    removed, with renames ordered so two corrections in one run cannot
    collide.
  - The session UUID of a HealthFit extra is kept on the page.
- **Order independence.** The page for a set of files is the same whichever
  file arrived first.
- **Archive semantics hold.** Every file of the set is archived. A re-drain
  of any of them is a skip, and a regen rebuilds the same page from the
  archive.

## Approach

- **Ingest.** Read `file_id` into a typed file-identity value on the
  activity.
- **Matching.** A pure module takes an incoming activity's identity and
  summary plus the corpus's page records, and returns one of: same page
  (with role), new page, or ambiguous (with candidates). `find_document`
  delegates to it after its exact checks.
- **Page keys.** Base selection and role recording become managed keys
  through the wiki-contract amendment. Precise start, elapsed and distance
  values go into managed keys too, if the design decides matching must not
  re-parse the archive.
- **Rename.** A rename step inside the per-document atomic write.

## Scope

- **In**:
  - the file-identity model fields and their decoding;
  - the match rule, its tolerances and its ambiguity handling;
  - source-kind derivation and the precedence setting (a `fitdocs.toml`
    table — not named `[sources]`, which collides with the managed key);
  - role and identity keys on the page, and the contract amendment;
  - base-change re-render, rename and asset cleanup;
  - UUID retention;
  - `check` findings;
  - a regen path that rebuilds roles from the archive;
  - closing the queue item.
- **Out**:
  - composing channels from extras (`channel-merge`);
  - fetching files (`connectors`);
  - any network access;
  - merging two sessions that are genuinely different recordings;
  - an interactive "which page is this?" prompt.

## Boundary Candidates

- File identity at ingest (`file_id` fields).
- The pure matcher: rule, tolerances, cardinality, ambiguity.
- Roles and precedence: source-kind derivation, configured order, base
  choice.
- Page lifecycle on a base change: re-render, rename, asset cleanup, UUID
  retention.

## Out of Boundary

- Which *channels* a page shows from which file (`channel-merge`).
- Where files come from (`connectors`, `intervals-connector`, a plugin).
- Load values: a base change re-renders the page, and the load pass rescores
  it as it would any rewritten page.

## Upstream / Downstream

- **Upstream**: `fit-ingest` (decode); `workout-docs` and `wiki-contract`
  (page, frontmatter, `sources`, ownership contract); `inbox` (drain);
  `sync` (the engine).
- **Downstream**:
  - `channel-merge` composes the roles this spec records;
  - every connector relies on this spec before real use;
  - a future push connector keys remote ids to the page identity this spec
    stabilizes.

## Existing Spec Touchpoints

- **Extends**:
  - `wiki-contract`: Amendment 4, the role and identity keys, the version
    bump, and ownership-contract prose on roles;
  - `fit-ingest`: the `file_id` fields;
  - `workout-docs`: its requirement 3.6 identity.
- **Adjacent**:
  - `inbox` (skip-without-archive semantics must hold);
  - `activity-qa-flags` (a merged page's flags);
  - `plan-resolution` (reads stems: a rename must leave block pages
    consistent after the next plan pass);
  - `load-history` (reads pages, not files).

## Constraints

- **Never guess.** Tolerances are stated constants with their measured
  source, and one-to-one assignment is mandatory. Each rule owes a named
  mutation (`change-protocol.md` § Fixture Discrimination): widening a
  tolerance, dropping the sport check, or accepting a second candidate must
  each turn a test red.
- **Fixtures are synthesized** FIT files with the measured shapes: a
  HealthFit-style copy with a `SESSION UUID` developer field and
  manufacturer `development`, a Garmin-style original with serial and
  `time_created`, and a Stryd-style file. No personal data.
- **Contract rituals.** The version bump, `MANAGED_KEYS` pins, the
  `FORBIDDEN_LITERALS` registration for any new reader, and the
  confinement guard's view of renamed paths.
- **Absent is `None`.** A file without `file_id` or distance is matched only
  by the rule that does not need them, or not at all.
