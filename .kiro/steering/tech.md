# Technology Stack

## Architecture

Installable Python CLI with one-way pipelines:

```
.fit file → ingest (garmin-fit-sdk) → activity model → derived metrics
         → load calculators (pluggable) → markdown + SVG render → data root

wellness inbox file → wellness.intake → wellness-archive/
                   → wellness.engine → normalized daily series in wellness/
                   → wellness.read_series → consumers, including wellness_daily
```

The `fitdocs` CLI runs no server and no background jobs. One database: a
derived, disposable analytics index outside the data root, rebuilt from the documents and archived `.fit`
files, never read back into a document, except the chart regions and chart
assets of dashboard pages under `dashboards/`; workout, history and block
documents never read it. Workout documents and their derived
values remain re-derivable from archived `.fit` sources and the athlete
profile; the index itself is a cache, not state, and deleting it costs only
rebuild time. The index's `wellness_daily` rows additionally come from the
normalized wellness series through the public reader. Wellness recognition,
archiving, parsing, merging, rebuilding, checking and indexing stay offline and
add no runtime dependency; the store uses the standard library and existing
`tomli_w`, with its package dependencies limited to `layout`, `settings` and
`units`.

A separately deployed relay server lives in `relay/` (package `fitdocs_relay`,
Starlette served by uvicorn). It is its own distribution with its own
dependencies and is never part of the `fitdocs` release. It keeps one
database, SQLite by default and PostgreSQL through an extra; the `fitdocs` CLI
never imports it. The two sides share only the standard-library-only modules
listed in `SHARED_MODULES` in `scripts/sync_relay_shared.py` (today
`relay_codes`, `relay_envelope`, `publish.outcomes`, `relay_targets` and
`identity.strict`), which the relay carries as pinned copies
under `relay/src/fitdocs_relay/shared/` that a cross-check test keeps
identical to their originals in the `fitdocs` package. The relay's deploy
contract, wire envelope (client-facing) and wrapper seam are versioned; the
versions are recorded in `relay/CHANGELOG.md`, tied to the constants by
`relay/tests/test_contract.py`.

## Core Technologies

- **Language**: Python 3.11+
- **Packaging/tooling**: `uv` (project + lock); installable via
  `uv tool install` / `pipx`; single console entry point `fitdocs`
- **FIT parsing**: `garmin-fit-sdk` (official SDK; proven in fitdocs.ai —
  same decode flags: `apply_scale_and_offset=True`, `expand_components=True`)

## Key Libraries

- `garmin-fit-sdk` — `.fit` decode (records, sessions, laps, sets, devices)
- `duckdb` — the analytics index, imported only by `fitdocs.index.store`; index
  connections use no extensions or external file access.
- `pillow` (`>=13.0.0`, no upper bound) — the map basemap: decode tiles,
  composite, encode WebP; imported only by `fitdocs.basemap`, lazily inside
  functions. The floor carries the CVE fixes (compact-chart-assets design).
- CLI + prompting: `typer` + `rich` (interactive prompts for missing
  load-calculator inputs)
- Charts: **hand-generated SVG** (no runtime JS). Embedded in markdown via
  standard image links so they render in Obsidian, GitHub, and any viewer.
  No matplotlib dependency unless a spec proves we need it.
- YAML frontmatter: `pyyaml`

## Network and Credentials

Network-capable code in the `fitdocs` package lives in exactly two places: the
map-tile fetch (`fitdocs.tiles`) and the connector transport
(`fitdocs.connectors.http`); the relay server (`relay/`) is outside this scope. Connector requests happen only during
`fitdocs connect` (one authentication call per attempt; for a registering
relay instance, a capabilities read, a registration start and one poll per
stated interval), `fitdocs disconnect` (one revocation call for a relay
instance, one disconnect request to its bound relay for a Strava instance,
none otherwise), `fitdocs pull`
(a single-attempt token renewal when a login-style token is due, then
bounded, retried data calls) and `fitdocs publish --yes` (for each page it
sends to a target, any of a listing, an update and an upload request, one at
a time); every other command — `sync`, `regen`,
`load`, `dashboard`, `recovery`, `check`, `query`, `history`, `plan`, `derive-benchmarks`, `index`, and
rendering — makes no connector request, whether or not connectors are
configured, and keeps its existing map-tile behavior (rendering a map may fetch missing
basemap tiles unless tile requests are disabled). `fitdocs publish` without
`--yes` and `fitdocs publish --targets` make none. For a Strava instance,
`fitdocs connect` makes one connect-start request and one poll per stated
interval to its bound relay, `fitdocs disconnect` makes one disconnect
request, and `fitdocs publish --yes` makes at most two requests per page; no
fitdocs command contacts Strava. Both of the package's
network paths go through the standard library's `urllib` only, sending the one composed
fitdocs User-Agent; connectors add no runtime dependency (beyond the
standard library they use only the already-required `tomli_w`). `fitdocs
query` runs agent SQL read-only under a locked DuckDB configuration with
external access and extension loading off. `fitdocs dashboard` and the
dashboard pass run chart SQL through the same sandbox. Every DuckDB connection fitdocs
opens has extension auto-install, extension auto-load and external file
access disabled; the allow-list binds fitdocs's own connections, not an
outside client that opens the index file. Connector credentials and
tokens, relay tokens included, are stored per user through the same credential
store outside the data root — one TOML file per instance in a
per-user directory, never inside the data root (a credentials directory
that resolves there is refused) — and the connectors package makes no
clock call of its own (`now` and `sleep`
are always injected by the caller, never read from the system clock
inside the package). An automated boundary guard enforces the network
allow-list, the module-dependency direction, and the no-clock rule.

## Development Standards

### Type Safety
Full type hints; `mypy --strict` on `src/`. The activity model is typed
dataclasses/pydantic-free (stdlib `dataclasses` preferred — keep the
dependency footprint small for an installable tool).

### Code Quality
`ruff` (lint + format). Absent data is `None`, never a fabricated `0` —
metrics that lack inputs return `None` and downstream renders/calculators
handle it explicitly (principle inherited from fitdocs.ai).

### Testing
`pytest`. Golden-file tests: fixture `.fit` files in → expected markdown/SVG
out. Load calculators are validated against their source methodology's own
published worked examples, not only against themselves (e.g. the Coggan IF
example: 210 W NP ÷ 280 W FTP = 0.75).

Every new assertion owes a named mutation it dies on — green proves an assertion
ran, not that it could fail. Gate and named anti-patterns:
`change-protocol.md` § Fixture Discrimination.

## Development Environment

### Required Tools
- `uv` (Python 3.11+ managed by uv)

### Common Commands
```bash
# Dev: uv sync
# Test: uv run pytest
# Lint: uv run ruff check . && uv run ruff format --check . && uv run mypy
# Run: uv run fitdocs <command>
```

## Key Technical Decisions

1. **Compute rich metrics locally.** fitdocs.ai imports NP/IF/decoupling/
   zone-times from Intervals.icu; we implement them in-package (formulas
   documented in `docs/reference/fitdocs-ai-reference.md`) so metric
   computation needs no external API call. (The map tiles and the explicit
   connector commands are the tool's only network paths — see "Network and
   Credentials" above.)
2. **Static SVG charts.** The power-vs-HR hero graph is reproduced as a
   generated SVG (band-normalized overlay, elevation backdrop) written next
   to the markdown doc. Renderer-portable; no plugins required.
3. **Strength via FIT `set_mesgs`.** The reference app never parses sets;
   we do, to make weight-training docs first-class.
4. **Pluggable load calculators.** `LoadCalculator` interface: declares
   required athlete/activity inputs, may decline a sport, returns typed load
   results. Registered by id (`"threshold"` first). Missing inputs → generic
   interactive prompt flow, answers persisted to the athlete profile. The
   `training-load` spec owns the *carrier* and ships no methodology of its
   own; which calculator runs is an explicit configured default, never
   registration order.
5. **Data-root contract** (mirrors joshua-stauffer/pkm): output location from
   `--out` flag > `FITDOCS_DATA` env > `.fitdocs/data-root` file; loud failure
   otherwise; never writes into a code repo by default. When installed inside
   the pkm system, the data root points at the pkm wiki so workout docs land
   as wiki pages (frontmatter + `[[wikilinks]]` per pkm's `wiki-schema.md`).

---
_Document standards and patterns, not every dependency_
