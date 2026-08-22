# Project Structure

## Organization Philosophy

Small installable Python package + SDD harness. Two hard rules inherited from
the pkm project this plugs into:

1. **Code/data split.** The repo holds only code, templates, schema, and
   docs. Personal data — `.fit` files and generated workout markdown — lives
   under a user-configured directory, never inside the repo.
2. **Raw is immutable; rendered is regenerable.** Source `.fit` files are
   never modified; workout documents are derived artifacts that can always be
   re-rendered from the `.fit` + athlete profile (user-supplied answers are
   persisted, not re-prompted).

## Directory Patterns

### Package source
**Location**: `src/fitdocs/`
**Purpose**: The installable package — parsing, metrics, load calculators,
rendering, CLI. Layered: `ingest` (fit parsing → activity model) → `metrics`
(derived values) → `load/` (calculator interface + implementations, one module
per methodology, e.g. `load/threshold.py`) → `render/` (per-sport markdown
templates + chart generation) → `cli`.

### Bundled data
**Location**: `src/fitdocs/load/<methodology>/data/` (or alongside the module)
**Purpose**: Lookup tables a calculator needs, shipped with the package. No
methodology currently bundles data; anything shipped here must be
redistributable under a license the project can honor.

### Reference docs
**Location**: `docs/reference/`
**Purpose**: Research and methodology writeups backing specs (e.g.
`fitdocs-ai-reference.md`). Durable, not spec-lifecycle-bound. A writeup here
is research, not shipped data. A third-party methodology's writeup and its
extracted lookup tables were kept here as the record of a withdrawn
methodology; that retention was **reversed 2026-07-30** because publishing
the repository would publish them. The `encumbered-content-purge` spec
deleted both from the tree. That spec's history rewrite removes both from
git history as well, once it runs. Nothing carrying a third party's
redistribution restriction belongs here once this repository is public.

### SDD harness
**Location**: `.kiro/` (steering, specs, settings), `.claude/skills/`
**Purpose**: cc-sdd workflow. Steering = persistent knowledge; specs = one
directory per feature with brief/requirements/design/tasks.

### Tests
**Location**: `tests/`
**Purpose**: Mirrors `src/fitdocs/` layout. Golden-file tests for rendered
markdown; fixture `.fit` files under `tests/fixtures/`.

## Naming Conventions

- **Files/modules**: `snake_case.py`; markdown docs `kebab-case.md`.
- **Generated workout docs**: date-prefixed kebab-case slugs
  (`YYYY-MM-DD-<sport>-<slug>.md`), matching pkm wiki conventions.
- **Load calculators**: one module per methodology named after it
  (`threshold.py`), registered under a short id (`"threshold"`).

## Code Organization Principles

- Dependencies point one way: `cli → render → load/metrics → ingest → model`.
  The activity model is the shared contract; renderers and calculators never
  re-read `.fit` files directly.
- `LoadCalculator` implementations declare their required inputs so the CLI
  can prompt for missing data generically — no calculator-specific prompting
  code in the CLI.
- Output documents must be valid, readable markdown in any renderer
  (GitHub, Obsidian, plain `cat`); PKM-specific affordances (frontmatter,
  wikilinks) degrade gracefully.

---
_Document patterns, not file trees. New files following patterns shouldn't require updates_
