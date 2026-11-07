# Implementation Plan

## Before You Start

- **No documentation tests (Req 14.8).** Add no test that reads a doc, a changelog or a spec. If a task's change turns a documentation-binding test red, delete that test function in that task, and do not update it. Record each deleted test's file and name in the task's Implementation Notes, so that 6.3 can name it in the amendment.
- **Rule copies move together, and last.** The sentences "the index is never read back into a document", "fitdocs never touches this region again" and "Numbers always come from the page's own computed values" stay as they are until group 6. They are true until the feature lands, and 6.1 to 6.3 move every copy in one change.
- **Versions.**
  - `DOC_VERSION` stays 12, and `POST_PLACEHOLDER` keeps its wording.
  - `CONTRACT_VERSION` rides the unreleased `"19"` unless a release has been cut when 6.1 runs; check `git tag` then.
  - The CLI command count moves by one, for `post-template`.
  - If any other pinned count moves (`contract.__all__`, `connectors.__all__`, the plugin surface), stop and record why in `design.md`.
- **Clock scan.** The new package's boundary guard scans raw text for clock and randomness spellings, so a docstring or comment must not quote one. `monotonic` and the timer are always injected.
- **Mutation evidence.** Every new assertion needs a named mutation to production code, observed red and then green through `uv run pytest` (`change-protocol.md` § Fixture Discrimination). Fixtures must violate the property under test. An example is a `since` whose only fault is being a `datetime`.
- **No real data.** No task reads the maintainer's wiki or index. Tests build synthetic pages and a synthetic index with the existing fixtures.
- **Relay copy.** The task that appends the outcome code also runs `scripts/sync_relay_shared.py` and the relay's own tests.

## Tasks

- [x] 1. Foundation: shared additions outside the new package

- [x] 1.1 Recognize a waiting post region and name the template's location
  - Add three things to the contract:
    - the tuple of every fresh-placeholder wording fitdocs has written (today one);
    - the provenance comment's grammar;
    - a predicate that is true exactly when a region's content is only whitespace once every placeholder wording and every provenance comment is removed.
  - Add the template file's name and path helper to the data-root layout. Leave the owned paths unchanged, and name the file in their docstring among the user-owned files.
  - Keep the new contract names out of `contract.__all__`, so the public-surface pin in `tests/test_public_api.py` does not move.
  - Done when tests show:
    - every listed wording, an empty region, a whitespace-only region and a provenance comment with nothing below it are all waiting;
    - text with or without a comment is not waiting, nor is the athlete's own hidden comment or an unclosed comment;
    - the path helper gives `<data-root>/post-template.toml`.

    Each test dies on its named mutation: emptying the tuple, skipping the stamp removal, or treating any comment as fitdocs's own.
  - _Requirements: 1.1, 5.1, 5.10, 5.11, 13.5_

- [x] 1.2 (P) Splice one region's content generically
  - Add a region splice to the region-marker module that replaces only one region's inner content. It gives nothing when the region is absent, and raises the region error on damaged markers.
  - Make the published-region splice delegate to it, behavior unchanged.
  - Done when the existing published-region tests pass unchanged, and new tests show adjacent markers spliced, every byte outside the region unchanged, an absent region reported, and damage raised.
  - _Requirements: 5.6_
  - _Boundary: RegionSplice_

- [x] 1.3 (P) Expose the placeholder-name rule and a template's names
  - Export, from the publish template grammar, a check that a name follows the placeholder-name grammar, and a function returning every placeholder name a parsed template uses, inside optional clauses or not.
  - Done when tests show both on valid and invalid names, and on a template whose only use of a name is inside an optional clause.
  - _Requirements: 1.7, 1.12_
  - _Boundary: publish.template_

- [x] 1.4 (P) Tell whether a page has a landed post
  - Add a ledger function answering whether any record matching the page's source digests, in any ledger given, carries a landed digest. This is the rule publish's decision already uses.
  - Done when tests cover a landed record on a second ledger, a record with no digest (not landed), and a record for another page's digest (not matched).
  - _Requirements: 6.3, 12.1_
  - _Boundary: publish.ledger_

- [x] 1.5 (P) Ask the query session whether the index holds this exact file
  - Add to the query session a check that the index's recorded document fingerprint for a page key equals the fingerprint of the given path and bytes. Read bookkeeping once per session.
  - Done when tests over a built synthetic index show true for an indexed page, false after a one-byte change to it, false for an absent key and for no key, and a single bookkeeping read across many calls.
  - _Requirements: 6.5, 9.6, 10.10_
  - _Boundary: SessionFreshness_

- [x] 1.6 Create the post-template package, its shared types and its boundary guard
  - Create the package marker and the shared value types the design lists:
    - the fill codes and region states;
    - the binding, variable outcome and page result;
    - the unavailable reason and the template summary;
    - the report, including its waiting count, its counts of the athlete's and published pages left out, and its derived counts.

    The pass sets the waiting count on every path. Check sets it to the Eligible count, and refill to 0.
  - Add the package's boundary test. It holds:
    - an equality-pinned import table, written so that each later task appends one entry;
    - the forbidden names: `duckdb`, `fitdocs.index`, `dashboards`, `render`, `load`, `metrics`, `ingest`, `sync` and the network-capable standard library;
    - the clock and randomness spellings;
    - a reverse-importer scan: outside the package, only `fitdocs.cli` imports it, in the shape of `_unlisted_query_importers`;
    - a positive control that each scan saw at least one module.
  - Done when the guard passes on the skeleton, and goes red when:
    - a scratch copy of a package module adds `import duckdb` or a clock call;
    - a scratch module outside the package imports it;
    - a scan is pointed at an empty directory.
  - _Requirements: 13.1, 13.4_

- [x] 2. Core: the template, the region and the resolver

- [x] 2.1 (P) Parse and validate the post template
  - Read `post-template.toml` into a validated template, collecting every problem across keys rather than stopping at the first. Each problem names the file and key, and for grammar the line and column.
  - Apply the design's rules in order: UTF-8 and TOML, the allowed and required keys, `since` as a TOML date only, title and description text with the comment-marker and single-line rules, `vars` entries with exactly a text `sql`, and variable names that follow the grammar, are not a page placeholder, and are used.
  - Compute the template digest from title, description and each variable's name and SQL only.
  - Loading gives nothing when no file exists, and refuses a directory, a symlink or an unreadable file.
  - Extend the package import table with this module's entry.
  - Done when tests cover one fixture per rule (including a `datetime` `since`, `<!--` in the description, an unused variable, a variable named `load_value` and a `{typo}` located by line and column), two problems reported together, the digest unchanged by moving `since` or adding a comment and changed by editing SQL, and an absent file giving nothing.
  - _Requirements: 1.2, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 5.5_
  - _Boundary: PostTemplateFile_
  - _Depends: 1.1, 1.3, 1.6_

- [x] 2.2 (P) Classify a post region and write filled text
  - Decide a region's state from its bytes, as waiting, filled or the athlete's, in that order. Waiting is the contract's predicate from 1.1. Filled means a stamp line matching the contract's grammar, with text below it whose digest matches the stamp.
  - Produce a filled region from a composed post, a template digest and an as-of. Double every brace in the title and description, and put the stamp line above the text.
  - Extend the package import table with this module's entry.
  - Done when tests show:
    - a round trip through publish's region reader, override parser and composer equal to the original post, with braces in a value and a title, `{title}` as literal text in a value, and an empty description;
    - each edit that keeps text giving the athlete's state: a changed character, CRLF, a removed stamp;
    - deleting the text, with or without the stamp, giving waiting;
    - the stamp line never matching a region marker.
  - _Requirements: 4.6, 4.7, 5.1, 5.2, 5.3, 5.4, 5.10, 8.4_
  - _Boundary: FillRegion_
  - _Depends: 1.1, 1.6_

- [x] 2.3 Check a template's SQL against the index
  - Open a resolver over a sandboxed query session, or give the reason the index is unavailable and the next step for not built, needs rebuild, busy and unverified.
  - For each variable:
    - require a single `SELECT` (refusing EXPLAIN);
    - require `$as_of` and allow only `$as_of` and `$page_key`;
    - run the lint over the serialized statement: the design's function names, keyword column references, `query` and `query_table`, and sampling;
    - name the variable in every problem.
  - Add the resolver module to `_QUERY_IMPORTERS` and to the package import table. It is the only package module that imports `query`.
  - Create the package's test fixtures, reusing `tests.query._helpers`: a synthetic data root with a built index holding a week with threshold load, two workouts on the same day and a week with zero load. 2.4 and the engine's integration cases use them.
  - Done when tests over that index refuse:
    - an EXPLAIN, a missing `$as_of` and a `$foo`;
    - `current_date` and `CURRENT_TIMESTAMP`, `now()`, `random()` and `query('SELECT random()')`;
    - `USING SAMPLE`.

    They also pass the design's example, and an unbuilt index gives the not-built reason. Each refusal dies when its rule is removed.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 13.3_
  - _Boundary: VariableResolver_
  - _Depends: 1.5, 2.1_

- [x] 2.4 Resolve one variable for one page
  - Bind exactly the parameters the statement uses: `$as_of` as the naive local start and `$page_key` as the page key. Run with a two-row cap and the given timeout.
  - Turn the result into text by the design's type table: integers, decimals without exponent, dates and text pass; booleans, floats, timestamps, other types and unsafe text are refused with advice; zero rows or NULL are absent.
  - Map timeouts, failures and refusals to their codes, with the database's message on one line.
  - Delegate the index-currency check to the session.
  - Done when tests over a synthetic index show:
    - the example share;
    - a zero-load week absent through `NULLIF`;
    - two rows refused;
    - a later workout on the same day excluded by `$as_of`;
    - one refusal for each refused type and for text holding a line break or `-->`;
    - a timeout reported as timed out.

    A `bool` is never rendered as an integer and a `datetime` never as a date.
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - _Boundary: VariableResolver_
  - _Depends: 2.3_

- [x] 3. The fill engine and its reports

- [x] 3.1 Fill one page
  - Read each page once. Decide its state, whether it is in the window and whether it has a landed post.
  - Build the binding from the page's recorded start and base digest. With no aware start, report no start time.
  - Require the index to hold this exact file. Resolve the variables in name order, stopping the page at the first failure.
  - Compose from the page's values and the variables' values with publish's composer, mapping a missing value and an empty title to their codes. Refuse composed text holding a comment marker.
  - Render the filled region, and decide whether the text changes.
  - When writing, re-read the file and write only if its bytes are unchanged, splicing only the `post` region and writing atomically. Only current pages with intact markers are written.
  - Declare the resolver protocol and extend the package import table.
  - Done when engine tests with a fake resolver show:
    - each outcome code;
    - a failure leaving the page's bytes unchanged;
    - an edit between read and write giving page changed with the edit kept;
    - an older page never written;
    - an identical recomposition reported unchanged with no write;
    - every byte outside the region unchanged after a fill;
    - a page the index does not hold as it is now giving `index_behind`, with no variable resolved and no write.
  - _Requirements: 3.3, 3.10, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.6, 5.7, 5.8, 5.9, 6.5, 10.4, 10.9, 10.11_
  - _Depends: 1.2, 1.4, 2.1, 2.2_

- [x] 3.2 Run the automatic pass
  - Collect the candidates, the waiting pages in the window, in file-name order. Return an empty report when there are none.
  - Load every ledger on disk. An unreadable ledger is reported as unavailable, counting the candidates as waiting, and nothing is written.
  - Drop the candidates with a landed post. What remains is the Eligible pages; return an empty report when none remain.
  - A closed index gate is reported with the count waiting. An unavailable resolver is reported.
  - A refused template SQL is reported once and nothing is written.
  - Fill each page with a 5-second statement limit. Stop starting new pages after 30 seconds by the injected monotonic clock, and stop at the first timeout, marking the rest not attempted with the variable named.
  - Close the resolver before returning, whatever happened. Filled pages are never queried.
  - Done when engine tests with a fake resolver and a fake clock show:
    - the empty report with no ledger read and no resolver opened when there is no candidate;
    - the empty report when every candidate has a landed post;
    - unreadable ledgers reported with the candidate count;
    - each unavailable path writing nothing;
    - the budget stop after the right page;
    - the timeout stop;
    - a landed waiting page left out;
    - a filled page never resolved;
    - the resolver closed on every path, including a raised error.
  - _Requirements: 2.5, 6.2, 6.3, 6.4, 6.6, 6.7, 6.8, 7.1, 7.2, 7.3, 8.5_

- [x] 3.3 Run check and refill
  - **Check without pages:** validate the template, or carry its problems, then check the SQL. Count the Eligible pages, which the next sync will try to fill, and the filled pages whose stamp names another template digest. Write nothing.
  - **Check with pages:** for each named page in any state, in or out of the window, show its state, the window, the landed flag from the ledgers it is given, each variable's value or why it has none, and the composed post or why there is none. Flag a page the index does not hold as it is now.
  - **An unavailable index:** check still reports the template's own problems and says the SQL was not checked and why.
  - **Refill without pages:** take every Eligible page and every filled page with no landed post, in the window. Count the athlete's pages and the published pages left out, the latter with a note that naming a page refills it.
  - **Refill with pages:** take each named waiting or filled page, in or out of the window and landed or not, and report a named athlete's page as left alone.
  - Refill gives the changed flag and new text in a dry run, names pages whose text would change and have a landed post, and allows 30 seconds per statement, stopping at the first timeout.
  - Done when engine tests with a fake resolver cover:
    - each selection row of the design's table;
    - a bare refill leaving a filled published page untouched and counted, while the same page named is refilled;
    - the Eligible count and the older-template count from check;
    - the landed naming, with and without writing;
    - a dry run writing nothing;
    - a failed refill keeping the page's text;
    - refill stopping at the first timeout with earlier pages kept;
    - check with an unavailable index reporting the file's problems and the unchecked SQL;
    - check given unreadable ledgers reporting that as a problem, still checking the template and SQL, and showing pages without a landed flag;
    - a refill row for a page the index does not hold as it is now, giving `index_behind` with `fitdocs index` as the next step, and the page unchanged.
  - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 10.2, 10.3, 10.5, 10.6, 10.7, 10.8, 10.10, 10.12_

- [x] 3.4 (P) Render the pass, check and refill reports
  - Render the pass as text:
    - empty when there is nothing to say;
    - otherwise the filled and waiting counts and any stop note;
    - at most five cause lines, each with a count, one example page and the fixed next step for its code;
    - one line naming `fitdocs post-template check` for a template problem;
    - one line with the reason and next step when the index or the ledgers are unavailable.
  - Render check and refill as text and as JSON carrying the same fields.
  - Extend the package import table with this module's entry.
  - Done when tests show the empty case, the five-cause cap with a sixth cause dropped, the timeout and budget notes naming the variable, and the JSON holding every field the text shows for the same report.
  - _Requirements: 7.4, 7.5, 7.6, 11.2_
  - _Boundary: FillReportRendering_
  - _Depends: 1.6_

- [x] 4. The waiting refusal in publish

- [x] 4.1 (P) Append the waiting outcome code
  - Append `post_waiting` after the last existing code, counted as a failure and not returned by a target. Its explanation says the page is waiting for its post from the post template and names `fitdocs post-template check` and writing the post by hand.
  - Regenerate the relay's shared copy with the sync script, and run the relay's own tests.
  - Delete `tests/publish/test_docs.py::test_the_code_table_equals_the_vocabulary_in_order`, a documentation-binding test this turns red, and record it for 6.3. 6.2 adds the row to the guide's table.
  - Done when:
    - the outcome tests pass with the existing prefix pins unchanged, and a new test pins the code's position, flags and text;
    - the shared-copy cross-check passes;
    - the relay suite is green.
  - _Requirements: 12.2, 12.3_
  - _Boundary: PublishWaitingRefusal_

- [x] 4.2 Refuse an Eligible page when publishing
  - Give the publish plan an optional template `since`, defaulting to none, so existing plans are unchanged.
  - When it is set, refuse with `post_waiting` each selected target of an opted-in page that is in the window, waiting and has no landed post in any ledger. Do this after the page-state, facts and ledger-conflict refusals and before composing. Treat every other page as today.
  - Done when engine tests show:
    - the refusal in a dry run and with posting, nothing sent;
    - the refusal for a page whose region the athlete emptied;
    - no refusal with no template, out of the window, after the athlete writes text into the region, or with a landed record on another target (where the per-target template is sent);
    - `page_out_of_date` keeping precedence;
    - a filled page deciding `would_post`, then `unchanged` once landed, then `would_update` after a refill changes it.

    Publish reads no index and imports nothing from the new package.
  - Build the filled region in these tests with the region module's own renderer, not by hand, so that the round trip is the real one.
  - _Requirements: 5.10, 12.1, 12.4, 12.5, 12.6, 12.7, 12.9, 12.10_
  - _Depends: 1.1, 1.4, 2.2, 4.1_

- [x] 5. Integration in the CLI

- [x] 5.1 Fill pages in the sync that creates them
  - Add the index gate: open only for refreshed, unchanged or built with no page or data-source error. Its reasons are worded like the dashboard pass's.
  - Add the post-fill pass, called between the index pass and the dashboard pass on both sync paths:
    - With no template file it imports nothing from the new package and prints nothing.
    - A refused template is one line.
    - The second index refresh runs only when a page was written, and the dashboard pass receives the last index report.
    - Any error is one line and never changes the exit code.
  - Leave `regen` and `load` untouched.
  - Done when end-to-end tests over synthetic `.fit` fixtures show:
    - `fitdocs sync` filling a new page with the index built, then `fitdocs query` reporting no drift, and a second sync writing and printing nothing;
    - with a dashboard page present, the dashboard pass receiving the second index report, not the first;
    - an unbuilt index and an index with a page error each giving one line, the page left waiting, and exit 0;
    - `fitdocs pull --sync` filling through the drain path;
    - `fitdocs regen` with the index directory deleted keeping a filled region byte for byte;
    - a later workout and a load recompute leaving it unchanged;
    - output and bytes identical to today with no template file.
  - _Requirements: 1.3, 6.1, 6.4, 6.7, 6.9, 6.10, 6.11, 6.12, 6.13, 7.6, 8.1, 8.2, 8.3_
  - _Depends: 2.4, 3.2, 3.4_

- [x] 5.2 Add the `fitdocs post-template` command
  - Add `fitdocs post-template check|refill [PAGES...] [--yes] [--format text|json] [--out PATH]`.
  - PAGES resolve as `fitdocs publish` resolves them. `--yes` with `check` is a configuration error.
  - Both forms load the publish ledgers before running: `check` needs them for the Eligible count and the landed flag, and `refill` to leave out published pages.
  - `check` reports a refused template or unreadable ledgers as problems with exit 1, still running the template and SQL checks, and reports a missing file with exit 2 naming the path.
  - `refill` refuses before any write, with exit 2, a missing or refused template, unknown pages, unreadable ledgers and refused SQL.
  - Move the CLI count pins from 17 to 18: `tests/test_cli_skill.py`, `tests/query/test_cli_query.py`, `tests/index/test_cli_index.py`, and the `cli.py` module docstring with its command list.
  - An unavailable index or a failed page gives exit 1. `refill --yes` refreshes the index once after writing. An interrupt exits 130.
  - Done when end-to-end tests cover:
    - each exit code;
    - `refill` without `--yes` writing nothing, and with it writing, naming a landed page and leaving `fitdocs query` without drift;
    - a bare `refill --yes` leaving a published page's text unchanged and reporting it, and the same page refilled when named;
    - an emptied region refilled by the next `fitdocs sync`;
    - `check` without pages reporting how many pages the next sync would fill;
    - an athlete's page untouched;
    - `check` with pages showing values and the composed post;
    - JSON and text carrying the same results.
  - _Requirements: 5.10, 9.1, 9.2, 9.5, 9.7, 9.8, 10.1, 10.2, 10.6, 10.13, 10.14, 10.15, 11.1, 11.2, 11.3_
  - _Depends: 2.4, 3.3, 3.4_

- [x] 5.3 Read the template's `since` before publishing
  - In `fitdocs publish`'s settings preflight, load the template. A refused one gives a configuration error naming the file, exit 2, before any request or write, `--targets` included. Pass its `since`, or nothing, into the plan.
  - Done when end-to-end tests show:
    - `fitdocs sync` with the index not built, then `fitdocs publish` refusing the new page with `post_waiting` and exit 1;
    - after `fitdocs index` and `fitdocs sync`, `would_post` with the filled text;
    - a broken template stopping publish with exit 2;
    - publish unchanged with no template file;
    - a filled page whose template file is then deleted keeping its text, with publish deciding `would_post` with that text and giving no `post_waiting`.
  - _Requirements: 1.3, 8.6, 12.1, 12.2, 12.8, 12.10_
  - _Depends: 4.2, 5.1_

- [x] 5.4 Hold the new writers to the confinement and network guards
  - Register `sync-with-post-template` and `post-template-refill` as writing entry points, each with a non-vacuous check that a region was filled. Add both ids to `_EXTERNAL_INDEX_ENTRY_IDS`, because both refresh the external index.
  - Show that `post-template check` writes nothing.
  - Show that the pass and the command make no request under the suite-wide network guard (`tests.support.network`, installed by `tests/conftest.py`), which fails any test that reaches a non-loopback host.
  - Done when:
    - the confinement test passes for both entry points;
    - it goes red when the non-vacuous check is removed or a fixture leaves the region waiting;
    - a `check` run leaves every data-root byte unchanged.
  - _Requirements: 11.3, 13.1, 13.2_
  - _Depends: 5.1, 5.2_

- [ ] 6. Contract, documentation and records

- [ ] 6.1 State the changed guarantees in the contract
  - In the code contract and `docs/ownership-contract.md`:
    - the `post` region may be written only while waiting or filled, and never while it is the athlete's;
    - `post-template.toml` is user-owned and read-only;
    - a filled `post` region is the second named exception to the index never being read back, carried afterwards as a snapshot.
  - Update the contract-19 history and the "What changed at this version" text. If a release has been cut, raise the version by one instead.
  - Delete each documentation-binding test this turns red, recording its name.
  - Done when the ownership-contract conformance tests pass, a full-text search of the two files finds no sentence still saying fitdocs never touches the `post` region, and the deleted tests are listed in Implementation Notes.
  - _Requirements: 14.1, 14.2, 14.3, 14.8, 14.9_

- [ ] 6.2 Document the feature and carry the recipe
  - This task owns every edit to `docs/publishing.md`, `CHANGELOG.md` and the packaged skills. It follows 6.1 because the changelog names the contract version 6.1 settles.
  - Add the `post_waiting` row to the guide's outcome table.
  - Rewrite the workouts skill's paragraph saying an empty region uses the configured template, so that it also covers the post template: an emptied region is filled again from it.
  - Add a post-templates section to `docs/publishing.md` covering:
    - the format, `since`, the two parameters and the value rules;
    - setting `since` to the day the file is created, and why: an example date in the past fills every page since then;
    - building the index once with `fitdocs index` before the first fill;
    - the three states, including emptying a region to return it to the template, and what keeps a post stable;
    - that a bare `refill` leaves published pages alone and naming them refills them;
    - the new code and the ways out of a waiting refusal;
    - both commands;
    - the lint's stated limits (`first`, `any_value`, `LIMIT` without `ORDER BY`, tables that depend on today, and `$as_of` referenced without constraining).
  - Add a changelog entry under Unreleased naming the contract change.
  - Add the worked recipe to the workouts skill: it sums `pages.load_value` for one methodology, never the week's running total, uses invented numbers, and tells the reader to set `since` to the day they create the file. Run the recipe's SQL once against a synthetic index to confirm it works, without adding a test.
  - Done when the docs build and the skill packaging tests pass, and the recipe's SQL has been run once and its result recorded in Implementation Notes.
  - _Requirements: 14.5, 14.6, 14.7_

- [ ] 6.3 Move the steering copies and record the amendments
  - Update `tech.md` (the read-back sentence and the commands that make no connector request), `structure.md` (the new package's import rule, `query`'s third importer, and `post_template`'s imports of `publish`) and `product.md` (the publishing capability).
  - Add amendments to `publish-core`, `wiki-contract`, `analytics-index` (Req 5.6's second exception) and `analytics-query`, each naming the documentation-binding tests deleted in this spec.
  - Mark Phase 16 in the roadmap, and add a queue item for the website copy.
  - It edits no file 6.1 or 6.2 owns. A contradiction it finds in one of them goes back to that task.
  - Done when a search across steering, `CLAUDE.md`, `docs/` and the packaged skills finds no remaining statement the feature contradicted, and each amendment names its deleted tests.
  - _Requirements: 14.4, 14.8, 14.10_

- [ ] 7. Validation

- [ ] 7.1 Validate the whole feature
  - Run the full validation (`uv run pytest -n auto`, `ruff check`, `ruff format --check`, `mypy`), the relay suite, and the branch's CI.
  - Confirm:
    - `DOC_VERSION` and the placeholder wording are unchanged;
    - `CONTRACT_VERSION` follows Req 14.9;
    - the CLI count moved by exactly one;
    - no runtime dependency was added;
    - the package guard, the query importer guard and the publish import table all pass.
  - Done when validation is green with evidence recorded and the branch is ready to merge.
  - _Requirements: 13.4, 13.5, 14.9_

## Implementation Notes

- 1.1: `contract.POST_FILL_STAMP` is an unanchored, ASCII-only (`[0-9]`, not `\d`) compiled regex with groups `template`, `as_of`, `text`. Use `fullmatch` on one line. `is_waiting_post` removes the wordings and stamps in ONE `sub` over a single alternation (`contract._OWN_COMMENTS`), so a wording spliced into a stamp cannot manufacture one. 2.2 should reuse these, not re-spell the grammar.
- 1.1 → 2.2: the grammar accepts an `as_of` that `datetime.fromisoformat` rejects (e.g. month 13). `classify` must not crash on it: treat an unparseable stamp as not fitdocs's own (the athlete's), and test it.
- 1.1 review took 3 rounds, all on the stamp grammar's tests (uppercase hex, digest length on BOTH digests, trailing text on the stamp line, field spacing, fraction width, 1-digit month/day, `re.escape`, `count=1`). The production code was correct from round 1. Sweep every grammar element before reporting.
- 1.2: `docmerge.replace_region(markdown, id, content) -> str | None` writes content verbatim and returns None only when the region is absent; damage raises `RegionError`. It does NOT check that `content` is free of marker lines, so 3.1's comment-marker refusal on composed text is what keeps a fill from writing a page `extract_regions` rejects. Review lesson: decoys with a different id cannot discriminate a literal-id pattern, so use same-id lookalikes that are not markers, and content with surrounding whitespace.
- 1.5: `QuerySession.page_is_current(page_key, path, data)` reads bookkeeping lazily once per session through `command.read_bookkeeping`, and lets read errors propagate. That read is the one `command.py` connection read without the `interrupt_quietly` / `is_user_interrupt` → `KeyboardInterrupt` conversion that `run` and `open_session` have. So a SIGINT landing there would surface as `RuntimeError("Query interrupted")`. 2.4's `SessionResolver.page_is_current`, or the engine, must convert it so that refill exits 130 (Req 10.14) and the pass stops cleanly (Req 6.12). Pin it with a test.
- 1.6, rulings recorded:
  - `FillReport.waiting` is `int | None`, set by the parent and reflected in design.md. None occurs only when `check` cannot read the ledgers; the renderers must then hide the Eligible count, not print 0.
  - `wrote` is the pages of rows whose code is `FILLED`. `PageResult.landed` means a landed publish post, never "written this run".
  - `counts` lists only codes that have at least one row, in FillCode order.
  - `failed` is true for template problems, `unavailable`, or any row code outside {FILLED, WOULD_FILL, UNCHANGED, ATHLETES_TEXT}. So INDEX_BEHIND and PAGE_NOT_CURRENT fail in both check and refill, and pages a bare refill leaves out are counts, not failures.
  - The boundary guard in tests/post_template/test_boundary.py has an equality-pinned `_ALLOWED_IMPORT_TARGETS`, and each later module task appends ONE entry. The resolver task (2.3) adds `fitdocs.query` for resolve.py only. query is not in `_FORBIDDEN_TARGETS`, but the per-module table forbids it everywhere else.
- 2.1: `post_template.template` has `parse_post_template(data, *, path)` and `load_post_template(data_root) -> PostTemplate | None`. `PostTemplateError(SettingsError)` has `.problems`; each problem is `<path>: <key>: <reason>`, already prefixed with the path, and grammar positions read "line L, column C of the value". Problems come in rule order: required keys, unknown keys, since, title, description, vars shape, vars names. The unused-variable check is skipped only when title or description fails to PARSE. The digest follows the design recipe (compact JSON, sorted vars, SQL rstrip of CR/LF).
- 2.2 → 3.1: `region.classify` hashes everything after the stamp's first `\n` exactly as written (UTF-8; a trailing newline counts; `render_filled` writes none). The engine must read page BYTES as publish does (`docio.read_document` → `read_bytes`), not `read_text`, which turns CRLF into LF and would hide an athlete's CRLF edit. Sync's own `read_text`/`write_text` (sync.py ~2074/2614) already normalizes CRLF on regen; that is existing behavior and out of scope. 2.2 dropped the design's "rest not blank" / "\n exists" guards as dead: Waiting is checked first and `is_waiting_post` covers both. The reviewer confirmed this with a 20k-input differential.
- 2.3: `post_template.resolve` has `open_resolver(data_root, env) -> SessionResolver | Unavailable`, plus `SessionResolver.check`/`close` and `_interruptible`, the Ctrl-C conversion that 2.4 must reuse for `resolve` and `page_is_current`. `check` only parses and keeps no parameters, so `resolve` re-screens to learn which names to bind (ruling in design.md). Shared fixture: `tests/post_template/_index.py` and `conftest.py` (`indexed_post_root` module-scoped, `post_root_copy` per test) give pages MON, AM, PM and REST with sha256 keys; `EXAMPLE_SQL`/`EXAMPLE_SHARE` are `{MON:100, AM:56, PM:24, REST:None}`. The lint list grew by 11 names beyond the design; design.md records them.
- 2.4: `SessionResolver.resolve(variable, binding, *, timeout_s) -> VariableOutcome` re-screens, binds only the screened names, and runs with `max_rows=2`. Shape is checked before absence. `to_text` refuses bool, float, datetime, time and other types with "cast it to text" advice, and refuses line breaks and comment markers; tab and other control characters pass, per the design (queued as a question). "" and 0 are values; only zero rows or NULL are absent. A TIMESTAMPTZ result is recognized by `query.statement.TIMESTAMPTZ_HINT` and refused with the timestamp advice. `page_is_current`, `screen` and `run` all go through `_interruptible`.
- 3.1 rulings:
  - `engine` imports the private `publish.pages._status`, so a page is read once and its status and bytes come from the same read. A public alias is queued.
  - `refs[-1]` (case kept) is the base digest, the same as `index/corpus.py` `page_key`.
  - TIMED_OUT is RETURNED as a row code, not raised. 3.2 stops when `result.code is FillCode.TIMED_OUT` and names `result.variables[-1].name`.
  - `publish.outcomes` was added to design.md Allowed Dependencies.
- 3.1 → 3.3: `_fill_page` returns ATHLETES_TEXT before composing, whatever `writing` is. Req 9.4 requires `check` with named pages to show the variables and the composed post for a page in ANY state, Athlete's included, while refill reports a named Athlete's page as left alone (10.5). So 3.3's check path must compose an Athlete's page without writing, for example with a compose-only helper or a flag. It must not change refill's behavior.
- 3.2 rulings:
  - The 30 s pass budget starts after the candidate scan, the ledger load and the gate, and before `open_resolver`. So the open wait on a busy index and the SQL `check` count against it, but the page scan does not.
  - The fill-path `waiting` counts every row that is not FILLED, NOT_ATTEMPTED included.
  - The unreadable-ledger next step is "fix the file it names, then run fitdocs sync again". Never advise removing a publish record: that re-sends posts and makes landed pages Eligible.
  - The empty-Eligible return comes before the gate is looked at, per Flow 7.6.
- 3.3: `run_check`/`run_refill` share `_fill_entries` (30 s statements, stop at the first timeout; INDEX_BEHIND detail gains "; run fitdocs index"). `_fill_page(show_athletes=True)` lets check compose an Athlete's page; refill and the pass never set it. Rulings (design.md): with a refused template check gives `waiting` and `older_template` = None and no rows; with the template parsed but the index unavailable or SQL refused, named pages still get NOT_ATTEMPTED rows with state, window and landed; refill always opens the resolver and runs check (10.15); `landed_changed` = FILLED or WOULD_FILL with a landed post. 3.4 renderers must hide `waiting`, `older_template` and `landed` when None.
- 3.4: `post_template.report` has `render_pass_text` and `render_text`/`render_json` for check and refill. It prints engine reasons as written, hides None counts and None landed flags, and groups VALUE_MISSING cause lines by `row.detail` (the placeholder). Cause lines are capped at 5, sorted by count, then FillCode order, then variable. The NEXT_STEPS wording was written at implementation; only value_missing came from the design. Refill's `older_template` is None (the engine `_report` default). The naming note goes only on the published left-out line. report imports engine for the timeout constants only (design.md).
- 4.1: `PublishCode.POST_WAITING` was appended last with flags "F" (failure, so exit 1), and the relay copy was synced. DELETED doc-binding test, for 6.3 to name: `tests/publish/test_docs.py::test_the_code_table_equals_the_vocabulary_in_order`, along with its orphaned `_yes_no` helper and `OUTCOMES` import. The guide's table still lacks the row; 6.2 adds it.
- 4.2: `PublishPlan.post_template_since: date | None = None`. `_decide_pair` refuses with POST_WAITING when the page is in the window (`document_date >= since`), Waiting, and not landed in ANY ledger on disk (`run.ledgers`). The check runs after the page-state, facts and conflict checks and before composing. The test helper `replace_ledgers` (tests/publish/test_engine.py) now uses `dataclasses.replace`, so plan fields are no longer dropped silently. 5.3 must pass `post_template_since` into the plan.
- 5.1: `cli._index_gate(report)` and `cli._run_post_fill_pass(data_root, report)` sit between the index and dashboard passes at both sync sites: the explicit-source sync body and `_run_drain_passes`, which serves no-source sync and `pull --sync`. The pass checks `lexists` before any import. A refused template prints one line naming `fitdocs post-template check`. Pass lines go to stdout. The second refresh (`handoff=None`) runs only when pages were written, after the pass text is printed. The needs_rebuild next step is "run fitdocs index". Test World fixture: tests/post_template/test_sync_pass.py.
- 5.2: `fitdocs post-template check|refill [PAGES] [--yes] [--format] [--out]`, where `--out` is the shared data-root override, not an output file. Checks run in this order: --yes with check, then the template, then PAGES, then the ledgers. Refill with refused SQL prints the report and exits 2. In JSON mode the post-write refresh prints to stderr. The CLI count is now 18. The shared fixture `_index.py` `page_text` now writes a `published` region (pages were DAMAGED before; no earlier test relied on status), pinned by `test_index_fixture.py`. Not yet in confinement WRITING_ENTRY_POINTS (5.4).
- 5.3: publish's settings preflight loads the template only when `post-template.toml` lexists (lazy import; the ruling is recorded in design.md). A refused template gives exit 2 with every problem line, before `--targets` too, and `post_template_since` reaches the single `PublishPlan` construction for both the dry run and `--yes`. The page half of Req 8.6 (keeping its text after the template is deleted) is PRESERVED-ONLY here: the post-unlink `pw.sync()` assertion cannot fail, and the real cover is `test_sync_pass.py::test_regen_with_the_index_deleted_keeps_the_filled_region`.
- 5.4: tests/test_confinement.py registers `sync-with-post-template` and `post-template-refill` in WRITING_ENTRY_POINTS, with `_wrote_a_filled_post_region_and_the_index`: a stamped post region, the index written, and the staged publish ledger untouched. It reads the sandbox via the module global `_POST_SANDBOX`, set only by `_stage_post_template`. Both ids are in `_EXTERNAL_INDEX_ENTRY_IDS`. `check` (bare and named) writes no byte and makes no request.
