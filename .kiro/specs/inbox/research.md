# Research & Design Decisions: inbox

## Summary

- **Feature**: `inbox`
- **Discovery Scope**: Extension (integration-focused discovery over the existing sync engine, plus ecosystem verification of watch-folder practice)
- **Key Findings**:
  - The converged watch-folder stability technique *is* "stat twice, compare size + mtime, separated by a settle interval" — paperless-ngx implements exactly that. Its known blind spot (cloud placeholder files that stat as complete but hold no data) is directly relevant here, because the brief names iCloud as a likely inbox location.
  - The ecosystem's two dominant failure modes are both about trust: tools that **delete on success** surprise users (Calibre auto-add, paperless consume dir), and tools that **leave failures in place with no memory** get stuck (paperless requires manually moving a failed file out and back in). The requirements' leave-in-place default and content-keyed quarantine record are the direct answers.
  - The existing engine already supplies everything the drain needs: `_process_isolated` isolates per-file failures, the archive-last write ordering makes interruption safe, and content-hash dedupe against `fit-archive/` *already is* the "processed" marker — so leave-in-place idempotency needs no new state.
  - Composing (`DrainReport` carries a `SyncReport`) rather than extending the shared report is what makes "explicit-source behavior is unchanged" provable rather than asserted.

## Research Log

### Existing architecture: what the drain can reuse unmodified

- **Context**: The brief scopes this feature as "a thin, configured interface over the existing sync engine". Establishing exactly where the seam is determines whether this is a small spec or a re-architecture.
- **Sources Consulted**: `src/fitdocs/sync.py`, `cli.py`, `config.py`, `tiles.py`, `layout.py`, `load/profile.py`; `.kiro/specs/route-maps/design.md`.
- **Findings**:
  - `sync()` and `regen()` already differ *only* in discovery and skip policy; both funnel items through `_process_isolated` → `_process_file`. A third discovery policy is the natural shape of a drain.
  - The archive copy is written last and its presence is the skip condition (`archive.exists() and not force`). Leave-in-place disposition therefore inherits idempotency with zero new state.
  - `tiles.py` established the `fitdocs.toml` table-reader contract (absent ⇒ typed defaults, keys default independently, unknown keys ignored, malformed ⇒ typed error → CLI exit 2). `[inbox]` should be indistinguishable in behavior.
  - `profile.py` established the data-root state-file contract (absent ⇒ empty, malformed ⇒ loud, atomic save via `mkstemp` + `os.replace`).
  - The CLI already resolves everything fallible before any engine call, which is exactly the ordering the inbox pre-flight needs to satisfy "a configuration error writes nothing".
- **Implications**: The design is three modules — policy (`inbox.py`), state (`quarantine.py`), and one new engine entry point (`drain()` in `sync.py`) — with no modification to any pipeline stage.

### paperless-ngx consume directory (the reference implementation)

- **Context**: The brief names paperless-ngx's consume dir as the reference for watch-folder safeguards. Its concrete defaults and its *mistakes* are both useful.
- **Sources Consulted**: [`document_consumer.py`](https://github.com/paperless-ngx/paperless-ngx/blob/main/src/documents/management/commands/document_consumer.py), [configuration docs](https://docs.paperless-ngx.com/configuration/), [usage docs](https://docs.paperless-ngx.com/usage/), [troubleshooting](https://docs.paperless-ngx.com/troubleshooting/), [setup docs](https://docs.paperless-ngx.com/setup/), [inotify(7)](https://man7.org/linux/man-pages/man7/inotify.7.html).
- **Findings**:
  - Stability check is literally `stat()` in a loop comparing `mtime` and `size`, sleeping between passes; on exhaustion it logs a timeout and gives up. Defaults: `CONSUMER_POLLING_DELAY` 5 s, `CONSUMER_POLLING_RETRY_COUNT` 5 (~25 s worst case), `CONSUMER_INOTIFY_DELAY` 0.5 s. A separate guard retries `open("rb")` 50× at 10 ms before refusing with "OS reports file as busy still".
  - Default ignore patterns are precisely the sync-tool droppings list: `.DS_Store`, `.DS_STORE`, `._*`, `.stfolder/*`, `.stversions/*`, `.localized/*`, `desktop.ini`, `@eaDir/*`, `Thumbs.db`.
  - **It deletes consumed files** ("think of this folder as a temporary location") and **leaves failures in place with no memory** — the documented recovery is to manually move the failed file out of the folder and back in.
  - Documented reason to prefer polling: inotify does not catch events on network filesystems (NFS named explicitly; inotify(7) states applications "must fall back to polling"). No paperless doc names cloud-sync mounts specifically.
- **Implications**: (a) Validates the stat-twice technique and a small settle interval. (b) The `._*` / `.stfolder/*` / `.stversions/*` / `.localized/*` entries are all dot-prefixed — a single "ignore any dot-prefixed path component" rule subsumes them without enumerating tools, and the remaining entries (`desktop.ini`, `Thumbs.db`, `@eaDir/*`) cannot be `.fit` candidates anyway. (c) Its delete-on-success and forget-on-failure behaviors are exactly what this spec's disposition policy and quarantine record are designed *not* to repeat.

### Cloud-sync artifacts and the stat-check blind spot

- **Context**: The constraint "inbox often lives on iCloud/Dropbox/Syncthing storage" needs concrete artifact names for the ignore policy, and its failure modes need to be understood before trusting a stat-based check.
- **Sources Consulted**: [Syncthing syncing docs](https://docs.syncthing.net/users/syncing.html), [Syncthing file versioning](https://docs.syncthing.net/users/versioning.html), [Dropbox cache folder](https://help.dropbox.com/delete-restore/cache-folder), [LoC AppleDouble format description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000625.shtml), [Eclectic Light on Sonoma iCloud Drive](https://eclecticlight.co/2023/10/25/macos-sonoma-has-changed-icloud-drive-radically/), [rsync man page](https://download.samba.org/pub/rsync/rsync.1).
- **Findings**:
  - Syncthing writes `.syncthing.<name>.tmp` (Windows `~syncthing~<name>.tmp`), degrading to a hash-named temp for long names; temp files can persist up to a day after a failed transfer. `.stfolder` is the folder marker, `.stversions` the version store.
  - Dropbox stages through `.dropbox.cache` at the Dropbox root (auto-cleared roughly every 3 days; sourced from a help-centre summary rather than a fetched page).
  - macOS emits `.DS_Store` and AppleDouble `._*` sidecars on filesystems without native xattr support — network shares and exFAT/NTFS, i.e. exactly the volumes a synced inbox tends to live on.
  - **The important one**: pre-Sonoma iCloud used visible `.<name>.ext.icloud` stubs; macOS Sonoma replaced these with APFS **dataless files** that keep the real name, report the *full downloaded size* from `stat`, and have no data extents. Detection requires `SF_DATALESS` in `st_flags`; a read blocks while the kernel fetches, and fails when offline.
  - Coarse mtime granularity is a real, cited weakness: rsync ships `--modify-window` because FAT stores times at 2-second resolution.
- **Implications**: Two design consequences. (1) The dot-component rule plus the four required junk patterns cover every artifact that could plausibly wear a `.fit` extension (`._*.fit` is the realistic one). (2) A stat-only readiness check **cannot** see an unmaterialized iCloud file, and naively letting it through would make the subsequent read fail and — under a plain reading of "a file that fails processing is quarantined" — permanently quarantine a file whose only problem was timing. The design therefore splits readiness into stat stability plus the read it must perform anyway to hash content, and treats a read failure as a *deferral*. Detecting `SF_DATALESS` directly was rejected as platform-specific for no additional benefit: the read probe covers the same case portably.

### Never-delete: evidence that silent removal is a trust hazard

- **Context**: The brief calls out "Calibre delete complaints" and asks the design to settle disposition explicitly.
- **Sources Consulted**: [MobileRead thread 224565 — "Calibre deletes original file after adding books to library!?"](https://www.mobileread.com/forums/showthread.php?t=224565); paperless-ngx usage docs (above); [beets configuration reference](https://beets.readthedocs.io/en/stable/reference/config.html).
- **Findings**:
  - Calibre's normal import copies and leaves the source alone; its *auto-add watch folder* deletes. The reported surprise is the mode switch — the same tool behaving destructively only on the watched path. The accepted answer is "stop using the Automatic Adding feature".
  - paperless has the same shape and had to put an explicit warning in its documentation.
  - beets is one-shot and user-invoked (`beet import`, no daemon or watcher), and its defaults are non-destructive: `import.copy = yes`, `import.move = no`. There is no delete option; `move` is the destructive one and is strictly opt-in.
- **Implications**: Leave-in-place must be the default and deletion must not exist at all — not merely be unimplemented. Modeling disposition as a two-member enum makes deletion unrepresentable rather than a future footgun, and the never-delete guarantee becomes a documented part of the public interface.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Inbox resolution only in the CLI | CLI resolves a path from config and calls existing `sync()` | Smallest change; zero engine impact | Cannot express stability, quarantine, or disposition — they are per-file decisions inside the batch | Rejected: satisfies R1/R2 only |
| B. Policy module + new engine entry point (**chosen**) | `inbox.py` decides selection/stability/disposition, `quarantine.py` owns state, `drain()` composes them around the unchanged pipeline | Reuses the pipeline verbatim; policy is independently testable; engine stays the only writer | `sync.py` grows a third entry point | Mirrors how `regen()` already differs from `sync()` |
| C. Generalize `sync()` with an injected discovery/policy strategy | One entry point parameterized by a policy object | No new entry point | Speculative abstraction; changes the signature every existing caller and test uses, undermining "explicit-source behavior is unchanged" | Rejected by the simplification lens |
| D. Extend `SyncReport` with inbox channels | Add defaulted `deferred`/`quarantined`/`moved` tuples, as route-maps did for `warnings` | Single report type; one CLI presentation path | Loads a shared contract with per-feature channels that mean nothing for `regen` or explicit-source sync | Rejected in favor of composition (see decision below) |
| E. Daemon / filesystem watcher | Long-running process using FSEvents/inotify | "Instant" ingestion | Explicitly out of scope; unreliable on the cloud mounts the inbox lives on (inotify(7), paperless setup docs) | Rejected by the brief and the constraint |

## Design Decisions

### Decision: Compose `DrainReport` around `SyncReport` rather than extending it

- **Context**: Requirement 7.1 asks for deferred/quarantined/moved reporting; Requirement 7.3 demands that explicit-source sync's reports be unchanged.
- **Alternatives Considered**:
  1. Add defaulted tuples to `SyncReport` (the route-maps `warnings` precedent).
  2. A `DrainReport` value that *contains* a `SyncReport` plus the inbox channels.
- **Selected Approach**: (2). `sync()` and `regen()` keep returning the identical `SyncReport`; `drain()` returns `DrainReport(inbox, sync, deferred, quarantined, moved, move_failures)`.
- **Rationale**: The `warnings` precedent was right for a channel that applies to *every* engine entry point (a map can be omitted during regen too). Deferral, quarantine, and disposition are meaningless for `regen` and for explicit-source sync. Composition keeps the shared contract honest and makes 7.3 a type-level fact rather than a test assertion.
- **Trade-offs**: Two report shapes and two CLI presentation functions instead of one. Accepted — `_report` stays untouched, which is itself the regression guard.
- **Follow-up**: Confirm during implementation that no existing test constructs or destructures `SyncReport` in a way the drain path needs to change.

### Decision: Readiness is stat stability *plus* a read probe

- **Context**: The stat-twice check is the standard, but macOS iCloud dataless files defeat it, and the inbox is expected to live on iCloud.
- **Alternatives Considered**:
  1. Stat only — accept that unmaterialized files fail and get quarantined.
  2. Stat plus `SF_DATALESS` detection in `st_flags`.
  3. Stat plus treating a failed content read as a deferral.
- **Selected Approach**: (3). The drain must read each stable candidate anyway to compute the content hash for the quarantine check; an `OSError` there defers the file instead of failing it.
- **Rationale**: (1) is actively harmful — a timing problem would be recorded as a permanent verdict about the file's content, and clearing it would require the retry flag or manual record editing. (2) is macOS- and filesystem-specific and buys nothing the read probe does not already cover (permissions, transient network mounts, and Dropbox's smart-sync equivalent all behave the same way). (3) turns the double-read into a safeguard that pays for itself.
- **Trade-offs**: Each admitted file is read twice per drain. Negligible for `.fit` files; the alternative (threading bytes into `_process_file`) would change the pipeline signature and weaken the "explicit-source path is untouched" guarantee.
- **Follow-up**: Verify with a real dataless-file scenario if a macOS test environment is available; otherwise simulate with an unreadable file.

### Decision: Quarantine keyed on content hash, with no timestamps in the record

- **Context**: Requirement 5.4 requires content-not-name identity; Requirement 7.4 requires a re-run to leave everything byte-identical.
- **Alternatives Considered**: name-keyed record; content-keyed with a `first_seen`/`last_seen` timestamp; content-keyed with no clock value.
- **Selected Approach**: Content-keyed (sha256 — the same identity the archive uses), entries sorted by hash, **no timestamps**, saved atomically and only when the serialized bytes differ.
- **Rationale**: Name keying breaks on the export-tool renames this feature exists to absorb. Timestamps would be the only clock-derived value in any fitdocs artifact and would make "a re-run writes nothing" depend on write-skipping alone rather than on the data genuinely being unchanged. Write-if-different makes 7.4 hold trivially and also protects the file from pointless rewrites.
- **Trade-offs**: No audit trail of when a file was quarantined. Acceptable — the record is an operational filter, not a log, and the reason string carries the diagnostic value.
- **Follow-up**: The record location (`<data-root>/.fitdocs/quarantine.toml`) is a Revalidation Trigger; distribution should mention it in the upgrade documentation.

### Decision: A single ignore rule (dot components) plus the four named patterns

- **Context**: Requirement 3.2 requires excluding dot-prefixed components; 3.3 names four junk patterns.
- **Selected Approach**: Ignore any candidate whose inbox-relative path contains a dot-prefixed component, plus `fnmatch` against `*.tmp`, `*.part`, `.syncthing.*`, `.DS_Store` and any configured patterns, matching case-insensitively against both the basename and the relative path.
- **Rationale**: Benchmarked against paperless's default list, the dot rule alone subsumes `._*`, `.stfolder/*`, `.stversions/*`, `.localized/*` and `.DS_Store`; the remaining paperless entries (`desktop.ini`, `Thumbs.db`, `@eaDir/*`) cannot carry a `.fit` extension. The named patterns are kept because the requirement names them and because they document intent to anyone reading the config. Matching the relative path as well as the basename lets a user exclude a subtree (`staging/*`) without a second configuration concept.
- **Trade-offs**: A user with a legitimately dot-prefixed directory of exports is excluded silently. Documented in the inbox contract.

### Decision: Move preserves the inbox-relative subpath and never overwrites

- **Context**: Requirement 6.2/6.3 — opt-in move with collision safety.
- **Selected Approach**: Destination = processed dir + the candidate's inbox-relative path, parents created on demand; on collision, `<stem>-<sha256[:8]><suffix>` then `-2`, `-3`, …; performed with `shutil.move` onto a path confirmed absent.
- **Rationale**: Preserving the subpath keeps whatever structure the export tool created. The content-derived collision suffix is deterministic, so the same file always lands on the same name. `shutil.move` (rather than `os.rename`) is required because the inbox is frequently on a different volume from the data root.
- **Trade-offs**: A same-content file moved twice (possible only after a manual re-drop) produces a second copy rather than being deduplicated. Correct under "never overwrite, never delete".

## Risks & Mitigations

- **Two readers now parse `fitdocs.toml` per command** (`[tiles]` and `[inbox]`) — negligible cost; keeps the tables decoupled. The shared filename constant moves to `layout.py` so there is one source of truth. A consolidated settings façade is left to wiki-contract/distribution if it ever earns its keep.
- **A drain that crashes between processing and the record write** re-fails the offending file once more on the next run — the safe direction (a genuinely bad file is reported again rather than silently suppressed).
- **`sync.py` grows a third entry point** (~150 lines). Mitigated by keeping all policy in `inbox.py`; extracting the drain would require exporting engine internals for no behavioral gain.
- **Quarantine could mask a systemic parser regression** (a bad release quarantines many valid files). Mitigated by the explicit retry option and by the record being a plain, human-readable, hand-editable TOML file whose location is documented.
- **Users may expect the inbox to be watched.** Mitigated by documenting "no watching, no scheduling" as an explicit part of the contract, per Requirement 8.2.

## References

- [paperless-ngx `document_consumer.py`](https://github.com/paperless-ngx/paperless-ngx/blob/main/src/documents/management/commands/document_consumer.py) — the stat-twice stability loop and busy-file guard.
- [paperless-ngx configuration](https://docs.paperless-ngx.com/configuration/) — consumer polling/inotify defaults and `CONSUMER_IGNORE_PATTERNS`.
- [paperless-ngx usage](https://docs.paperless-ngx.com/usage/) and [troubleshooting](https://docs.paperless-ngx.com/troubleshooting/) — delete-on-consume warning; stuck-failure recovery procedure.
- [paperless-ngx setup](https://docs.paperless-ngx.com/setup/) and [inotify(7)](https://man7.org/linux/man-pages/man7/inotify.7.html) — why polling is the portable floor on network filesystems.
- [Syncthing: Understanding Synchronization](https://docs.syncthing.net/users/syncing.html) and [File Versioning](https://docs.syncthing.net/users/versioning.html) — `.syncthing.*.tmp`, `.stfolder`, `.stversions`.
- [Dropbox: the cache folder](https://help.dropbox.com/delete-restore/cache-folder) — `.dropbox.cache` staging area.
- [Library of Congress: AppleDouble](https://www.loc.gov/preservation/digital/formats/fdd/fdd000625.shtml) — `._*` sidecars.
- [Eclectic Light: macOS Sonoma has changed iCloud Drive radically](https://eclecticlight.co/2023/10/25/macos-sonoma-has-changed-icloud-drive-radically/) — APFS dataless files, `SF_DATALESS`, stat reporting full size.
- [rsync man page](https://download.samba.org/pub/rsync/rsync.1) — `--modify-window`, FAT 2-second mtime resolution.
- [beets configuration reference](https://beets.readthedocs.io/en/stable/reference/config.html) — one-shot import; `import.copy = yes`, `import.move = no`.
- [MobileRead thread 224565](https://www.mobileread.com/forums/showthread.php?t=224565) — Calibre auto-add deleting source files; user trust fallout.
