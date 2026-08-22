# Technology Stack

## Architecture

Installable Python CLI with a one-way pipeline:

```
.fit file → ingest (garmin-fit-sdk) → activity model → derived metrics
         → load calculators (pluggable) → markdown + SVG render → data root
```

No server, no database, no background jobs. State = the user's files
(source `.fit`s, generated markdown/SVG, a small athlete profile file).
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
   documented in `docs/reference/fitdocs-ai-reference.md`) so the tool works
   fully offline.
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
