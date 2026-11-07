# Requirements Document

## Project Description (Input)
Post templates whose variables are SQL over the analytics index. The athlete writes one template file: the post's text in the existing `{name}` grammar plus one SQL definition per variable, bound to `$as_of` (the workout's recorded start) and `$page_key`. After `fitdocs sync`, each new page's user-owned `post` region holds the finished text, written once by a fill pass that runs after the index refresh. `fitdocs publish` sends that text through its existing path and stays offline. `fitdocs regen` carries the text byte for byte; re-querying happens only on request. Text the athlete wrote or edited is never overwritten. Discovery context, decisions and viability evidence: `brief.md`.

## Introduction

An athlete who publishes their workouts wants each post to say things the page itself does not hold, such as this workout's share of the week's load so far. Today they either run the SQL and type the number into the page, or use a template limited to 17 values read from the page.

With this feature the athlete writes one file, once. Every new page then arrives with its post already written, numbers included, in the same `fitdocs sync` that creates the page. No further command is needed. The text stays as written unless the athlete asks for it to be recomputed, and the athlete's own words are never overwritten.

### Terms

- **Post template:** the file `post-template.toml` at the top of the data root.
- **Variable:** a name the post template declares with one SQL statement.
- **Page placeholder:** one of the 17 values `fitdocs publish` already reads from a page.
- **Window:** the pages dated on or after the post template's `since`. A page's date is its recorded local date.
- **Waiting:** a page whose `post` region is byte-for-byte the fresh placeholder, in any wording fitdocs has ever written.
- **Filled:** a page whose `post` region holds a provenance comment whose text digest matches the region's text.
- **Athlete's:** a page whose `post` region is neither Waiting nor Filled.
- **Fill:** to write composed text into a Waiting or Filled page's `post` region.
- **Fill Pass:** the automatic step in `fitdocs sync` and `fitdocs pull --sync` that fills pages.
- **Landed post:** a publish record confirming that a page's post is on a publish target.
- **Eligible:** a Waiting page in the window with no landed post.

### Decisions taken at requirements (2026-11-07, maintainer)

- **The template is TOML, not markdown.** The athlete's PKM catalogs every `.md` file under the wiki as a page, and a markdown template would also need its own strict YAML parser. This supersedes the example format in `brief.md`.
- **The command is `fitdocs post-template`, and filling needs no command.** A page fills automatically in the `fitdocs sync` that creates it. The command exists to check the template and to re-run the queries. The brief's separate `fill` form is folded into `refill`.
- **A page refused for waiting counts as a failure** (exit 1), because nothing was sent.

## Boundary Context

- **In scope:** the post template file and its validation; resolving variables with `$as_of` and `$page_key`; the Fill Pass and where it runs; the provenance comment and the three region states; the `fitdocs post-template` command with its `check` and `refill` forms; the waiting refusal in `fitdocs publish`; the contract amendments, documentation and a worked recipe in the packaged skill.
- **Out of scope:**
  - one template per sport or per target;
  - query parameters on the `fitdocs query` command line;
  - re-querying during `fitdocs regen`, or running SQL during `fitdocs publish`;
  - an as-of dimension in the index, or any new index table or column;
  - filling history, block or dashboard pages;
  - expressions, loops or formatting options in the template (SQL does the formatting);
  - a post written by a model;
  - checking the post template from `fitdocs check`;
  - whether a query's numbers are right, which the author owns;
  - variables inside a `post` region the athlete writes by hand, where only the 17 page placeholders stay available.
- **Adjacent expectations:**
  - `fitdocs sync`, its drain and `fitdocs pull --sync` already refresh the index after writing pages, and this feature runs after that refresh.
  - `fitdocs publish` keeps composing offline from the page and the settings; its targets see only the composed text and do not change.
  - `fitdocs regen` already carries the `post` region verbatim, and that does not change.
  - The packaged page format does not change: `doc_version` stays where it is and no existing page is rewritten on upgrade.

## Requirements

### Requirement 1: The post template file

**Objective:** As an athlete, I want to define my post once in one file, so that every new workout page gets it without per-page work.

#### Acceptance Criteria

1. The fitdocs CLI shall read the post template from exactly one location, `post-template.toml` at the top of the data root.
2. The fitdocs CLI shall never create, modify, rename or delete the post template file.
3. While no post template file exists, every fitdocs command shall behave as it does without this feature: no page filled, no index session opened for it, no additional index refresh, no additional output and no publish refusal.
4. The fitdocs CLI shall require the top-level keys `since` and `title` and shall accept the top-level keys `description` and `vars`, treating an absent `description` as empty text.
5. If the post template lacks a required key or holds any other top-level key, then the fitdocs CLI shall refuse the template and name the key.
6. If `since` is not a TOML date without a time, then the fitdocs CLI shall refuse the template with a message showing the accepted form, `since = 2026-11-07`.
7. The fitdocs CLI shall read `title` and `description` in the existing post grammar (`{name}`, `{?...}`, `{{` and `}}`), where a name is a page placeholder or a declared variable.
8. If `title` or `description` has a grammar error or names an unknown placeholder, then the fitdocs CLI shall refuse the template and name the key, the line, the column and the reason.
9. If `title` holds a control character or a line or paragraph separator, then the fitdocs CLI shall refuse the template.
10. If the literal text of `title` or `description` holds `<!--`, `-->` or `--!>`, then the fitdocs CLI shall refuse the template, because such text can damage the page's region markers.
11. The fitdocs CLI shall read each entry of `vars` as a table holding exactly one key, `sql`, whose value is text.
12. If a variable's name does not follow the placeholder-name grammar, equals a page placeholder, or is not used by `title` or `description`, then the fitdocs CLI shall refuse the template and name the variable.
13. If a variable's entry lacks `sql`, holds another key, or has a `sql` value that is not text, then the fitdocs CLI shall refuse the template and name the variable.
14. If the post template cannot be read, is not valid UTF-8 or is not valid TOML, then the fitdocs CLI shall refuse it and name the file and the reason.
15. The fitdocs CLI shall run the checks in this requirement without opening the analytics index.

### Requirement 2: Checking a variable's SQL

**Objective:** As an athlete, I want a bad query refused before it can write anything, so that a mistake in the template never reaches a page.

#### Acceptance Criteria

1. If a variable's SQL is not exactly one read-only query that the `fitdocs query` sandbox accepts, then the fitdocs CLI shall refuse it and name the variable.
2. If a variable's SQL does not reference `$as_of`, then the fitdocs CLI shall refuse it and name the variable.
3. If a variable's SQL references a parameter other than `$as_of` and `$page_key`, then the fitdocs CLI shall refuse it and name the variable and the parameter.
4. If a variable's SQL uses a clock or randomness function that fitdocs recognizes, then the fitdocs CLI shall refuse it and name the variable and what was found.
5. If any variable's SQL is refused, then the fitdocs CLI shall fill no page from that template and shall report the refusal once rather than once per page.

### Requirement 3: Resolving a variable for a page

**Objective:** As an athlete, I want each variable computed as of the workout it describes, so that the number means what it says when I read it later.

#### Acceptance Criteria

1. When a variable is resolved for a page, the fitdocs CLI shall bind `$as_of` to the page's recorded start as local wall-clock time without an offset, derived from the page on every run with no stored state, so that it equals the page's `start_time_local` in the index.
2. When a variable that references `$page_key` is resolved for a page, the fitdocs CLI shall bind `$page_key` to the identity the index uses for that page.
3. If a page records no start time, then the fitdocs CLI shall not fill it and it shall stay Waiting.
4. When a statement returns zero rows or a NULL, the fitdocs CLI shall treat the variable as absent, and shall never write it as `0` or as an empty value.
5. If a statement returns more than one row or more than one column, then the fitdocs CLI shall treat it as an error for that page.
6. When a statement returns an integer, a decimal, text or a date, the fitdocs CLI shall render it as text: an integer as its digits, a decimal without an exponent, a date as `YYYY-MM-DD`, and text as returned.
7. If a statement returns a floating-point value, finite or not, then the fitdocs CLI shall treat it as an error for that page, with advice to cast it in the SQL.
8. If a statement returns any other type, then the fitdocs CLI shall treat it as an error for that page, with advice to cast it to text in the SQL.
9. If a returned text value holds a line break of any kind, `<!--`, `-->` or `--!>`, then the fitdocs CLI shall treat it as an error for that page.
10. If resolving a variable fails for one page, then the fitdocs CLI shall leave that page as it was and continue with the next page, except as Requirement 7 states for a timeout.

### Requirement 4: Composing the post

**Objective:** As an athlete, I want the existing template rules to decide what is required and what is optional, so that there is nothing new to learn.

#### Acceptance Criteria

1. When a page is filled, the fitdocs CLI shall compose the title and description from the page's placeholder values and the variables' values, by the rules `fitdocs publish` already uses.
2. If a variable or page placeholder used outside an optional clause has no value, then the fitdocs CLI shall not fill the page and shall report `value_missing` with the name.
3. If any value an optional clause needs is absent, then the fitdocs CLI shall drop that clause and fill the page, and that text shall stand until a refill.
4. If the composed title is empty, then the fitdocs CLI shall not fill the page and shall report `title_empty`.
5. If the composed text holds `<!--`, `-->` or `--!>` from any source, then the fitdocs CLI shall not fill the page and shall report it.
6. When a page is filled, the fitdocs CLI shall write finished text, with no placeholder left to expand at publish time.
7. When `fitdocs publish` composes a Filled page, it shall produce exactly the post composed at the fill, including any braces and placeholder-like text in the values.

### Requirement 5: Region states and the athlete's words

**Objective:** As an athlete, I want anything I wrote to be safe from fitdocs, so that I can edit any post without losing it.

#### Acceptance Criteria

1. The fitdocs CLI shall decide a page's state from the bytes of its `post` region alone, as Waiting, Filled or Athlete's.
2. The fitdocs CLI shall never write the `post` region of an Athlete's page.
3. When a page is filled, the fitdocs CLI shall write a hidden comment above the text, which renders as nothing and holds a digest of the template, the as-of and a digest of the text.
4. When the athlete changes any of the filled text, removes the provenance comment or empties the region, the fitdocs CLI shall treat the page as Athlete's from then on.
5. The fitdocs CLI shall compute the template digest from `title`, `description` and each variable's name and SQL only, so that moving `since` or editing TOML comments does not mark a Filled page as made from an earlier template.
6. When a page is filled, the fitdocs CLI shall change only the inner content of its `post` region and leave every other byte of the page unchanged.
7. When a page is filled, the fitdocs CLI shall write it atomically, so that a reader sees the complete previous page or the complete new page.
8. When a page is about to be written, the fitdocs CLI shall read the region again and write only if its state is unchanged, so that an edit saved during the run wins.
9. The fitdocs CLI shall write only to pages of the current document format with intact region markers.

### Requirement 6: Filling automatically when a page is created

**Objective:** As an athlete, I want a new page to arrive with its post already written, so that I never run an extra command for it.

#### Acceptance Criteria

1. When `fitdocs sync`, with or without a source, or `fitdocs pull --sync` finishes its index refresh, the fitdocs CLI shall run the Fill Pass in the same command, so that a page that command created holds its filled text when the command ends.
2. The Fill Pass shall consider every top-level workout page that is Eligible, whether or not the page has opted in to any publish target.
3. If a Waiting page has a landed post, then the Fill Pass shall leave it unchanged, so that moving `since` back never queues updates in bulk.
4. If that command's index refresh did not end refreshed, unchanged or built, or reported any page error or data-source error, then the Fill Pass shall write no page and shall report the reason and the next step, because a number computed over an incomplete index would be wrong and would stay in the post.
5. The Fill Pass shall fill a page only when the index's copy of that page is identical to the current file.
6. When a Waiting page is not filled, the Fill Pass shall leave it Waiting and retry it on the next run, with no action from the athlete.
7. If the post template is refused, then the Fill Pass shall write no page and shall report the problem in one line that names `fitdocs post-template check`.
8. If the publish records cannot be read, then the Fill Pass shall write no page and shall report that, because it cannot rule out a landed post.
9. When the Fill Pass has written at least one page, the fitdocs CLI shall refresh the index again before the dashboard pass runs, so that a later `fitdocs query` reports no drift for those pages and the dashboard pass reads the outcome of that last refresh.
10. When the Fill Pass has written no page, the fitdocs CLI shall run no additional index refresh.
11. The Fill Pass shall never fail the command that runs it and shall never change that command's exit code; an unexpected error shall become one line of output.
12. When the Fill Pass is interrupted, every page shall hold either its complete previous bytes or its complete filled bytes, and the command shall exit as it does for any other interrupt.
13. `fitdocs regen` and `fitdocs load` shall not run the Fill Pass and shall not read the index for it; a Waiting page they leave current shall wait for the next `fitdocs sync` or a `fitdocs post-template refill`.

### Requirement 7: Keeping the Fill Pass quick and its report short

**Objective:** As an athlete, I want a slow query or a large backlog to stay out of my way, so that `fitdocs sync` remains something I run without thinking.

#### Acceptance Criteria

1. The Fill Pass shall stop any one statement after 5 seconds.
2. The Fill Pass shall stop starting new work 30 seconds after it begins.
3. If a statement times out or the 30 seconds run out, then the Fill Pass shall stop, keep the pages it already wrote and leave the rest Waiting for the next run.
4. When the Fill Pass stops early, the fitdocs CLI shall say so and shall name the variable that timed out, when one did.
5. When the Fill Pass has filled a page or left an Eligible page unfilled, the fitdocs CLI shall print the number filled, the number waiting and at most five lines of causes, each with a count, one example page and the next step.
6. While the post template is accepted and no page is Eligible, the Fill Pass shall print nothing.

### Requirement 8: What keeps a filled post stable

**Objective:** As an athlete, I want a filled post to stay exactly as written until I ask otherwise, so that nothing changes on a posted activity by surprise.

#### Acceptance Criteria

1. When `fitdocs regen` runs, the fitdocs CLI shall carry a Filled page's `post` region byte for byte, run no query, and succeed with or without an index.
2. When the index is rebuilt or deleted, a Filled page shall not change.
3. When a later workout arrives, a late import lands, a load is recomputed, or a benchmark or methodology changes, a Filled page shall not change until a refill.
4. When the post template is edited or `since` is moved, a Filled page shall not change until a refill.
5. The Fill Pass shall run no query for a Filled page.
6. When the post template file is deleted, every Filled page shall keep its text and `fitdocs publish` shall go on sending that text.

### Requirement 9: Checking the template

**Objective:** As an athlete or an assistant writing a template, I want to see what it would produce before it writes anything, so that I can get it right without touching a page.

#### Acceptance Criteria

1. The fitdocs CLI shall provide `fitdocs post-template check [PAGES...]`, which writes nothing to the data root and does not refresh the index.
2. When `check` runs without PAGES, it shall validate the post template and each variable's SQL, report every problem it finds, and report the number of Filled pages made from an earlier template.
3. When `check` runs with PAGES, it shall show for each page its state, whether it is in the window, whether it has a landed post, each variable's value or why it has none, and the composed post or why there is none.
4. When `check` is given a page in any state, in or out of the window, it shall show what the template would give for that page.
5. If the index is not built, needs a rebuild or is busy, then `check` shall still validate the post template file, shall say that the SQL was not checked and why, and shall count as a failure.
6. If the index's copy of a named page differs from the current file, then `check` shall say so in that page's result, because the values shown may be out of date.
7. `check` shall exit 0 when it finds no problem and 1 when it finds any.
8. If no post template file exists, then `check` shall exit 2 and name the expected path.

### Requirement 10: Re-running the queries on request

**Objective:** As an athlete, I want to recompute a post when I know a number has changed, so that I can correct it and see what that does before it happens.

#### Acceptance Criteria

1. The fitdocs CLI shall provide `fitdocs post-template refill [PAGES...] [--yes]`, which writes nothing without `--yes`.
2. When `refill` runs without PAGES, it shall consider every page in the window that is Eligible or Filled.
3. When `refill` is given PAGES, it shall consider each named page that is Waiting or Filled, in or out of the window and with or without a landed post.
4. `refill` shall use the current post template, and each page it writes shall record that template's digest.
5. If a named page is Athlete's, then `refill` shall leave it unchanged and report that it holds the athlete's own text.
6. When `refill` runs without PAGES, it shall report the number of Athlete's pages it left out.
7. When a page's text would change and the page has a landed post, `refill` shall name the page and say that the next `fitdocs publish --yes` will update the posted activity, with or without `--yes`.
8. When `refill` runs without `--yes`, it shall show for each page whether its text would change, and the new text when it would.
9. If a refill cannot compose a new post for a Filled page, then `refill` shall keep the page's existing text and report the page and the reason.
10. If the index's copy of a page differs from the current file, then `refill` shall leave that page as it was and name `fitdocs index` as the next step.
11. If `refill` composes the same text a Filled page already holds, then the page's composed post shall not change, so that the next `fitdocs publish` decides `unchanged` for a target it has landed on.
12. `refill` shall allow each statement 30 seconds, stop at the first timeout and keep the pages it already wrote.
13. When `refill --yes` has written at least one page, the fitdocs CLI shall refresh the index once before exiting, so that a later `fitdocs query` reports no drift for those pages.
14. When `refill` is interrupted, every page shall hold either its complete previous bytes or its complete new bytes, and the command shall exit 130.
15. `refill` shall exit 0 when no page failed, 1 when any page failed or the index is unavailable, and 2 before any write when the post template is absent or refused (including a variable's SQL refused under Requirement 2), a named page cannot be selected, or the publish records cannot be read.

### Requirement 11: Shared behavior of the command

**Objective:** As an athlete or an assistant, I want the new command to work like the commands around it, so that nothing about it needs separate explaining.

#### Acceptance Criteria

1. The `fitdocs post-template` command shall resolve PAGES as `fitdocs publish` resolves them.
2. The `fitdocs post-template` command shall accept `--format text` and `--format json`, with text as the default, and shall carry the same results in both.
3. The `fitdocs post-template` command shall write nothing to any page outside the `post` region and nothing to the post template, the settings file or the publish records.

### Requirement 12: The waiting refusal in `fitdocs publish`

**Objective:** As an athlete, I want a page still waiting for its text refused rather than sent with the default template, so that a later fill does not silently change a post I already sent.

#### Acceptance Criteria

1. If an opted-in page is Eligible, then `fitdocs publish` shall refuse that page for each selected target it opts in to and send nothing for it, in a dry run and with `--yes` alike.
2. The fitdocs CLI shall add one code for this refusal to the end of the closed publish vocabulary, leave every existing code and its explanation unchanged, and count the new code as a failure, so that the run exits 1.
3. The new code's fixed explanation shall say the page is waiting for its post and shall name both ways forward: `fitdocs post-template check` to see why, and writing the post by hand.
4. When a Waiting page is filled, or the athlete makes any edit to its `post` region, `fitdocs publish` shall no longer refuse it for waiting.
5. While a Waiting page is not Eligible, `fitdocs publish` shall treat it as it does today, including sending the per-target template.
6. The `fitdocs publish` command shall give a refusal it already gives for a page's state or facts ahead of the new code.
7. While no post template file exists, `fitdocs publish` shall never give the new code.
8. If the post template file fails a check in Requirement 1, then `fitdocs publish` shall stop with a configuration error (exit 2) before any request and before any write, on every invocation, naming the file and the problem.
9. `fitdocs publish` shall read no index and run no SQL, and shall give the same refusals whether or not an index exists.
10. When a Filled page is opted in, `fitdocs publish` shall decide and report it through its existing outcomes, so that a page with no post gives `would_post`, an unchanged post gives `unchanged` and a changed post gives `would_update`.

### Requirement 13: What stays on the machine

**Objective:** As an athlete, I want filling to stay local, so that adding numbers to my pages sends nothing anywhere.

#### Acceptance Criteria

1. The Fill Pass and the `fitdocs post-template` command shall make no network request.
2. The fitdocs CLI shall send filled text only through `fitdocs publish --yes`, for a page that has opted in to that target.
3. The fitdocs CLI shall run a variable's SQL read-only under the same sandbox as `fitdocs query`, so that it cannot read or write files or addresses outside the index.
4. The feature shall add no runtime dependency.
5. The feature shall not change the document format version, and shall not change the fresh placeholder's wording.

### Requirement 14: Published contract and documentation

**Objective:** As an athlete relying on fitdocs's written guarantees, I want them to state exactly what changed, so that I can trust what is left of them.

#### Acceptance Criteria

1. The ownership contract shall state that fitdocs may write a `post` region only while it is Waiting or Filled, and never while it is Athlete's.
2. The ownership contract shall state that `post-template.toml` is user-owned and read-only to fitdocs.
3. The ownership contract shall name a filled `post` region as the second exception to the rule that the index is never read back into a document, and shall state that the text is then carried as a snapshot, so that a page stays re-renderable and deleting the index still costs only rebuild time.
4. The change that lands this feature shall move every published copy of the changed rules, in steering, in the published documents, in the contract text in code and in the packaged skill.
5. The publishing guide shall document the template format, `since`, the two parameters, the value rules, the three region states, what keeps a post stable, the new outcome code, the ways out of a waiting refusal and the commands.
6. The publishing guide shall state that the `$as_of` requirement and the clock and randomness check are a lint and not a guarantee of stability, and shall name what they cannot catch: `first`, `any_value`, `LIMIT` without `ORDER BY`, tables that depend on today, and a statement that references `$as_of` without constraining by it.
7. The packaged skill shall carry a worked recipe that sums each page's load for one methodology, rather than reading the week's running total, and that uses invented numbers.
8. The project shall add no test that reads documentation, a changelog or a spec; a doc-binding test this change turns red shall be deleted and named in the amendment.
9. The contract version shall stay at the unreleased version if no release has been cut when this lands, and shall otherwise move by one.
10. The documentation site shall not be edited by this spec, because it describes released versions; its copy shall be recorded as a follow-up queue item.
