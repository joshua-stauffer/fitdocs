---
id: 2026-11-13-releasing-testpypi-install-command-fails
title: docs/releasing.md step 10's TestPyPI install command fails, because TestPyPI carries a duckdb outside the required range
status: open
importance: low
importance_why: The rehearsal check is manual and the public-index check in verify-published is unaffected; the cost is a maintainer hitting a failing documented command mid-release.
effort: S
kind: docs
area: docs/releasing.md
created: 2026-11-13
surfaced_by: 0.3.0 release, step 10 rehearsal check
pinned_at: ae74fc18
resume_command: "do: replace the TestPyPI install command in docs/releasing.md step 10 with one that resolves, and correct the paragraph above it that says pypi.org falls through for dependencies [queue: .kiro/queue/2026-11-13-releasing-testpypi-install-command-fails.md]"
context:
  - docs/releasing.md
blocked_by: []
---

## What
`docs/releasing.md` step 10 gives the rehearsal check as
`uv tool install --no-cache --index https://test.pypi.org/simple/ fitdocs==X.Y.Z`
and says the default index (`pypi.org`) "falls through to supply the
dependencies TestPyPI does not carry". Under uv's default `first-index`
strategy that only holds for packages TestPyPI has no copy of at all. TestPyPI
has a `duckdb` project, but no version in `>=1.2,<2`, so uv stops there and
the install fails.

## Why it matters
The documented command fails on every release while TestPyPI's `duckdb` stays
out of range, so a maintainer following the runbook cannot run the rehearsal
check as written. The paragraph's explanation of index priority is also wrong
for this case.

## Evidence
On 2026-11-13 with uv 0.13.6, after `publish-testpypi` succeeded in release run
43493193530:

```
uv tool install --no-cache --index https://test.pypi.org/simple/ fitdocs==0.3.0
hint: `duckdb` was found on https://test.pypi.org/simple/, but not at the requested version (duckdb>=1.2,<2). A compatible version may be available on a subsequent index (e.g., https://pypi.org/simple). By default, uv will only consider versions that are published on the first index that contains a given package, to avoid dependency confusion attacks.
```

What worked instead was fetching the wheel URL and sha256 from
`https://test.pypi.org/pypi/fitdocs/0.3.0/json`, checking the download with
`shasum -a 256 -c`, then running `uv tool install --no-cache --from <wheel> fitdocs`
in the isolated tool directories. That installed the package and printed `0.3.0`.

## How to pick it up
1. Pick a replacement. Two options keep pypi.org authoritative for dependencies:
   install the TestPyPI wheel by URL or path, as in Evidence, or name the
   TestPyPI index for `fitdocs` alone. `--index-strategy unsafe-best-match`
   also resolves, but it lets any TestPyPI upload win a dependency, which is
   the confusion `first-index` exists to stop.
2. Run the chosen command against an already published rehearsal version,
   such as 0.3.0, and confirm it prints the version.
3. Replace the command and its explanatory paragraph in step 10.

Done when the step-10 rehearsal command, run as written, installs and reports
the version.
