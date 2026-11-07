# Brief: post-templates

## Problem

An athlete who publishes their workouts wants each post to say things the page
itself does not hold, such as this workout's share of the week's load so far.
Today there are two ways to get a post, and neither does that:
- **Write it by hand.** Run the SQL, read the number and type it into the page's
  `post` region, for every workout.
- **Use a template.** Its placeholders are a fixed list of 17 values read from
  the page, so it can't say anything about the week, the block or the athlete's
  history.

The athlete wants to define the post once and have every new page arrive with it
already written.

## Current State

- **`post` region.** Every workout page has one. A fresh page holds a hidden
  comment that renders as nothing. It is user-owned: fitdocs writes the
  placeholder once and "never touches this region again"
  (`docs/ownership-contract.md`).
- **Post grammar.** A title line, a blank line and a description, with `{name}`
  placeholders, `{?...}` optional clauses and `{{`/`}}` escapes
  (`publish/template.py`, `publish/compose.py`). `read_post_region` removes
  hidden comments before it reads the text.
- **`fitdocs publish`.** Composes offline, from the page and the settings file
  alone. It may not import `index`, `query` or `dashboards`
  (`tests/publish/test_boundary.py`). Any change to the composed text makes the
  next run decide `would_update` (`publish/engine.py`).
- **Query.** `open_session` and `QuerySession.run` (`query/command.py`) run one
  sandboxed read-only statement, with named parameters and a row cap. The CLI
  exposes no parameters. Only `cli` and `dashboards` may import `query`.
- **The dashboards precedent.** Hidden `<!-- fitdocs:chart -->` directives hold
  SQL, `$today` is the only parameter, and the pass runs after the index pass.
  Frozen charts store their rows and never re-query, because a date alone does
  not make a past result stable.
- **The gap.** Nothing fills a workout page from the index, and a published
  guarantee says nothing may: fitdocs "never reads the index back into a document
  or uses it to produce a document value", apart from dashboard charts.

## Desired Outcome

1. The athlete writes one template file, once: the post's text plus one SQL
   definition per variable.
2. After `fitdocs sync`, each new page's `post` region holds the finished text,
   with the real numbers, readable in the wiki.
3. `fitdocs publish` sends that text through its existing path.
4. The text does not change unless the athlete asks. `fitdocs regen` carries it
   byte for byte.
5. The athlete's words always win. Text they wrote or edited is never overwritten.

## Approach

**Fill the `post` region once, in a pass that runs after the index refresh.**

### Decided by the maintainer (2026-11-07)

- **Results are written into the `post` region.**
  - *Rejected: a separate values region.* The page would show tokens rather than
    numbers, and every page would gain a region.
  - *Rejected: resolving at publish time.* Publishing would need a built index, a
    dry run would depend on it, and the text would never appear in the wiki.
- **`regen` keeps the filled text; re-querying happens only on request.**
  - *Rejected: re-querying on every regen.* Regen would depend on a per-machine
    cache that may be absent, and could queue post updates nobody asked for.
- **Variables use the existing `{name}` grammar, not `$NAME`.** `{?...}` already
  handles absent values, page values work in the same template, and `$` stays
  reserved for SQL parameters.

### Discovery defaults

Stated to the maintainer with the questions above, with no objection.
Requirements review is the place to change them.

- `$as_of` is the workout's recorded start, and `$page_key` identifies the
  workout. SQL that doesn't use `$as_of` is refused.
- A page fills only while its `post` is the untouched placeholder and it is dated
  on or after the template's `since`.
- `fitdocs publish` refuses a page still waiting for its fill.
- There is one template file, not one per sport or per target.

### The template

```markdown
<!-- fitdocs:post-template
since: 2026-11-07
vars:
  percent_weekly_load:
    sql: |
      SELECT round(100 * max(load_value) FILTER (page_key = $page_key)
                   / NULLIF(sum(load_value), 0))::INT
      FROM pages
      WHERE date >= date_trunc('week', $as_of)
        AND start_time_local <= $as_of
-->
{title}

{?{percent_weekly_load}% of this week's load so far.}
```

- The body is exactly what an athlete would write in a `post` region, so there is
  no second language to learn.
- `since` is required. A template without it is refused, so turning the feature on
  can't fill a whole archive by accident. Backfilling means moving `since`.
- A variable may not shadow one of the 17 page placeholders. `load_value` is an
  obvious name to reach for, so this will come up.
- The example ignores `load_methodology`. A published recipe has to pick a
  methodology, and must sum `pages.load_value`, not read `weekly_load`, which holds
  the whole week as of the last refresh.

### Resolving a variable

- **Binding.** `$as_of` is the page's `start_time` with the offset dropped, derived
  from the page on every run, so it needs no stored state. It compares exactly
  equal to `pages.start_time_local`. Bind exactly the names screening reports:
  DuckDB errors on an excess or a missing parameter. Any other name is refused.
- **Shape.** One column and at most one row. Zero rows or NULL means absent. More
  than one row or column is an error for that page.
- **Values.** Decided by the Python value's type, because DuckDB 1.2 reports
  `NUMBER` for INT, DOUBLE, DECIMAL and HUGEINT. Integers, decimals, text and dates
  become text. A float is refused, with advice to cast it, because
  `0.30000000000000004` would otherwise reach a post. Non-finite values are failures.
- **Refused text.** A value holding a line break (the `_TITLE_BREAK` class in
  `publish/compose.py`), `<!--`, `-->` or `--!>` is refused. Such a value can
  silently lose text or damage the page's region markers.

### Composing and writing

A fill is the existing composer over a merged mapping, followed by one escape:

1. `compose_post` runs over the page's values plus the query's values.
2. `{` and `}` in the result are doubled.
3. The text is written as `title`, blank line, `description`, under a hidden
   provenance comment holding the template digest, the as-of and a digest of the
   text.

Every placeholder is expanded, so the region holds exactly what will be posted.
There is no partial-expansion code and no literal `{title}` on the page.

The grammar already says what's required:
- **`{var}` is required.** When it is absent the page is not filled (`value_missing`).
  It stays waiting and is retried on the next pass.
- **`{?...}` is optional.** The clause drops out, the page fills, and that is final
  until a refill. A value that arrives late, such as a load computed later, does not
  appear by itself.
- **An empty title** gives `title_empty`, and the page stays waiting.

The region then has three states, decided by comparing bytes:
- **Waiting:** equal to `POST_PLACEHOLDER`. It may be filled.
- **Filled by fitdocs:** the provenance digest matches the text. It may be refilled
  on request.
- **Athlete's:** anything else. It is never written, and the region's user-owned
  status stays as it is.

### When it runs

`sync`, drain and `pull --sync` only, with this order at the end of the command:

| Step | Note |
|---|---|
| index pass | existing |
| **fill pass** | runs only when the index outcome is `REFRESHED`, `UNCHANGED` or `BUILT` with no page or producer errors, and only for a page whose `document_fingerprint` in the index equals the current file |
| **close the session** | a refresh with a read-only session open in the same process reports `needs_rebuild` |
| **refresh** | only when the pass wrote a page. A plain `refresh_after_command(handoff=None)` made 0 derive calls and cleared the drift, because `post` is blanked in the render fingerprint |
| dashboard pass | uses the second report |

Without those gates a stale index becomes permanent text: with the page missing from
the index, the example SQL returns NULL at both DuckDB versions, and that would be
written as absent.

`regen` and `load` do not fill, so regen stays free of the index. A page they bring
current waits for the next sync or the explicit command. Like the dashboard pass, the
fill pass never fails the command and never changes its exit code.

### The command

One new command, working name `fitdocs post`. It is a dry run unless given `--yes`, as
`fitdocs publish` is.

- **Check.** Validates the template and shows each variable's value and the composed
  post for named pages, writing nothing. `fitdocs check` does not read this file, so
  this is the athlete's authoring loop.
- **Fill.** The pass's work for named pages or a range.
- **Refill.** Re-runs the queries for filled, unedited pages, and names any page with a
  landed post, because its text change will update the posted activity on the next
  `fitdocs publish --yes`.

A template edited after pages were filled is reported, never silently re-queried, as
with frozen charts.

### Publish

- **Awaiting refusal.** A page in the `since` window whose region is still the
  placeholder gets one new outcome code, appended to the closed vocabulary. Otherwise a
  `sync` then `publish --yes` with a busy index would send the default template, and a
  later fill would update the post.
- **The way out.** A page can wait forever: no index, a required variable on a ride with
  no load, or SQL that fails on that page. The refusal names the cause, and the athlete
  can make the variable optional, write the post by hand, or fix the SQL. Any edit to the
  region lifts the refusal.
- **Boundary.** `fitdocs.publish` may import no YAML parser, so `cli` parses the template
  and hands `since` to `PublishPlan`. Publish stays offline and still reads no index.
- **Already-posted pages.** Moving `since` back over them must not queue updates in bulk.
  The pass leaves a page with a landed post alone; only the explicit command changes it.

### What "stable" means, exactly

| Event | What happens to a filled post |
|---|---|
| `fitdocs regen`, `index --rebuild`, index deleted | nothing: the text is carried and no query runs |
| A later workout arrives | nothing. On a refill, SQL bounded by `$as_of` also can't see it |
| Late import, load recompute, benchmark or methodology change | nothing until a refill, which then shows the corrected number. That is what a refill is for |
| SQL uses the clock or randomness | a best-effort lint refuses what it can (below), and the rest is the author's responsibility |

### Viability (2026-11-07)

Probes ran on DuckDB 1.5.6 (the lock) and 1.2.0 (the floor), Python 3.11, on synthetic
data. They did not cover real data, a full-size index with stream tables, Windows or
contention between processes. The fsync cost of writes wasn't measured.

- **Binding and self-inclusion.** The example SQL returns the right share, excluding the
  previous Sunday and the later workout. A zero-load week returns NULL through `NULLIF`;
  without it the cast raises `Conversion Error: Type DOUBLE with value nan` at both
  versions.
- **Round trip.** Filled text read back through `read_post_region`, `override_templates`
  and `compose_post` gives an equal post, including with braces in values and in page
  titles, and with the provenance comment first (1.5.6 only).
- **Volatile SQL.** `json_serialize_sql` works under the locked sandbox at both versions.
  A prototype refused 23 of 23 clock and random forms at 1.5.6 and 21 at 1.2.0; the other
  two don't exist there and fail at run. `current_date` and friends parse as `COLUMN_REF`,
  and `query('SELECT random()')` hides the call in a string, so a lint has to handle both.
  It can't catch `first`, `any_value`, `LIMIT` without `ORDER BY`, or tables that depend on
  today (`blocks`), and `WHERE $as_of IS NOT NULL` satisfies the `$as_of` check. So it is a
  lint with a stated limit, not a guarantee.
- **Cost.** About 0.3 ms per statement on 2,600 synthetic pages. A pass filling 5 pages with
  3 variables is estimated at 4-5 s, nearly all of it the refresh (measured 2.9-3.2 s). A
  backfill of 2,500 pages is estimated at about 13 s, plus fsync.
- **Runaway SQL.** The 30 s default per statement would allow 7.5 minutes inside a 5-page
  sync. The pass needs a lower per-statement limit and a per-pass budget, and stops at the
  first timeout.
- **Placeholder equality.** It survives a real regen round trip, and the constant has had
  one wording ever. A future rewording would strand existing pages, so the classifier
  compares against a list of every wording.

No new runtime dependency: `pyyaml` is already required.

## Scope

- **In:**
  - the template file: format, parser, validation;
  - variable resolution with `$as_of` and `$page_key`;
  - the fill pass and its ordering;
  - the provenance comment and the three region states;
  - the new command: check, fill, refill;
  - the awaiting refusal in `fitdocs publish`;
  - the contract amendments, a docs page, and a worked recipe in the packaged skill.
- **Out:**
  - one template per sport or per target (a later file naming scheme can add them);
  - `fitdocs query` parameters on the command line;
  - re-querying on regen, or SQL at publish time;
  - an as-of dimension in the index;
  - filling history, block or dashboard pages;
  - expressions, loops or formatting options in the template; SQL does the formatting;
  - a post written by a model.

## Boundary Candidates

- **Template grammar.** Pure: file text in, a validated template or a located error out.
- **Variable resolution.** Binds, screens, runs and turns one value into text. The only
  part that imports `query`.
- **Fill decision and region write.** The three states, the provenance comment and the
  atomic splice. No SQL.
- **Pass orchestration.** Gates, order, second refresh and the report, in `cli`.
- **Publish refusal.** One code and an injected `since`, inside `fitdocs.publish`.

## Out of Boundary

- Publish's composition and targets, which see only the region's text.
- Index schema and producers: no new table or column.
- The `dashboards` package. It is the pattern, not a dependency: `parse_directive` requires
  chart keys and only `cli` may import dashboards.
- Whether a query's numbers are right. The author owns the SQL.

## Upstream / Downstream

- **Upstream:** `publish-core` (`compose_post`, `read_post_region`, `parse_template`),
  `analytics-query` (`open_session`, screening), `analytics-index` (`refresh_after_command`
  and its outcomes), `wiki-contract` (regions and ownership), `load-history` and the page
  columns the SQL reads.
- **Downstream:** per-sport or per-target templates; recipes for block and wellness context
  in posts.

## Existing Spec Touchpoints

- **Extends, through amendments carried by this spec:**
  - `publish-core`: the `post` ownership sentences, the new outcome code, the `PublishPlan`
    input.
  - `wiki-contract`: `post` ownership, and the template joining the files fitdocs reads but
    does not own (with `fitdocs.toml`, `athlete.toml`, `plans/`).
  - `analytics-index`: Req 5.6, the "never read back" guarantee, gains a second named
    exception.
  - `analytics-query`: its out-of-scope line on existing commands reading the index; the
    importer rule.
- **Adjacent:** `dashboards` (pattern), `intervals-publish` and `strava-publish` (receive
  whatever is composed; no change), `workout-docs` (renders the placeholder; no change).

## Constraints

- **The guarantee moves on purpose, and only as far as this.** The filled text is a snapshot,
  so a workout page stays re-renderable from `.fit` sources, the athlete profile and its own
  carried regions, and deleting the index still costs only rebuild time. The copies that move
  with this spec: `tech.md`, `structure.md` (the `query` importer rule),
  `docs/ownership-contract.md`, `docs/publishing.md`, `contract.py`, the `fitdocs-workouts`
  skill, and the product line "Numbers always come from the page's own computed values". They
  stay as they are until the spec lands, because they're true until then.
- **Documentation tests.** Per the maintainer's rule of 2026-11-03, this spec adds no test that
  reads docs, a changelog or a spec. A doc-binding test its edits turn red is deleted, not
  updated, and the amendment names it. Expected: pins of the "never read back" wording in
  `tests/index/test_contract_docs.py`, `tests/dashboards/test_published.py`,
  `tests/connectors/test_network_statements.py` and `tests/test_ownership_contract.py`.
- **Guards that move:** `_QUERY_IMPORTERS` in `tests/query/test_boundary.py`,
  `WRITING_ENTRY_POINTS` in `tests/test_confinement.py` (with `non_vacuous`), the outcome order
  pin in `tests/publish/test_outcomes.py`, and a new boundary test for the package, including no
  clock. Avoid a new `_INDEX_IMPORTERS` entry: `cli` holds the report, and the page key comes
  from `contract.sha_of_ref`.
- **Region splice.** Use the `(?:.*?\n)?` form from `publish/links.py`; the load-style regex
  misses adjacent markers. Write atomically, and only to pages of the current `DOC_VERSION`.
- **Versions.** `CONTRACT_VERSION` changes because a stated guarantee changes: it rides the
  unreleased 19 if no release has been cut when this lands, otherwise +1. `DOC_VERSION` should not
  move, since the page's shape doesn't change. The CLI count moves with the new command.
- **Absent is `None`.** A missing number is never written as `0`.
- **Directive body.** `-->` or `--!>` in SQL is refused with its own message, using the
  `_TERMINATORS` rule in `dashboards/grammar.py`. SQL `--` comments and blank lines are fine.
- **Public repository.** Examples use invented numbers and no personal data.

## Open for Requirements and Design

- The template's path, and whether it can be a `.md` file at all without showing up as a wiki page
  in the athlete's PKM.
- The command's name and exact forms.
- Whether the awaiting code counts as a failure (exit 1). Recommended: yes, because nothing was sent.
- The per-statement limit and the per-pass budget.
