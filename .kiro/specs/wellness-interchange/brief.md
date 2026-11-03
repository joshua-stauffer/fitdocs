# Brief: wellness-interchange

## Problem

Wellness enters fitdocs only through source-specific formats: Apple Health
exports, a Garmin data export, and intervals.icu
(`src/fitdocs/wellness/formats/`). Two new producers have nothing to deliver
in:
- **A relay provider whose native schema cannot be published.** The hosted
  Garmin provider receives daily summaries in a schema that comes from
  Garmin's confidential developer documentation. The public CLI cannot
  parse it without publishing it.
- **A user's own connector plugin** (the plugin-api update in this
  extension), pulling wellness from a source with an API token.

Both need a format fitdocs defines and documents, which any producer can
write.

## Current State

- **Formats are registered** in `src/fitdocs/wellness/registry.py`, each a
  `FormatSpec` with an id, an archived suffix, a parser and a supersession
  rule.
  - Archive entries live under `wellness-archive/<format id>/<sha256><suffix>`
    (`wellness/archive.py:76-86`).
- **A format names one source** (`entry.format.source.id`,
  `wellness/archive.py:184`). Every file of a format is therefore attributed
  to the same source.
- **The series and its attribution:**
  - The engine merges snapshots into one normalized daily series. Every
    value is tagged by its source (Phase 12).
  - The wellness attribution variant renders a Garmin line for
    Garmin-sourced values (`render/attribution.py:71-91`).
- **Consumers:** workout-wellness, recovery, hr-derivation and the index's
  `wellness_daily`.

## Desired Outcome

- A fitdocs-defined, versioned daily wellness file, documented in
  `docs/wellness.md`, which the wellness inbox recognizes.
- **What a file carries:**
  - one or more days;
  - each metric present with its unit;
  - the source declared per file (an id, plus an optional device), so a
    Garmin-sourced day is attributed to Garmin and a plugin's day to its own
    source.
- **Metrics:** it covers what the normalized series holds: resting HR, HRV,
  sleep, weight, SpO2, VO2max and steps.
- **Values:**
  - an absent metric is absent, never `0`;
  - the latest entry wins per day and metric.
- **Validation:** a malformed file is refused with a message, like the
  other formats. The existing formats are unchanged.

## Approach

- **A JSON document, parsed with the standard library.** It carries a
  format identifier and version, a declared source, and a list of daily
  records.
- **Registered like any wellness format,** with one model change: the source
  is read per file instead of per format. The design picks whether
  `FormatSpec` gains a per-file source hook, or the source registry gains
  declared sources.
- **Attribution follows the declared source** through the existing wellness
  attribution.

## Scope

- **In**:
  - the format definition and its version;
  - the parser and recognizer;
  - the per-file source;
  - archive naming;
  - supersession;
  - attribution through the declared source;
  - docs, with a worked example;
  - golden fixtures.
- **Out**:
  - any source's native schema;
  - converting from any source (producers convert);
  - intraday or per-sample data;
  - new metrics the normalized series does not already hold;
  - delivering files (connectors and the relay do that).

## Boundary Candidates

- The format definition: the schema, the version, and the units.
- Recognition and parsing into `DaySnapshot`s.
- Source declaration and its effect on the archive and attribution.

## Out of Boundary

- Pulling wellness through the relay (relay-held-files).
- Plugins that emit the format (plugin-api).
- The hosted Garmin conversion (the hosted deployment).

## Upstream / Downstream

- **Upstream**: wellness-store (the registry, archive, engine and series);
  the wellness attribution in render.
- **Downstream**:
  - relay-held-files: wellness items are delivered as interchange files;
  - plugin-api: plugins with `pull-wellness`;
  - the hosted Garmin provider;
  - consumers, unchanged.

## Existing Spec Touchpoints

- **Extends**: wellness-store, which gains a registered format with the
  source declared per file. Take the amendment number and any version
  literal at main + 1 when landing.
- **Adjacent**:
  - apple-health-import and wellness-pull, the other formats, left
    untouched;
  - recovery and workout-wellness, as readers.

## Constraints

- **Standard library only.** No runtime dependency, and stays offline
  (`tech.md`).
- **Absent is `None`, never a fabricated `0`** (CLAUDE.md hard rule).
- **The format is a public contract.** Version it and change it only by
  appending.
- **The public-text rule:** examples use neutral or fitdocs-defined field
  names. Nothing mirrors Garmin's developer documentation.
- **Personal data never enters the repo.** Fixtures are synthetic.
