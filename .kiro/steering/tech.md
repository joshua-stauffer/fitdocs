# Technology Stack

## Architecture

Installable Python CLI with a one-way pipeline:

```
.fit file → ingest (garmin-fit-sdk) → activity model → derived metrics
         → load calculators (pluggable) → markdown + SVG render → data root
```

No server, no database, no background jobs. State = the user's files
(source `.fit`s, generated markdown/SVG, a small athlete profile file, the
per-user connector credentials files outside the data root, and the
connector ledgers under `.fitdocs/`).
Everything is re-derivable from the `.fit` + profile.

## Core Technologies

- **Language**: Python 3.11+
- **Packaging/tooling**: `uv` (project + lock); installable via
  `uv tool install` / `pipx`; single console entry point `fitdocs`
- **FIT parsing**: `garmin-fit-sdk` (official SDK; proven in fitdocs.ai —
  same decode flags: `apply_scale_and_offset=True`, `expand_components=True`)

## Key Libraries

- `garmin-fit-sdk` — `.fit` decode (records, sessions, laps, sets, devices)
- CLI + prompting: `typer` + `rich` (interactive prompts for missing
  load-calculator inputs)
- Charts: **hand-generated SVG** (no runtime JS). Embedded in markdown via
  standard image links so they render in Obsidian, GitHub, and any viewer.
  No matplotlib dependency unless a spec proves we need it.
- YAML frontmatter: `pyyaml`

## Network and Credentials

Network-capable code lives in exactly two places: the map-tile fetch
(`fitdocs.tiles`) and the connector transport
(`fitdocs.connectors.http`). Connector requests happen only during
`fitdocs connect` (one authentication call per attempt) and `fitdocs pull`
(a single-attempt token renewal when a login-style token is due, then
bounded, retried data calls); every other command — `sync`, `regen`,
`load`, `check`, `history`, `plan`, `derive-benchmarks`, and rendering —
makes no connector request, whether or not connectors are configured, and
keeps its existing map-tile behavior (rendering a map may fetch missing
basemap tiles unless tile requests are disabled). Both network paths go
through the standard library's `urllib` only, sending the one composed
fitdocs User-Agent; connectors add no runtime dependency (beyond the
standard library they use only the already-required `tomli_w`; the frozen
runtime dependency list is unchanged). Connector credentials and tokens are
stored per user outside the data root — one TOML file per instance in a
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
