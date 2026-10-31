# Brief: publish-core

## Problem

The athlete wants each workout's post (a title, custom text and the
workout's metrics) to appear on the platforms where their training is seen,
straight from the wiki, without retyping anything. The first two targets are
intervals.icu and Strava. Today nothing in fitdocs writes to a remote
service.

Every target needs the same five things:

- what to post;
- whether this page has opted in;
- a dry run;
- a record of what was posted;
- a result vocabulary that carries no text from the remote service.

If each target built its own, they would drift. And the "nothing comes back
from the service" rule would be only as strong as the weakest target.

## Current State

- **The push capabilities are reserved, and none is driven.**
  - `PUSH_ACTIVITY`, `ANNOTATE_REMOTE_ACTIVITY` and
    `RESOLVE_REMOTE_ACTIVITY` exist in the capability vocabulary
    (`connectors/protocol.py:83-103`). The first two are
    `changes_remote=True, irreversible=True`, and all three are
    `driven=False`.
  - The irreversible flag exists so that "a later push command can require
    dry-run or confirmation" (`.kiro/specs/connectors/brief.md:74-78`;
    connectors Req 1.2-1.4).
- **No templating seam exists.**
  - The only `.format` templating is the tile URL (`tiles.py`).
  - Charts are drawn with "no template engine" (`render/charts/svg.py:3`).
  - No template library is among the runtime dependencies
    (`pyproject.toml`).
- **Page anatomy.**
  - The managed frontmatter keys (`contract.py:602-626`) are `title`,
    `date`, `start_time`, `sport`, `modality`, `indoor`, `distance_km`,
    `moving_time`, `avg_hr_bpm`, `avg_power_w`, `elevation_gain_m`,
    `calories_kcal`, `load_value`, `load_methodology` and `load_basis`, plus
    the identity keys.
  - The athlete-owned regions are `notes` and `workout`
    (`contract.py:933-945`).
  - The athlete owns only the effort-tag frontmatter keys
    (`contract.py:644-674`). Any other hand-added key is dropped with a
    warning (`contract.py:627-641`).
- **Service text reaches the output today.**
  - The intervals.icu connector puts up to 300 characters of redacted
    service body into user-facing messages
    (`connectors/intervals.py:106-118, 569-589`).
  - `connect` and `pull` print those messages.
  - The packaged skill tells the reader to "read the printed next step and
    report it" (`skills/fitdocs-workouts/SKILL.md:86`).
  - Publishing must not inherit this.
- **Precedents for a closed vocabulary.**
  - `DashboardCode` is append-only, its values are the JSON codes, and a
    prefix test pins its order (`dashboards/problems.py:27-65`). Its
    `ProblemDict` also carries free-text `message`/`fix`, which a publish
    outcome must not.
  - Others: query `OutcomeKind`, QA `FlagKey`, inbox `Disposition`,
    connectors `AuthFailureKind`.
- **CLI conventions.**
  - Exit codes are 0 / 1 / 2 / 130 (`cli.py:314-321`).
  - JSON output exists for `query` and `dashboard` only.
- **A ledger precedent.**
  - The connectors ledger `.fitdocs/connectors/<instance>.toml` is
    versioned, sorted, atomic and write-if-different
    (`connectors/ledger.py`).
  - It maps a pulled `remote_id` to the `sha256` of
    `fit-archive/<sha256>.fit`.
- **Duplicate hazard.** `HttpClient`'s DATA mode retries POST on 429, 5xx
  and transport errors (`connectors/http.py:297-317`). A non-idempotent post
  could land twice.

## Desired Outcome

- **Opt-in.** A workout page can opt in to publishing, per target.
- **Default post.** Without a per-page override, a preconfigured template per
  target produces the title and description, with values interpolated from
  the page.
- **Override.** Whoever curates the page can override the title and
  description in a new athlete-owned `post` region. fitdocs fills the
  placeholders inside it too.
- **Dry run by default.**
  - `fitdocs publish` changes nothing. It prints exactly what each opted-in
    page would post, and to which target.
  - `--yes` posts.
  - Running it again posts nothing new. A page whose composed post changed
    is posted again as an update.
- **Codes only.**
  - Every outcome is one code from a closed, documented, append-only
    vocabulary, explained in fitdocs's own words.
  - No text, identifier or URL from a target's API is printed, logged or
    written. The one exception is the activity link a target spec explicitly
    permits.
- **Links.** A posted page carries a fitdocs-owned link to the posted
  activity, one per target.
- **Discovery.** Targets can be discovered. A listing (for example
  `fitdocs publish --targets`) names the configured targets and their state
  as codes, in text and JSON.

## Approach

A target-neutral core that every target plugs into, in four stages:

1. **Compose** (offline and pure). It turns a page into a
   `Post(title, description)`.
   - The source is the page's `post` region if present, else the target's
     template.
   - Placeholders are filled only from the page's managed values. Numbers
     never come from typed text: this is "No LLM in the numeric path" applied
     to posts.
   - Absent values are handled explicitly and never rendered as `0`.
2. **Decide** (offline). It checks the opt-in and compares the composed
   post's digest with the publish ledger. The result is one of: would post,
   would update, unchanged, not opted in.
3. **Deliver** (network, only with `--yes`).
   - It hands the target a publish request: the `Post`, the activity's match
     keys (start time with its recorded offset, elapsed time, distance and
     sport), and a reference to the archived base `.fit` for
     upload-when-absent.
   - The target returns one outcome code and, optionally, its permitted
     link.
4. **Record.** The publish ledger under `.fitdocs/` keeps, per page per
   target, the digest, code, time and link. The page's fitdocs-owned links
   block is rendered from it.

**Templates.**
- They use a small placeholder syntax implemented in the package, such as
  `{distance_km}`. There is no template-engine dependency.
- No expressions and no attribute access: a template is configuration, not
  code.
- The design settles the syntax, including how a clause depends on a value
  being present.

## Scope

- **In**:
  - the closed publish-outcome vocabulary:
    - each code has a fixed explanation written by fitdocs;
    - it is append-only, and a prefix test pins its order;
    - every target uses it, and so does the relay (a seam with
      relay-accounts and strava-publish);
  - the publish-target contract that targets implement.
    - The design decides whether it is a connectors operation protocol
      driving the reserved capabilities, or its own seam.
    - Either way, composition lives outside `fitdocs.connectors`, which may
      not import `contract`, `docio` or `docmerge`. It hands targets plain
      values.
  - per-target templates in `fitdocs.toml`:
    - each target has a built-in default;
    - the placeholders are the page's managed values plus a few derived
      ones (pace, for example). The design names them;
    - an unknown placeholder is a configuration error (exit 2, nothing
      sent);
  - the athlete-owned `post` region (wiki-contract and workout-docs
    amendments), preserved across regeneration;
  - per-page, per-target opt-in. The mechanism is a requirements decision.
    One candidate is a user-owned frontmatter key such as `publish:`,
    joining the effort-tag keys as frontmatter the athlete owns;
  - `fitdocs publish [PAGES…] [--to TARGET] [--yes] [--format text|json]`,
    with dry run as the default and the existing exit codes;
  - the target-discovery listing;
  - the publish ledger and its version;
  - the fitdocs-owned links block on the page, rendered from the ledger
    (`CONTRACT_VERSION` main + 1 at landing; `DOC_VERSION` if the page
    layout changes);
  - single-attempt delivery for non-idempotent calls. The design decides
    idempotency keys;
  - the agent skill's publishing section:
    - it says fitdocs can publish to several configured backends;
    - it explains how to list them, how to write the `post` region and how
      to read the outcome codes;
    - it names no backend. They are discovered through the CLI (maintainer,
      2026-10-31);
  - the documentation for people.
- **Out**:
  - any concrete target (`intervals-publish`, `strava-publish`,
    `relay-intervals`);
  - media and photos, deleting a post, planned workouts;
  - a publish-target plugin kind (a follow-on);
  - a daemon or scheduler. The publish command is one-shot.

## Boundary Candidates

- Composition (pure, offline) against delivery (network) against record
  (ledger and links block).
- The outcome vocabulary as a standalone module with no imports, which the
  relay can share without pulling in the rest of the package.

## Out of Boundary

- How a target authenticates, finds its remote activity, or maps a
  service's responses into the vocabulary. Each target spec owns its own
  mapping.
- The relay service.

## Upstream / Downstream

- **Upstream**:
  - workout pages: the managed keys, plus the `docio`/`docmerge` readers;
  - connectors: the credential store, `http.py`, the capability vocabulary;
  - `activity-identity`: `identity.matching.pair_evidence`, the one match
    rule targets reuse.
- **Downstream**: `intervals-publish`, `strava-publish`, `relay-intervals`.
  The relay's API envelope returns this vocabulary.

## Existing Spec Touchpoints

- **Extends**:
  - `wiki-contract`: the `post` region, the opt-in mechanism, the links
    block, the publish ledger location, `CONTRACT_VERSION`;
  - `workout-docs`: rendering the `post` placeholder and the links block;
  - `connectors`: driven flags and a single-attempt write mode in `http.py`,
    if the target contract is a connectors protocol;
  - `docs-site`: a publishing page;
  - the packaged agent skill.
- **Adjacent**:
  - `dashboards`, the other closed-code reporter;
  - `effort-tags`, the precedent for athlete-owned frontmatter.

## Constraints

- **Codes only.** Nothing a target's API returns is printed, logged or
  written. The only exception is the activity link a target spec permits:
  - intervals.icu: a link built from the activity id;
  - Strava: a relay redirect URL carrying only fitdocs's own publication
    id.

  Outcome explanations are text written by fitdocs.
- **Network only when posting.** Without `--yes` the command makes no
  network call. Discovery lists the configured targets from configuration.
- **Two conditions to post.** Posting needs both the page's opt-in and
  `--yes`.
- **Absent data is `None`.** A placeholder for an absent value never renders
  `0`. The design chooses between omitting the clause, a declared fallback,
  or refusing the page with a code.
- **Determinism.** Composition is pure: the same page and configuration give
  the same post bytes.
- **Testing discipline.** Every new assertion owes a named mutation
  (`tech.md`, Testing).
