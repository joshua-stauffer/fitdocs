# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who keeps their training in a markdown
wiki through fitdocs, and who also wants each workout's post (a title, their
own words and the workout's numbers) to appear on the platforms where their
training is seen, intervals.icu and Strava first, straight from the wiki and
without retyping anything.

**Current situation.** Nothing in fitdocs writes to a remote service. The
connector protocol reserves three capabilities for it (push activity,
annotate remote activity, resolve remote activity), and none is driven. No
templating seam exists, and a workout page has no place for a post. The
connector transport retries a data `POST` on 429, 5xx and network failures,
so a non-idempotent upload could land twice. The intervals.icu connector
puts up to 300 characters of a service's own response text into messages
that `fitdocs connect` and `fitdocs pull` print. Every future publish target
needs the same five things: what to post, whether the page has opted in, a
dry run, a record of what was posted, and a result vocabulary that carries no
text from the remote service. Built once per target, they would drift, and
the rule that nothing from a service comes back would be only as strong as
the weakest target.

**What should change.** A target-neutral publish core that every target
plugs into. A workout page opts in to publishing per target. Its post is
composed offline from a per-target template, or from an athlete-owned `post`
region on the page, with placeholders filled from the page's own managed
values; an absent value is never rendered as `0`. `fitdocs publish` is a dry
run by default that prints exactly what each opted-in page would post and
to which target; `--yes` posts. Running it again posts nothing new, and a
page whose composed post changed is posted again as an update. Every outcome
is one code from a closed, documented, append-only vocabulary explained in
fitdocs's own words, and nothing a target's service returns is printed,
logged or written, except the one activity link a target's own spec permits.
A publish ledger records what was posted, and a fitdocs-owned region on the
page links to each posted activity. The configured targets can be listed
from the CLI. A non-idempotent request is attempted exactly once.

Source: `.kiro/specs/publish-core/brief.md`; Phase 14 of
`.kiro/steering/roadmap.md` (wave 1, parallel with `relay-server`).
Dependencies: none. Downstream: `intervals-publish`, `strava-publish`,
`relay-intervals`, and the relay's pinned copy of the outcome vocabulary.
Extends `wiki-contract`, `workout-docs`, `connectors`, `effort-tags` and
`distribution`, and the packaged agent skill. The documentation site is not
edited (it describes released versions only); its publishing copy is
recorded as a follow-up queue item.

## Introduction

This feature gives fitdocs a publishing core without shipping any concrete
publish target. It defines what a post is and how it is composed, how a
page opts in, what `fitdocs publish` prints and does, what every target
receives and may answer, how outcomes are recorded and linked from the
page, and how a non-idempotent request is kept from landing twice. The
first targets (`intervals-publish`, `strava-publish`) plug into it in a
later wave.

Terms used below:
- A **publish target** (or **target**) is a configured connector instance
  whose connector can publish posts. Its **target name** is the instance's
  name in `fitdocs.toml`.
- A **post** is a title and a description. **Composing** a post turns a
  workout page into a post for one target, offline.
- A **template** is a title or description text with **placeholders**
  (`{name}`) and **optional clauses**, filled from a page's values.
- A page **opts in** to a target when its `publish` frontmatter key names
  that target.
- A **decision** is what a run would do for one page and one target: post it
  for the first time, update an earlier post, or nothing because the post is
  unchanged or the page is not opted in.
- An **outcome code** (or **code**) is one member of the publish
  vocabulary.
- A post has **landed** when the target has confirmed that its activity
  carries the post's title and description.
- The **publish ledger** is fitdocs's per-target record of what it posted
  for each page.
- A **publication id** is fitdocs's own random identifier for one page on
  one target, handed to the target with every request for that page.
- A **permitted link** is the one link to a posted activity that a target's
  own spec allows fitdocs to record. The **published region** is the
  fitdocs-owned region of a page that lists those links.

## Boundary Context
- **In scope**: the closed, append-only outcome vocabulary and its fixed
  explanations; the per-page, per-target opt-in (the `publish` frontmatter
  key); the athlete-owned `post` region; the built-in default template and
  per-target templates in `fitdocs.toml`, their placeholder syntax and the
  named placeholder set; offline, deterministic composition; `fitdocs
  publish` with its dry-run default, `--yes`, page and target selection,
  text and JSON output and exit codes; the target listing; the publish
  target contract in the connector framework (driving the three reserved
  publish capabilities); the single-attempt request mode in the connector
  transport and the publication id used as an idempotency key; the publish
  ledger and its version; the fitdocs-owned published region and the page
  contract changes that carry it; the packaged skill's publishing section;
  the repository documentation, the changelog, a follow-up queue item for
  the documentation site's publishing copy, and the amendment records on the
  specs this extends.
- **Out of scope**: any concrete target, including everything specific to
  intervals.icu, Strava or a relay (`intervals-publish`, `strava-publish`,
  `relay-intervals`, `relay-server`); how a target authenticates, finds its
  remote activity, uploads, or maps a service's answers into codes; the
  relay service; pushing planned workouts, including syncing a training
  block back to a service (the roadmap follow-on "Planned-workout push to
  intervals.icu"; the push-planned-workout capability stays reserved and
  undriven); deleting or retracting a post; media and photos; fields beyond
  the title and description; a publish-target plugin kind; opting pages in by
  a rule in the settings file; a daemon or scheduler; `fitdocs check`
  reporting a malformed `publish` key or `post` region; rewriting the
  network statements in `tech.md`, `docs/connectors.md`, the README and the
  connectors and distribution specs, which change with the first target
  that can make a publish request (this feature ships none).
- **Adjacent expectations**:
  - A target spec maps every answer its service gives into this feature's
    vocabulary, decides how it finds its activity, and declares the link it
    permits. It returns exactly one code per request.
  - The relay carries a byte-identical pinned copy of the vocabulary and
    answers a publish request with one of its codes; `relay-server` ships
    the drift check, and `strava-publish`, the first spec where both
    packages exist, adds the vocabulary's pinned copy to it.
  - The packaged skill names no service; the targets are discovered from the
    CLI.
  - Every other command (`sync`, `regen`, `load`, `check`, `index`,
    `query`, `dashboard`, `pull`, `connect`, and the rest) behaves as before,
    except that rendered and regenerated workout pages carry the two new
    regions and the `publish` key is carried as a user-owned key.

## Requirements

### Requirement 1: A Closed Outcome Vocabulary
**Objective:** As an athlete, and as the author of a publish target or of the relay, I want every publish outcome to be one fitdocs code with fitdocs's own explanation, so that nothing a platform says reaches my terminal, logs or wiki, and every target means the same thing by the same code.

#### Acceptance Criteria
1. The publish vocabulary shall be a closed set of outcome codes, each with a stable lowercase identifier and a fixed one-sentence explanation written by fitdocs.
2. The publish vocabulary shall be append-only: a later version shall only add codes after the existing ones, never remove, rename or reorder a code or change what it means, and an automated test shall pin the existing identifiers in order, so that every future code, including one a later planned-workout push needs, is an addition.
3. The publish vocabulary shall distinguish at least: would post, would update, unchanged, not opted in; an invalid opt-in, an unknown target, a page from an older or a newer fitdocs, a page with damaged region markers, an unreadable page, an invalid post region, an invalid template, a missing placeholder value, an empty title, missing activity facts, and a conflicting ledger record; posted to an existing activity, uploaded as a new activity, no matching activity, more than one matching activity, an activity the target cannot change, a missing activity file, not connected, unreadable credentials, rejected credentials, a missing permission, rate limited, unavailable, refused as invalid, sent with an unknown result, an unexpected target failure, not attempted after an earlier result stopped the target, a page whose published region could not be rewritten, and a ready target.
4. The publish vocabulary shall state, for each code, whether it means the post has landed, whether it counts as a failure for the exit status, whether a target may return it, and whether it stops further sending to that target for the rest of the run.
5. The publish vocabulary shall depend on nothing outside the language's standard library, so that a separately installed program can carry it unchanged without installing fitdocs.
6. When the fitdocs CLI reports a publish outcome, it shall print, log and write only the code, the code's explanation, and fitdocs's own text (a page name, a target name, a link label, and details of problems fitdocs found offline), and shall never print, log or write a body, header, message, identifier or URL that a target's service returned, except the permitted link of Requirement 12.
7. The published documentation shall list every code with its explanation, and an automated test shall hold that list equal to the vocabulary.

### Requirement 2: Opting a Page In
**Objective:** As an athlete, I want to choose, page by page and target by target, which workouts are published where, so that nothing is posted that I did not mark.

#### Acceptance Criteria
1. The fitdocs CLI shall recognize one user-owned frontmatter key, `publish`, on a workout page, whose value is either one target name or a list of distinct target names.
2. The fitdocs CLI shall never write the `publish` key into a document, and shall carry its lines through every rewrite byte-for-byte as it carries the effort-tag keys, whether or not its value is valid.
3. While a page carries no `publish` key, or carries an empty list, the fitdocs CLI shall post nothing from that page to any target.
4. Where a page's `publish` key names a target, the fitdocs CLI shall consider that page for that target, and shall never post the page to a target it does not name.
5. If a page's `publish` key is neither one target name nor a list of distinct target names, the fitdocs CLI shall report the page with the invalid-opt-in code and post nothing from it.
6. If a page's `publish` key names something that is not a configured publish target, the fitdocs CLI shall report that page and name with the unknown-target code, send nothing for that name, and still consider the page's other named targets.
7. When a page stops naming a target it was posted to, the fitdocs CLI shall send nothing more for that page to that target, delete nothing at the target, and keep the target's recorded link on the page.
8. The `publish` key shall change nothing about how a page is rendered, regenerated, loaded, indexed or checked, other than being carried as a user-owned key and never reported as unmanaged.

### Requirement 3: The Post Region
**Objective:** As whoever curates a workout page, I want to write that workout's own post on the page itself, so that a race or a memorable session can carry its own words while every other page uses the template.

#### Acceptance Criteria
1. The fitdocs CLI shall render every workout page with an athlete-owned `post` region whose fresh content is a hidden instruction that renders as nothing, and shall carry that region's content through every rewrite verbatim, as it carries the `notes` region.
2. While the `post` region holds nothing but hidden comments and blank lines, the fitdocs CLI shall compose the page's post from the target's template.
3. When the `post` region holds text, the fitdocs CLI shall read its first line as the title and the lines after one following blank line as the description, and shall compose the page's post for every target it opts in to from them instead of from the template.
4. When the `post` region holds only a title line, the fitdocs CLI shall compose a post with that title and an empty description.
5. The fitdocs CLI shall fill placeholders and optional clauses in the `post` region exactly as it fills them in a template.
6. The fitdocs CLI shall treat hidden comments in the `post` region as authoring notes and shall never post them.
7. If the `post` region's title line is followed by a line that is not blank, or a hidden comment in it is not closed, the fitdocs CLI shall report the page with the invalid-post code and post nothing from it.
8. The fitdocs CLI shall never change the `post` region's content, including when it publishes the page.

### Requirement 4: Templates
**Objective:** As an athlete, I want every page I opt in to get a sensible post without writing one, and to shape that default per target, so that publishing needs no per-page work.

#### Acceptance Criteria
1. The fitdocs CLI shall ship one built-in default template, a title and a description, that composes a post for every current workout page whatever values it lacks.
2. Where the settings file's `[publish]` table sets `title` or `description`, the fitdocs CLI shall use that template for every target in place of the built-in default's matching field.
3. Where a `[publish.targets.<name>]` table sets `title` or `description`, the fitdocs CLI shall use that template for the named target in place of the table-wide or built-in field.
4. The fitdocs CLI shall accept as a template only text, placeholders written `{name}`, literal braces written `{{` and `}}`, and optional clauses written `{?...}` whose text is included only when every placeholder inside them has a value; a template shall have no expressions, no other conditionals, no attribute access, no filters and no formatting options.
5. If an optional clause contains no placeholder or contains another clause, or a brace is unbalanced, the fitdocs CLI shall treat the template as having a syntax error.
6. If a template in the settings file names an unknown placeholder or has a syntax error, a title template spans more than one line, the `[publish]` table holds an unknown key or a value that is not text, or `[publish.targets]` names something that is not a configured publish target, then `fitdocs publish` shall stop with a configuration error naming the settings file, the table, the key and, for a template, the placeholder or position, before any request and before any write.
7. If a page's `post` region names an unknown placeholder or has a syntax error, the fitdocs CLI shall report that page with the invalid-template code, naming the placeholder or the position, and post nothing from it, while other pages proceed.
8. The fitdocs CLI shall validate the `[publish]` table on every `fitdocs publish` invocation, including a dry run, the target listing, and a run where no page opts in.

### Requirement 5: Placeholder Values
**Objective:** As an athlete, I want the numbers in my posts to be exactly the numbers on my pages, so that a post never states a value fitdocs did not compute and never invents one it lacks.

#### Acceptance Criteria
1. The fitdocs CLI shall fill placeholders only from the page's own managed values and from values derived from them by fixed arithmetic, and never from text the athlete typed (the notes, the effort tag, the `post` region's own words) or from any service.
2. The fitdocs CLI shall publish a fixed set of named placeholders covering at least the page's title, sport, local date, local start time, distance in kilometres and in miles, moving time, elapsed time, pace per kilometre and per mile, speed, average heart rate, average power, elevation gain, calories, training load and the load's methodology.
3. The fitdocs CLI shall render each placeholder in one fixed, documented format.
4. Where the page lacks the value a placeholder needs (the value is missing or malformed, or a derived value's inputs are missing or zero), the fitdocs CLI shall treat the placeholder as having no value, and shall never render it as `0`, as an empty string, or as any other default.
5. Where the page records a value of zero, the fitdocs CLI shall render that zero.
6. If a placeholder outside an optional clause has no value, the fitdocs CLI shall report the page with the missing-value code, naming the placeholder, and post nothing from it to that target.
7. When every placeholder in an optional clause has a value, the fitdocs CLI shall include the clause's text with its placeholders filled; otherwise the clause shall contribute nothing.

### Requirement 6: Composition
**Objective:** As an athlete, I want a page to compose the same post every time and a changed post to be recognized as changed, so that a dry run shows exactly what will be posted and an update is sent only when something changed.

#### Acceptance Criteria
1. The fitdocs CLI shall compose a post offline, reading only the page and the settings file, and shall compose byte-identical titles and descriptions from the same page and settings.
2. The fitdocs CLI shall compose a single-line title with surrounding whitespace removed, and a description whose line endings are newlines and whose trailing whitespace is removed.
3. If a composed title is empty, the fitdocs CLI shall report the page with the empty-title code and post nothing from it to that target.
4. The fitdocs CLI shall treat a composed post as changed exactly when its title or its description differs from the last landed post for that page and target, and for no other reason.
5. The fitdocs CLI shall compose each target's post separately, so that one page may send different posts to two targets with different templates.
6. If a workout page does not record its sport and its start time with the clock offset its device recorded, the fitdocs CLI shall report the page with the missing-activity-facts code and post nothing from it.

### Requirement 7: `fitdocs publish` and Its Dry Run
**Objective:** As an athlete, I want to see exactly what would be posted, where, before anything is sent, so that publishing is never a surprise.

#### Acceptance Criteria
1. The fitdocs CLI shall provide `fitdocs publish [PAGES...] [--to TARGET]... [--yes] [--targets] [--format text|json] [--out PATH]`, resolving the data root as every tree command does.
2. When no PAGES are given, `fitdocs publish` shall consider every workout page in `workouts/` in file-name order; when PAGES are given, it shall consider only those pages, each named by its file name (with or without `.md`) or by its path.
3. If a named page is not a workout page in `workouts/`, `fitdocs publish` shall stop with a configuration error naming it, before any request and before any write.
4. Where `--to` is given, once or more, `fitdocs publish` shall consider only the named targets; if a `--to` name is not a configured publish target, it shall stop with a configuration error naming every configured publish target, before any request and before any write.
5. While `--yes` is not given, `fitdocs publish` shall make no network request and write nothing (no ledger, no page, no credentials), and shall print, for each considered page and each target it opts in to, the decision and, for a page that would be posted or updated, the exact title and description it would post.
6. The fitdocs CLI shall decide would-post when the ledger holds no landed post for the page and target, would-update when the ledger's landed post differs from the composed one, and unchanged when they are equal, and the decisions and posts a dry run prints shall be exactly those a `--yes` run made next, with nothing changed in between, acts on.
7. The fitdocs CLI shall count, and not list, considered pages that opt in to none of the considered targets, except that a page named in PAGES is listed with the not-opted-in code.
8. If a page that opts in to a considered target was written by an older fitdocs, by a newer fitdocs, or has damaged region markers, `fitdocs publish` shall report it with the matching code and post nothing from it; if a page named in PAGES cannot be read, it shall report it with the unreadable-page code.
9. The fitdocs CLI shall print `fitdocs publish`'s text report as one line per page and target carrying the code, the post's text indented beneath it where printed, a summary of counts by code, and each printed code's explanation once; with `--format json` it shall print one JSON document of a stable, versioned shape holding the same results.
10. The fitdocs CLI shall exit `fitdocs publish` with 0 when no result carries a failure code, 1 when at least one does, 2 on a configuration error, before any request or write, and 130 when interrupted.
11. When no publish target is configured and no considered page opts in to anything, `fitdocs publish` shall say that no publish target is configured and exit with 0.

### Requirement 8: Posting with `--yes`
**Objective:** As an athlete, I want `--yes` to post exactly what the dry run showed and to carry on sensibly when a target fails, so that one bad page or one unreachable service never costs me the rest of the run.

#### Acceptance Criteria
1. Where `--yes` is given, `fitdocs publish` shall hand the target one publish request for each considered page and target whose decision is would-post or would-update, and shall record the target's one outcome code; it shall send nothing for a pair that is unchanged, not opted in, or refused offline.
2. The fitdocs CLI shall post a page to a target only when the page opts in to that target and `--yes` is given.
3. When `fitdocs publish --yes` runs a second time with nothing changed, it shall send nothing and leave the ledger and every page byte-identical.
4. The fitdocs CLI shall send one request at a time, taking pages in file-name order and each page's targets in target-name order.
5. If a target's outcome is one that stops the target, the fitdocs CLI shall send nothing more to that target for the rest of the run and report that target's remaining pairs with the not-attempted code, while other targets continue.
6. If a target cannot be prepared for sending because it has no credentials or its credentials cannot be read, the fitdocs CLI shall report each of its pairs with the not-connected or unreadable-credentials code and make no request to it.
7. If a target fails unexpectedly, or answers with a code a target may not return, the fitdocs CLI shall record the target-failure code, print no part of the failure's message, and continue with the next pair.
8. The fitdocs CLI shall save each outcome to the ledger before it sends the next request, so that an interruption keeps every outcome already received.
9. If `fitdocs publish --yes` is interrupted, the fitdocs CLI shall stop sending, keep every saved outcome, and exit with 130.
10. The fitdocs CLI shall report, for each pair sent, its outcome code and, when one was recorded, the permitted link.

### Requirement 9: The Publish Target Contract
**Objective:** As the author of a publish target, I want one published contract that says what a target receives and what it may answer, so that intervals.icu, Strava through a relay, and any later target plug in the same way.

#### Acceptance Criteria
1. The connector framework shall drive the annotate-remote-activity, resolve-remote-activity and push-activity capabilities through one publish operation, treat a connector that declares annotate-remote-activity as able to publish, and require a connector that declares resolve-remote-activity or push-activity to declare annotate-remote-activity too.
2. If a connector that declares any of the three publish capabilities lacks the publish operation or a link label, or declares resolve-remote-activity or push-activity without annotate-remote-activity, the connector framework shall reject its registration with a reason naming the problem, and register nothing.
3. The connector framework shall hand a target, per request, only: the publication id; the post's title and description; the subject being published, which for a workout page is the completed activity it records (its sport, its start time with the recorded clock offset, its elapsed time and distance where recorded and otherwise absent, the content digests of the page's archived files in rank order, and the location of its base file when the archive holds it); and the link recorded for that page and target by an earlier outcome, if any.
4. The connector framework shall take from a target exactly one code that a target may return and, only with a code meaning the post has landed, at most one link.
5. The connector framework shall leave finding the remote activity, deciding whether to upload, and mapping a service's answers into codes to each target, and `fitdocs publish` shall perform none of these steps itself.
6. The published target contract shall require a target to answer more than one matching activity with the ambiguous code and an activity it cannot identify from the facts given with the missing-activity-facts code, never by choosing one or by uploading.
7. The connector framework shall still never read, render or write a workout document, and shall receive the publish request only as plain values.
8. The connector framework shall add the publish operation, the set of publish capabilities, and the publish request and result value types to its published surface, the single-attempt mode being a field of the request type it already publishes, and the automated surface pin shall list them.
9. The connector framework shall keep the capability vocabulary at exactly nine members, keep push-planned-workout and the four pull capabilities other than pull-activities and pull-wellness reserved, and keep every capability's remote-change and irreversible marks.

### Requirement 10: Writes That Cannot Land Twice
**Objective:** As an athlete, I want a request that creates something at a service to be sent exactly once and to carry a stable identifier, so that a timeout or an interruption never leaves a duplicate activity behind.

#### Acceptance Criteria
1. The connector framework shall offer a single-attempt request mode: a request marked single-attempt shall be sent exactly once, whatever the response and whatever the network failure, in every client mode.
2. The connector framework shall keep the existing bounded retries of unmarked data requests and the single attempt of authentication requests unchanged.
3. The fitdocs CLI shall mint a page's publication id for a target, random and not derived from the page, and save it to the ledger before the first request for that page and target is sent.
4. The fitdocs CLI shall hand the same publication id on every later request for that page and target, never change it, and never reuse it for another page or target, so that a target can use it as an idempotency key.
5. When a target reports that a request was sent but its result is unknown, the fitdocs CLI shall record the unconfirmed code and shall not count the post as landed, so that the next run decides again and sends it again.
6. The published target contract shall require a target that can create an activity to look for an existing one before creating one on every request, so that a request repeated after an unknown result finds the activity rather than creating a second.

### Requirement 11: The Publish Ledger
**Objective:** As an athlete, I want fitdocs to remember what it posted, page by page and target by target, so that a run knows what is new, what changed, and where each post went.

#### Acceptance Criteria
1. The fitdocs CLI shall keep one publish ledger per target in the data root's tool-owned state directory, recording for each page its identity, the publication id, the digest of the last landed post, the last outcome code and when it was received, and the last permitted link with its label.
2. The fitdocs CLI shall key the ledger by page identity plus target, so that a record survives the page's rename, a change of its base file and its regeneration, and shall make the page identity name the kind of page, so that another kind of page can later be recorded the same way.
3. The fitdocs CLI shall write a version into every ledger and refuse to read a ledger of a newer version.
4. While a target has no ledger, the fitdocs CLI shall treat every page as never posted to it, and reading a ledger shall create nothing.
5. The fitdocs CLI shall write a ledger atomically, in a stable order, and only when its content changes.
6. If a ledger cannot be read, is malformed, is of a newer version, or was written for a different connector than the target now uses, `fitdocs publish` shall stop with a configuration error naming the file, before any request and before any write, and shall never overwrite or rebuild it.
7. If more than one ledger record matches one page, or one record matches more than one page, the fitdocs CLI shall report that page and target with the conflicting-ledger code and send nothing for them.
8. The fitdocs CLI shall write into the ledger nothing a target's service returned except a permitted link.

### Requirement 12: The Published Region
**Objective:** As an athlete, I want each published workout page to link to its posted activities, so that I can go from my wiki to the post in one click.

#### Acceptance Criteria
1. The fitdocs CLI shall render every workout page with a fitdocs-owned `published` region, empty in a fresh render so that it renders as nothing.
2. When `fitdocs publish --yes` considers a page, the fitdocs CLI shall rewrite that page's `published` region from the ledgers as one line listing each recorded link with its label in target-name order, or as empty when no link is recorded, shall rewrite nothing else on the page, and shall not write the page when the region is unchanged.
3. The fitdocs CLI shall record a link only from a target's answer with a code meaning the post has landed, and only when it is an `https` link that cannot break the line or the markdown link it is written into; otherwise it shall record no link and say so in the report.
4. A target shall declare its link label as fixed text, and the label shall be the only text beside the link in the region.
5. The fitdocs CLI shall carry the `published` region through regeneration as generated content, and shall replace hand edits to it the next time `fitdocs publish --yes` considers the page.
6. While `--yes` is not given, the fitdocs CLI shall never write the `published` region.
7. If a page's `published` region cannot be rewritten, the fitdocs CLI shall keep the recorded outcomes, report the page with the region-not-written code, and rewrite it on a later `fitdocs publish --yes`.
8. While a page has no `published` region because an older fitdocs wrote it, or was written by a newer fitdocs, the fitdocs CLI shall leave the page unwritten, reporting it only as Requirement 7 criterion 8 states.

### Requirement 13: The Page Contract and Versions
**Objective:** As a user relying on the published ownership contract, I want the new regions, key, ledger and command stated in it and versioned, so that nothing about publishing contradicts a guarantee I rely on.

#### Acceptance Criteria
1. The fitdocs CLI shall advance the ownership contract version to one more than its value at landing, with an append-only version history.
2. The fitdocs CLI shall advance the document-format version to one more than its value at landing, because every workout page gains the `post` and `published` regions.
3. The published ownership contract shall state the `post` region as user-owned, the `published` region as fitdocs-owned and refreshed by `fitdocs publish --yes` from the publish ledger, the `publish` key as user-owned, the ledger's location in the tool-owned state directory, the `[publish]` table of the settings file, and that `fitdocs publish` writes only the ledgers and `published` regions and never the `post` region or any other content.
4. The workouts ownership declaration shall name `post` among the user-owned regions, `publish` among the user-owned keys, and the `published` region as generated content refilled from the publish ledger.
5. If a page that opts in to a considered target is stamped with a lower document-format version, `fitdocs publish` shall not publish it, and `fitdocs regen` shall bring it current with both new regions in their fresh form and everything it preserves today preserved.
6. The fitdocs CLI shall render a workout page byte-identically for identical inputs, and a regeneration shall carry the content of the `post` and `published` regions.
7. The fitdocs CLI shall leave every other command's behavior unchanged apart from the two new regions on rendered pages and the carry of the `publish` key.

### Requirement 14: Listing the Targets
**Objective:** As an athlete, or an agent working my wiki, I want to list which publish targets are configured and whether each is ready, so that publishing is discoverable without reading the settings file.

#### Acceptance Criteria
1. When `fitdocs publish --targets` runs, the fitdocs CLI shall list every configured publish target in name order with its name, its connector, the connector's display name, which of the three publish capabilities it declares, and its state as a code: ready, not connected, or unreadable credentials.
2. When `fitdocs publish --targets` runs, the fitdocs CLI shall make no network request and write nothing.
3. When no publish target is configured, `fitdocs publish --targets` shall say so and exit with 0.
4. If `--targets` is combined with PAGES, `--to` or `--yes`, `fitdocs publish` shall stop with a configuration error.
5. The fitdocs CLI shall never show a credential value in the listing.
6. Where `--format json` is given, the fitdocs CLI shall print the listing as one JSON document of a stable, versioned shape.

### Requirement 15: The Packaged Skill's Publishing Section
**Objective:** As an agent working an athlete's wiki, I want instructions for publishing that hold for whatever targets the athlete configured, so that I can preview and explain posts without guessing which services are involved.

#### Acceptance Criteria
1. The packaged `fitdocs-workouts` skill shall gain a publishing section stating that fitdocs can publish workout posts to several publish targets the athlete configured, and naming no service, platform or brand.
2. The publishing section shall state how to list the targets with `fitdocs publish --targets`.
3. The publishing section shall state how a page opts in with the `publish` key and how to write the `post` region, with its placeholders and optional clauses.
4. The publishing section shall state that `fitdocs publish` without `--yes` changes nothing and shows what would be posted, that `--yes` posts irreversibly, and that `--yes` is run only when the athlete has asked for it.
5. The publishing section shall state how to read the outcome codes and what to tell the athlete about a failure code, shall link the publishing documentation, and shall say never to run `fitdocs connect`.
6. Every command, option and code the publishing section names shall exist in the release, under the existing skill guards.

### Requirement 16: Documentation and Records
**Objective:** As an athlete or a maintainer, I want publishing documented where I already look and recorded against every spec it changes, so that the feature is usable and its contract changes are traceable.

#### Acceptance Criteria
1. The fitdocs documentation shall gain a publishing page stating the command and its options, the `[publish]` settings, the template syntax, every placeholder and its format, the `post` region's syntax, the `publish` key, every outcome code with its explanation, the ledger, the `published` region, and that nothing a service returns is printed, logged or written except permitted links.
2. The feature shall edit no page of the documentation site, and shall record the site's publishing copy (a publishing guide page, the command and configuration reference entries, and each existing site line the feature makes stale, by file and line) as a follow-up queue item for the next release's site update.
3. The configuration documentation shall name the `[publish]` table and `fitdocs publish`, and the documentation index and the package's project links shall name the publishing page.
4. The changelog's unreleased section shall describe the feature, the new regions, the `publish` key, and the version changes.
5. The specs this feature extends (`wiki-contract`, `workout-docs`, `connectors`, `effort-tags`, `distribution`) shall each record an amendment, numbered as the next free amendment at landing, and existing criteria and approvals shall be preserved.
6. The project structure steering shall describe the publishing package and the direction of its dependencies.
