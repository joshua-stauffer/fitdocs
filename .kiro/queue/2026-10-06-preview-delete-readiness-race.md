---
id: 2026-10-06-preview-delete-readiness-race
title: Wait for the retained page after deletion before testing preview failure preservation
status: open
importance: medium
importance_why: A timing-dependent baseline test blocks unrelated canonical regression gates.
effort: S
kind: bug
area: docs-site, tests/sitebuild/test_preview.py
created: 2026-10-06
surfaced_by: /kiro-impl analytics-index task 7.1 review2 and debug1
pinned_at: 53d4a24
resume_command: "do: fix the post-deletion readiness race in tests/sitebuild/test_preview.py before introducing malformed content; preserve all existing HTTP, content, failure-report and source-preservation assertions [queue: .kiro/queue/2026-10-06-preview-delete-readiness-race.md]"
context:
  - tests/sitebuild/test_preview.py
  - scripts/sitebuild/preview.py
  - scripts/sitebuild/generator.py
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What

`test_live_preview_serves_edits_adds_deletes_failures_and_fixes` waits for the
deleted route to return 404, then writes malformed content. That 404 can occur
while Zensical is still rebuilding the last valid tree. The later `/why/`
assertion can therefore observe temporary missing HTML instead of the completed
retained page. Wait boundedly for `/why/` to serve `EDITMARKERONE` after deletion
before introducing the malformed content.

## Why it matters

The canonical analytics-index review failed this unchanged test twice even
though the task-local checks passed. The same timing failure was reproduced on
the immutable revision before the CLI task. This is test synchronization;
the investigation established no CLI regression or production contract defect.

## Evidence

- `tests/sitebuild/test_preview.py:1156` waits only for the deleted route's 404;
  `:1179` expects the retained `/why/` response to be 200 after a fixed sleep.
- At `53d4a24`, a diagnostic preserving the original status assertion observed
  `DEBUG broken initial 404 html False staged True`, then
  `DEBUG recovers while broken 200 elapsed 1.0616353747900575 html True` without
  changing malformed content. The original assertion still failed.
- Adding only the bounded post-deletion retained-page wait on that baseline
  passed every original assertion: `1 passed in 19.43s`. Diagnostic edits were
  restored byte-identically. One diagnostic pass does not prove every possible
  preview race is eliminated.
- Candidate and pre-CLI baseline uninstrumented exact tests also passed once,
  confirming timing dependence. The exact command is
  `uv run --python /Users/josh/.pyenv/versions/3.11.15/bin/python3.11 --group docs pytest tests/sitebuild/test_preview.py::test_live_preview_serves_edits_adds_deletes_failures_and_fixes -q`.
- Parent inspected raw debug outputs. Full artifacts are under
  `/private/tmp/analytics-index-evidence/7.1/debug1/`: `REPORT.md`,
  `baseline-trace-1.txt`, `baseline-synchronization.txt`, `candidate-exact.txt`,
  `baseline-exact.txt`, and `restoration-and-identity.txt`.

### Distinct added-page observation (analytics-index 8.2)

On the steering candidate based on `9ecf5a7`, a canonical run failed at
`tests/sitebuild/test_preview.py:1154` / helper `:1023` with
`not within 20.0 s: the added page`: 9,384 passed, one failed and two expected
actionlint skips. Its exact retry passed in 25.88s. Raw evidence is
`/private/tmp/analytics-index-evidence/8.2/review2/canonical-full.txt` and
the exact-retry output in that directory. The controller inspected the raw
failure and debugger report; it did not independently rerun the trace.

The debugger's current pre-steering baseline detected, built, staged and
served the added page within 4.16s, then candidate and baseline both hit the
separate later deletion/404 assertion. The original failed fixture had
already been removed, so its intermediate build/sync/HTTP state was
unavailable. The added-page timeout's internal cause remains unresolved
(MEDIUM confidence in transient preview-readiness classification); these
observations do **not** establish the deletion race as its cause or the
post-deletion wait as its fix. Diagnostic edits were restored. See
`/private/tmp/analytics-index-evidence/8.2/debug1/REPORT.md`,
`baseline-trace.txt` and `source-proof.json`.

The task was accepted only after an unchanged retry passed a fresh canonical
run: 9,385 passed, two expected skips, exit 0. Evidence:
`/private/tmp/analytics-index-evidence/8.2/review2-debug1-retry/VERDICT.md`.
The earlier failed run remains a failure. This item still owns the known
post-deletion synchronization repair; this extra observation bounds what
that repair can claim to resolve.

### Distinct initial-edit observation (analytics-index 8.3)

On the six-document amendment candidate based on `3e2191a`, the canonical
run failed at `tests/sitebuild/test_preview.py:1141` / helper `:1023` with
`not within 20.0 s: the edited text of /why/`: 9,384 passed, one failed and
two expected skips. Captured output said `Build started` without a completion
message; this does not establish which build, watcher or HTTP stage stalled.
The exact retry passed in 20.24s. The controller inspected the raw canonical
failure, exact retry and debugger report, but did not rerun the trace.
Evidence: `/private/tmp/analytics-index-evidence/8.3/review1/canonical-full.txt`
and `preview-exact-retry.txt` in that directory.

A detached pre-task `3e2191a` trace detected the edit at 4.223s, completed
build/sync at 7.476s and served the marker at 8.496s, 4.355s after the write.
It subsequently failed at the separate later deletion/404 assertion. The
initial-edit timeout was not reproduced, its original fixture was gone, and
its internal cause remains unresolved (MEDIUM readiness classification,
LOW exact mechanism). Preview code, tests and dependencies were byte-identical
before the amendment task. Diagnostic edits were restored. See
`/private/tmp/analytics-index-evidence/8.3/debug1/REPORT.md`,
`baseline-trace.txt` and `runtime-identity.json`.

Acceptance required an unchanged retry through a fresh full run: 9,385 passed,
two expected skips, exit 0; `/private/tmp/analytics-index-evidence/8.3/review1-debug1-retry/VERDICT.md`.
The earlier failure remains a failure. Neither the known deletion repair nor
the added-page observation explains or resolves this initial-edit stall.

### UTC recurrence (analytics-index 8.4)

The unchanged preview branch failed again at `test_preview.py:1179` during
UTC validation on the candidate based on `3cf3c2e`: `/why/` returned 404
instead of 200, with 9,385 passed, one failed and two expected skips in
379.31s. Raw output is
`/private/tmp/analytics-index-evidence/8.4/final-utc/pytest.txt`.
The controller inspected the actual traceback. Plain validation and the
DuckDB 1.2.0 floor check passed; CI validation was not run after the failure.

Debug2 confirmed that preview/stage/generator/test/dependency bytes match
the prior causal baseline and this is the same deletion/break assertion,
distinct from the initial-edit and added-page deadlines above. The current
fixture was unavailable after cleanup, so its precise assertion-time build
state was not newly traced. The earlier causal baseline is the evidence for
the known race; it is not a current-run trace. Report:
`/private/tmp/analytics-index-evidence/8.4/debug2-preview/REPORT.md`.
The failed UTC run remains failed; an unchanged fresh full UTC gate and CI
gate are required before accepting analytics-index. No preview patch or
timeout weakening was made in that feature.

The unchanged debug2 full UTC retry reproduced the same `:1179` / 404 failure:
9,385 passed, one failed, two expected skips in 269.65s, exit 1. The controller
inspected the final raw output at
`/private/tmp/analytics-index-evidence/8.4/final-utc-debug2-retry/pytest.txt`.
The two-debug-cycle limit was exhausted; task 8.4 is blocked on the owning
docs-site repair. CI mode remains unrun. Both UTC failures are preserved;
neither is replaced by the passing plain or floor checks.

## How to pick it up

1. Read the live-preview test's delete/break sequence and its bounded
   `wait_for`, `served`, and `unchanged_across` helpers, then the docs-site
   preservation requirements and preview/generator code.
2. Add the retained-page readiness wait after deletion using those helpers.
   Keep the original failure-status/content/source-preservation assertions and
   child cleanup. Build a controlled timing case to discriminate the readiness
   guard rather than relying only on an intermittently green live run.
3. Run the exact live-preview test and relevant sitebuild suite through
   `uv run --group docs pytest`, plus static checks. Use the project's correct
   interpreter and warm uv cache. Do not patch analytics-index around this test.
4. If the separate initial-edit or added-page deadline recurs during verification, capture
   polling build start/end, staged/HTML existence, sync containing the added
   page, generator process status and HTTP status **at the timeout, before
   fixture cleanup**. Diagnose that state before proposing another fix;
   preserve the timeout and original assertions instead of attributing it
   automatically to the post-deletion race.

## Owning repair landed; distinct initial-edit blocker remains (2026-10-06)

The generation-aware deletion repair landed on main and was pushed as
`2c17eb3`. A unique valid marker written after unlink must be served along
with the original marker before malformed input is written. Independent
review reproduced five claimed and two independent intended assertion
failures/restored passes; fresh unmodified full suite: 8,703 passed, two
expected skips, 162.58s, all statics clean. Parent completion: three passed
in 31.67s. Runtime and dependencies were unchanged. Evidence:
`/private/tmp/docs-site-readiness-evidence/review-generation-final/VERDICT.md`.

After analytics rebase onto that repair (`3a0b507`), plain full validation
passed 9,387 tests with two expected skips in 243.52s and all statics passed.
UTC failed both live-preview cases at the **initial edit**,
`test_preview.py:1143` / helper `:1024`: `not within 20.0 s: the edited text
of /why/`. Both failures occurred before deletion or the new generation wait.
UTC result: 9,385 passed, two failed, two expected skips, 274.60s, exit 1.
Raw: `/private/tmp/analytics-index-evidence/8.4/final-authorized-review/utc/pytest.txt`.
The controller inspected both tracebacks. No state was captured at timeout
before cleanup; native timing cause remains unknown. This is separate from
the repaired predicate gap, and a plain pass does not waive the UTC failure.

The existing initial-edit/add observations remain open context. Both the
analytics task and owning repair exhausted their two debug rounds; no third
debug or unchanged retry was run. Next work must explicitly scope the
remaining initial-edit stall and capture polling/build/sync/HTTP state at
timeout before proposing a repair. Preserve all deadlines and assertions.
The original deletion-focused pickup recipe above is historical after
`2c17eb3`; this initial-edit investigation is the remaining follow-up.

### Index verification resume — 2026-10-07

On main landing `a413d15` with the pending 27 mypy registrations, independent
unmodified plain acceptance failed: 9,386 passed, one failed, two expected
skips, 297.67 seconds. The original live case timed out at initial edit
1143/helper1024, before deletion. UTC/CI were not run after that failure.
The final allowed failure-only diagnostic passed 9,387 tests/two skips in
287.82 seconds; no failure capture fired, so native cause remains unknown.
Original source was restored exactly. Debug returned `STOP_FOR_HUMAN`;
the diagnostic pass does not replace failed acceptance, and there was no
third debug round or retry. Evidence:
`/private/tmp/analytics-index-evidence/verification-resume/final-review/`
and `initial-edit-debug2/REPORT.md`. Floor, release artifacts and installed
wheel smoke passed independently. Task 8.4 remains blocked on this owner.

### Native cause found: fseventsd starvation, not fitdocs or Zensical (2026-10-07)

A standalone reproducer outside pytest (`/private/tmp/docs-site-preview-fsevents-evidence/repro.py`)
drove the real build → `sync_tree` → `zensical serve` 0.0.65 path and
stalled at the initial edit in 8 of 38 trials. A `sample` of every stalled
generator showed it idle: all `zrx/executor` threads parked, the
`notify-rs fsevents loop` thread in `CFRunLoopRun`. No event had arrived.

An independent minimal FSEvents watcher (`fsw.c`, `FileEvents|NoDefer`,
latency 0.05 s) on the same `live/` directory missed the same events. In
**every** stalled run3 trial (4, 5, 6, 7, 14) it got no `staged/why.md` event
for the edit within 20 s: none at all, or only after the later touch at
about 69–75 s. Healthy trials got the event within about 2 s of the sync.
Neither stream saw drop flags. So macOS delivered the events late or not at
all to both subscribers, and Zensical only inherits that.

At the time, `fseventsd` was using 176 % CPU (load average 41–51). The main
churn was another project's runaway review harness running
`cp -R /. <tmpdir>`, a recursive copy of the whole root filesystem (6.2 GB
written, data volume 94 % full). Peer sessions here also cause heavy file
churn: HealthFit corpus copies, full syncs and concurrent full suites. The
earlier unexplained initial-edit, add and fix-stage stalls (live process
alive, staged bytes correct, HTML stale) match this mechanism. The
deletion-predicate repair `2c17eb3` is still correct and separate.

Implication: no fitdocs or Zensical patch removes this. Any FSEvents
watcher stalls while `fseventsd` is saturated. Before running a canonical
gate, check `ps -o pcpu= -p $(pgrep -x fseventsd)`. Do not run
the live-preview tests while it is saturated, and do not treat a stall
under that condition as a regression. A product-side hardening option for a
human decision: `preview.serve` already knows when it synced. It could
restart, or otherwise force, the generator when served output stays stale.
That changes the docs-site design's one-process contract and needs approval
first.

### Repair: Zensical polling watcher (2026-10-07)

Josh approved the product-side repair. `generator.start_serve` now starts
`zensical serve` with the caller's environment plus `ZENSICAL_POLL_WATCHER=1`.
Zensical 0.0.65 reads that variable in
`crates/zensical-watch/src/agent/monitor.rs`, and any value selects notify's
`PollWatcher` (500 ms, or `ZENSICAL_POLL_INTERVAL`). No FSEvents are involved.

Under continued load, with `fseventsd` at about 100 % CPU:
- The reproducer with polling ran 24 of 24 trials with no stall; the edit was
  served 0.31–0.42 s after the sync. In the same trials the independent
  FSEvents watcher missed the edit 19 times (`run4-poll/`).
- Both live-preview tests, run six times each: 12 of 12 passed with the fix.
  Six runs at the unfixed `HEAD` the same way failed 4 of 12, with
  `the added page` (twice) and `the fixed text of /why/` hitting the 20 s
  limit. Deadlines and assertions are unchanged.
- Unit pin: `test_start_serve_selects_the_polling_watcher`. It fails when the
  variable is dropped or when the inherited environment is replaced.

Peers blocked on the live-preview gate should rebase onto the merge and
rerun their gates.

### Analytics-index confirmation — 2026-10-07

After consuming main0b92561/polling repair9384516, independent unmodified
plain, UTC and CI suites each passed9,388 tests with two expected skips
in269.43/265.59/283.53 seconds respectively. Every mode's statics passed;
task8.4 independently APPROVED. Fresh floor62 and release/installed-wheel
checks passed. Earlier failures remain failed records. Evidence:
`/private/tmp/analytics-index-evidence/verification-polling/review/VERDICT.md`.
The shared log also records downstream derived1.1 canonical9395/2skips
and query1.3 canonical9477/2skips after the same repair; those sessions
retain their own subsequent task gates. This confirms the analytics-index
blocker is cleared; queue closure is left to the owning queue workflow.

## analytics-derived added-page recurrence (2026-10-07)

Task 1.1 records-only candidate at base `a413d15`, using canonical pyenv Python 3.11.15 and warm uv cache, failed its required full gate: 9,393 passed, one failed, two expected actionlint skips, 300.41 seconds. The unchanged controlled live-preview test failed at `tests/sitebuild/test_preview.py:1157`, helper `:1024`, `not within 20.0 s: the added page`; this is before deletion. Output only shows Serving/Build started and does not establish which transition stalled. No state was captured at timeout before cleanup; cause remains UNKNOWN. Source, preview tests and dependency declarations are unchanged by the candidate. This symptom matches an earlier unresolved added-page observation, not proof of a common mechanism or the repaired deletion race.

Independent task-local evidence passes (113 scoped tests, static checks, 19 claimed plus two own mutations). Required canonical review remains REJECTED; debug round 2 returns STOP_FOR_HUMAN. The reviewer's already-started standalone run passed once in 22.89 seconds; it does not supersede the failed full gate. No third debug, guessed patch or unchanged retry was made. Raw evidence: `/private/tmp/analytics-derived-evidence/1.1/reviewer-r1/full-pytest.txt`; debug: `/private/tmp/analytics-derived-evidence/preview-debug/report.md`. Durable downstream handoff: `.kiro/specs/analytics-derived/implementation-blocker.md` on `impl/analytics-derived`.

The next owning investigation must explicitly include the added-page deadline as well as the separately observed initial-edit deadline, with failure-time build/watcher/stage/sync/generator/HTTP capture before cleanup. Preserve all existing deadlines and assertions. A deletion-readiness repair or intermittent standalone pass cannot establish an added-page repair.


## analytics-derived confirms fresh gate after polling repair (2026-10-07)

After rebase onto owning repair `0b92561`, independent task 1.1 review passed its fresh canonical gate: 9,395 passed, two optional actionlint skips, 262.54 seconds, exit 0. Both original live-preview tests pass without deadline or assertion changes. Task-local mutations and static checks pass; parent scoped verification is 113 passed. The earlier failed canonical runs remain historical failed records. This confirms analytics-derived's task 1.1 gate; other peer confirmations still belong to their controllers.

## Initial-edit recurrence after the polling repair (2026-10-08)

On main `f8cc39b`, which contains polling repair `0b92561`
(`scripts/sitebuild/generator.py:24` sets `ZENSICAL_POLL_WATCHER=1`), an
unmodified full run during `/kiro-validate-impl activity-identity` failed
`test_live_preview_post_delete_wait_requires_last_good_readiness` at the
**initial edit**: `tests/sitebuild/test_preview.py:1143` / helper `:1024`,
`not within 20.0 s: the edited text of /why/`, entered via `:1271`.
Result: 1 failed, 9,622 passed, 8 skipped (2 actionlint, 6 forbidden-strings
unset), 235.58 s; plain mode, interpreter from `uv run`. No state was captured
at timeout. The exact test then passed 3/3 standalone (9.72/5.79/5.39 s) and an
unchanged full rerun passed: 9,623 passed, 8 skipped, 228.59 s, exit 0. The
machine was concurrently running other sessions' work.

So the polling watcher did not eliminate the initial-edit stall; it only made
it rarer. The memory-level claim "FIXED 0b92561" is too strong. The pickup
recipe's step 4 (capture build/watcher/stage/sync/HTTP state at timeout,
before cleanup) still stands.
