# Research & Design Decisions

## Summary

- **Feature**: `post-templates`
- **Discovery Scope**: Extension (light discovery). `brief.md` holds the viability probes from discovery; this log records what the design added.
- **Key Findings**:
  - A real archive of about 2,600 pages confirms the two facts the design rests on: `$as_of` built from the page equals `pages.start_time_local` on every page, and the fresh placeholder survives byte for byte.
  - The SQL cost is negligible at full size (under 1 ms for the example, about 20 ms for an all-history join over `records`). The per-sync cost is reading pages, about 1 s.
  - `QuerySession` has every read the fill needs except one: whether the index holds this exact file. Adding that to `query` keeps the new package out of `_INDEX_IMPORTERS`.

## Research Log

### Real-data measurement (2026-11-07)

- **Context**: The brief's probes used synthetic data and said so. The requirements set a 5 s statement limit and a 30 s pass budget, so the numbers needed checking at full size.
- **Method**: A read-only script against the maintainer's wiki and index, at DuckDB 1.5.6. It printed counts and timings only, and the script stayed in the session scratch directory.
- **Findings**:
  - Selecting all top-level pages took 1.56 s, then reading each page again took 1.00 s. Reading each page once costs about 1 s. Hashing the corpus (`scan_workout_pages`) took 1.09 s.
  - `document_start_time(...).replace(tzinfo=None)` equalled `pages.start_time_local` on every page, with no mismatches and none missing from the index.
  - Every current page with an untouched region compared equal to `POST_PLACEHOLDER`.
  - `open_session` took 0.04 s. Screening and `json_serialize_sql` each took under 10 ms.
  - The example share query took 0.8 ms the first time and 0.4 ms after. A join of `records` and `pages` bounded to the week took 11.6 ms, then 3.3 ms. The same join over all history took about 19 ms.
  - Nearly all pages in that archive were at an older `doc_version`. They are unaffected by this feature (dated before any `since`) and need a regen before they can be published or filled.
- **Implications**: 5 s per statement is generous for honest SQL and still bounds a runaway. The 30 s budget is effectively a backfill bound. The pass should read each page once rather than call `select_pages` and then `read_page`.

### The SQL lint's shape

- **Context**: The brief said a lint must handle keyword forms and `query('...')`, but the probe code was not kept.
- **Sources**: A probe of `json_serialize_sql` at DuckDB 1.5.6.
- **Findings**:
  - `now()`, `today()`, `random()`, `uuid()`, `gen_random_uuid()`, `setseed()`, `get_current_time()`, `transaction_timestamp()` and `current_localtimestamp()` appear as `function_name`.
  - `current_date`, `CURRENT_TIMESTAMP` and `localtimestamp` appear as single-part `COLUMN_REF` nodes, with the case as typed.
  - `query('...')` and `query_table('...')` appear as `function_name` on a `TABLE_FUNCTION`, with the inner SQL hidden in a string constant. They are refused by name.
  - `USING SAMPLE` and `TABLESAMPLE` appear as a non-null `sample` key.
  - `WHERE $as_of IS NOT NULL` is invisible to the lint. Requirement 14.6 states this limit.
- **Implications**: The lint is a small pure walker over parsed JSON. The brief's measurement at the 1.2.0 floor (21 of 23 forms refused, the other two absent there) still stands.

### Value types

- **Sources**: The same probe.
- **Findings**: `HUGEINT` returns `int`, `DECIMAL` returns `Decimal('1.50')` keeping its scale, `DOUBLE` returns `float`, `DATE` returns `date`, `TIMESTAMP` returns `datetime` (a subclass of `date`), `BOOLEAN` returns `bool` (a subclass of `int`), and a list returns `list`.
- **Implications**: Conversion checks `bool` before `int` and `datetime` before `date`. A naive `datetime` binds as `TIMESTAMP`, so `$as_of` compares exactly with `start_time_local`.

### Integration points

- **`publish.pages`**: `select_pages` resolves named pages. `_top_level_pages` parses each document's frontmatter, which is what `read_page` does again.
- **`publish.ledger.load_ledgers(data_root, {})`**: returns every ledger on disk with no identity check and needs no connector settings. `fitdocs publish` works over the same on-disk set, including `_refresh_published`. This is why "landed" means any ledger on disk.
- **`publish/outcomes.py`**: `tests/publish/test_outcomes.py` pins a prefix ("appending is free"), so the new code moves no pin. The relay carries a byte-identical copy, so `scripts/sync_relay_shared.py` must run in the same change. The new code is not `from_target`, and the relay's deploy, envelope and seam versions do not move.
- **`docmerge`**: `_MARKER_RE` matches only `begin` and `end` markers, so a provenance comment starting `<!-- fitdocs:post-fill` cannot be read as a region marker.
- **`read_post_region`**: strips comments first, which removes the provenance comment and leaves a leading blank line that the reader already drops.
- **Versions**: `v0.2.0` shipped contract 16 and doc version 11. Contract 19 and doc version 12 are unreleased, so this feature rides 19 if no release is cut first.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks | Decision |
|---|---|---|---|---|
| New `post_template` package, with `cli` composing it | Mirrors `dashboards`: a pure core, one module that imports `query`, and `cli` holding the index report | Keeps `publish` free of `query`; boundary is testable by import scan | One more package | **Chosen** |
| Add the fill to `publish` | Reuse the package that owns the grammar | Fewer packages | Breaks the published rule that `publish` imports no `query`, the rule that keeps it offline | Rejected |
| Extend `dashboards` | Reuse the directive engine | Precedent | Only `cli` may import `dashboards`; its grammar requires chart keys; a TOML template shares nothing with it | Rejected |

## Design Decisions

### Decision: TOML parsed by the new package, `since` handed to publish

- **Context**: `post_template` depends on `publish` for the grammar, so `publish` cannot import it back.
- **Selected Approach**: `cli` calls `load_post_template` and passes `since` into `PublishPlan`. `publish` gets one optional date and stays unaware of templates.
- **Trade-offs**: `cli` holds one more preflight step. The dependency direction stays one way, and no YAML parser is added anywhere.

### Decision: "Waiting" lives in `contract`

- **Context**: `publish` and `post_template` both need to recognize the fresh placeholder, and every wording ever written must stay recognized.
- **Selected Approach**: `contract.POST_PLACEHOLDER_WORDINGS` and `contract.is_waiting_post`, beside the constant they describe.
- **Follow-up**: A future rewording adds to the tuple rather than replacing the entry.

### Decision: "Landed" lives in `publish.ledger`

- **Selected Approach**: `has_landed_post(ledgers, shas)`, used by `publish.engine` and `post_template.engine`, so the two cannot disagree. A record with a non-null digest counts as landed, the rule `decide` already uses.

### Decision: Freshness is a `QuerySession` method

- **Context**: The per-page gate needs the index's recorded `document_fingerprint`, and the brief wanted no new `_INDEX_IMPORTERS` entry.
- **Selected Approach**: `QuerySession.page_is_current(page_key, path, data)`, which hashes only the page in question and reads bookkeeping once per session.
- **Alternative rejected**: `page_drift` over a full scan. It returns counts rather than page identities and costs a full corpus hash per pass.

### Decision: Generalize the region splice

- **Generalization**: `publish.links.replace_published` is one region's copy of a generic operation. `docmerge` is documented as generic over region ids, so `replace_region` belongs there and `replace_published` delegates to it.
- **Scope kept small**: No other existing splice moves.

### Decision: A `Resolver` protocol in `engine`

- **Selected Approach**: `engine` declares a small protocol and `cli` passes an opened `resolve.SessionResolver`. This is the `dashboards` `SourceOpener` idiom.
- **Rationale**: It keeps every `query` import in one module, which the boundary guard can pin, and lets engine tests run without an index.

### Decision: One `fill` engine for three callers

- **Generalization**: The pass, `check` and `refill` differ only in which pages they consider, whether they write, and their limits. One per-page routine serves all three, so "what a page would say" cannot differ between `check` and the fill.

### Simplifications considered

- **Date-range option on `refill`**: Dropped. Naming pages or moving `since` covers it.
- **Stored cause for a waiting page**: Dropped. Publish names `check`, which computes the cause on demand, so no new state exists.
- **Filename-date prefilter for the pass**: Rejected for now. It would save most of the 1 s per sync, but a filename date can differ from the page's date on pages not yet migrated by the local-time fix. Revisit only if the cost is felt.
- **Second refresh output suppression**: Not added. The existing index line is accurate.

## Risks & Mitigations

- **One persistent index error holds back every fill.** The maintainer chose this on 2026-11-07: a wrong number that stays in a post is worse. Each sync says why, and pages retry automatically.
- **Author's SQL can still be unstable.** The lint is best effort. Requirement 14.6 states the limit, and a fill is a snapshot, so instability only appears on a refill.
- **A refresh with a session open reports `needs_rebuild`.** The session closes before the second refresh, with a test pinning it. See queue item `2026-11-07-index-refresh-with-open-reader-reports-needs-rebuild`.
- **Not measured:** Windows, contention between processes, and fsync cost at backfill scale. Each write is atomic and each run makes progress, so a slow backfill finishes over several syncs.

## References

- `brief.md` for the discovery probes, the stability table and the rule copies that move.
- `.kiro/steering/change-protocol.md` for the fixture discrimination gate.
- [DuckDB `json_serialize_sql`](https://duckdb.org/docs/stable/data/json/sql_to_and_from_json) for the serialized statement form.
