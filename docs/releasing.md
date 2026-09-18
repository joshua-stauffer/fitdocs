# Releasing fitdocs

This is the ordered release procedure a single maintainer can follow end to
end, by hand, from a clean checkout of the revision being released. Every
step below names the exact command that performs it, and which automation
job (task 6.3, task 6.4) runs the identical command when the process is
triggered by a version tag instead of run by hand — so the manual path and
the automated path can never quietly diverge (Req 5.1, 5.10).

The plan's rule, stated once here rather than repeated at every step:
nothing is published before step 5 passes. If any step stops the release,
fix the cause and start again from step 1; the public index is left
unchanged (Req 5.8). A released version is never re-published: once step 9
has run for `X.Y.Z`, that version number is spent, and a second publish
attempt for the same number is a failure of the publish job, not a silent
skip (Req 2.5).

## Automation jobs

The release workflow (task 6.3, task 6.4) is a chain of jobs; a job's
failure prevents every job after it. This table is the one place that
names all eight, so a later job cannot rename one without this table
catching it:

| Step | Automation job |
|------|----------------|
| 1. Quality gates | `gates` |
| 2. Cut the changelog entry | — (editorial; no job) |
| 3. Version consistency | `version` |
| 4. Build | `build` |
| 5. Artifact conformance and encumbered-content gates | `check` |
| 6. Clean-environment verification | `verify-artifact` |
| 7. Tag | — (git operation; pushing the tag triggers the chain) |
| 8. Rehearsal publication | `publish-testpypi` |
| 9. Public publication | `publish-pypi` |
| 10. Post-publication verification | `verify-published` |

## 1. Quality gates

The full test suite, the linter, and the strict type check must pass on the
exact revision being released — the same three commands
[`CONTRIBUTING.md`](../CONTRIBUTING.md#the-three-quality-gates) names and the
same three continuous integration runs on every push and pull request (Req
5.2):

```
uv run pytest
```

```
uv run ruff check . && uv run ruff format --check .
```

```
uv run mypy
```

**Stop if:** any of the three commands exits nonzero. Fix the failure and
re-run all three before continuing; a release never proceeds on a red gate.

**Automation:** the `gates` job runs these exact three commands.

## 2. Cut the changelog entry

Turn the standing `## [Unreleased]` section into a dated release entry, and
open a fresh `## [Unreleased]` above it for the next round of work:

```
## [X.Y.Z] - YYYY-MM-DD
```

The released version literal must be bumped to the same `X.Y.Z` in **three**
tracked places in the same change, not one: `[project].version` in
[`pyproject.toml`](../pyproject.toml), and `metadata.version` in **both**
packaged skills' frontmatter —
[`src/fitdocs/skills/fitdocs-workouts/SKILL.md`](../src/fitdocs/skills/fitdocs-workouts/SKILL.md)
and
[`src/fitdocs/skills/build-training-block/SKILL.md`](../src/fitdocs/skills/build-training-block/SKILL.md).
Follow [`CHANGELOG.md`](../CHANGELOG.md)'s own convention note for the entry
itself. `tests/test_changelog.py`, `tests/test_version_identity.py`, and
`tests/test_agent_skill.py` keep this honest — run them before moving on:

```
uv run pytest tests/test_changelog.py tests/test_version_identity.py tests/test_agent_skill.py
```

**Stop if:** any of the three fails. A failing `test_changelog.py` means the
new entry does not match the established Keep a Changelog format; a failing
`test_version_identity.py` means the released-version literal is missing
from one of its required locations (the manifest, the changelog's newest
entry, or a packaged skill's `SKILL.md`) or appears somewhere it must not;
a failing `test_agent_skill.py` means a packaged skill's `metadata.version`
was not bumped to match `[project].version` (`tests/test_agent_skill.py`'s
`metadata["version"] == project["version"]` assertion, pinned per packaged
skill).

**Automation:** none — this is an editorial step only a maintainer performs.
No job cuts a changelog entry or bumps a version on your behalf.

**Commit this change.** It is the revision the rest of this procedure
releases: step 1's three quality gates must be re-run against the commit
this step produces — a passing gate run from before the version bump does
not satisfy Req 5.2, which requires the gates to pass on "the exact revision
being released" — before you continue to step 3.

**Today's state:** `CHANGELOG.md` carries only `## [Unreleased]`; there is no
released entry yet, because fitdocs has not published a version. Step 3
below reports a `version_mismatch` violation until this step has run for the
first time — that is the expected state before this step is done, not a
defect to work around.

**Before the first release:** two of this project's own tests currently pin
the *pre-release* state and must change in the same commit as the first cut,
not after it: `tests/test_changelog.py::test_real_changelog_has_no_released_version_literal`
(which asserts no `## [X.Y.Z]` heading exists yet) and
`tests/test_changelog.py::test_real_changelog_has_added_entries_under_unreleased`
(which reads the `Added` entries from the standing `[Unreleased]` section,
where they will no longer live once this step moves them under the new
release heading). `tests/test_version_identity.py`'s
[`docs/plugins.md`](../docs/plugins.md) allowlist also pins the released-
version literal's example-snippet occurrence to today's version, and will
need updating the moment the manifest version diverges from that snippet.
Fixing these tests is not this step's job; they are named here so the first
maintainer to run this step is not surprised by them.

## 3. Version consistency

Confirm the manifest version, the changelog's newest released entry, and the
tag you intend to push all agree, before anything is built, using
[`scripts/check_artifacts.py`](../scripts/check_artifacts.py):

```
uv run python -m scripts.check_artifacts --no-artifacts --tag vX.Y.Z
```

**Stop if:** exit code is nonzero. A `version_mismatch` violation names which
pair disagrees (manifest/changelog, manifest/tag, or changelog/tag) and, when
the changelog has no released entry for the manifest's version at all,
reports that as its own violation too. Go back to step 2.

**Automation:** the `version` job runs this exact command.

## 4. Build

Build the one wheel and one source distribution the release ships, from the
working tree, into a cleared output directory, using
[`scripts/build_release.py`](../scripts/build_release.py):

```
uv run python -m scripts.build_release --out-dir dist
```

**Stop if:** exit code is nonzero. The build failed, or did not produce
exactly one wheel and one sdist; nothing downstream has anything to check.

**Automation:** the `build` job runs this exact command.

## 5. Artifact conformance and encumbered-content gates

This step needs the out-of-repository token match data the repository's own
re-introduction guard reads (Req 6.3; see
[`CONTRIBUTING.md`](../CONTRIBUTING.md#encumbered-material) for the rule
future contributors follow). The maintainer keeps this file
**outside the repository working tree** — a path a `git clone` of this
project never contains — and points `FITDOCS_FORBIDDEN_STRINGS` at its
absolute path for this command only. A source located *inside* the
repository is refused as a hard error, not merely a warning, because a
forbidden-term source that lives in the tree it is meant to police could
itself be edited away.

```
FITDOCS_FORBIDDEN_STRINGS=/absolute/path/outside/the/repository/match-data.txt \
    uv run python -m scripts.check_artifacts --tag vX.Y.Z
```

This runs both gates at once: the artifact conformance checks (required and
forbidden members, no link members, complete metadata) and the
encumbered-content scan, plus the version-consistency check again against
the artifacts now on disk.

**Stop if:** exit code is nonzero, in either of two distinguishable ways:

- A `gate_not_run` violation (exit 1) means `FITDOCS_FORBIDDEN_STRINGS` was
  **unset** — this **is a failed gate, never a step to skip**: set the
  variable to the maintainer's match-data file and re-run the command above
  before continuing.
- Any other broken source is a **hard error** (exit 2), raised with the
  guard core's own message, before either gate has scanned anything: the
  variable was **set** but names a path that does not exist, a file that
  could not be read, a source with no entries (empty or comments-only), or a
  path that resolves inside the repository working tree. Fix the path the
  message names and re-run the command above.

Any other reported violation names the offending member or metadata field
directly; fix its cause (usually
[`release/artifact-policy.toml`](../release/artifact-policy.toml) or the
build inputs) and return to step 4.

**Automation:** the `check` job runs this exact command, with the match data
supplied from the `FITDOCS_FORBIDDEN_STRINGS_CONTENT` repository secret
written to a runner-local file outside the checkout before the job runs.

## 6. Clean-environment verification

Install the built wheel — not the working tree — into an isolated tool
directory, and exercise the installed console command there. Export the
isolation variables **before** installing, in the current shell, so both the
install and the later invocations see them:

```
export UV_TOOL_DIR=$(mktemp -d)
export UV_TOOL_BIN_DIR=$(mktemp -d)
uv tool install --offline --from dist/fitdocs-X.Y.Z-py3-none-any.whl fitdocs
```

Invoke the installed binary **by its full path inside `$UV_TOOL_BIN_DIR`**,
not by its bare name: `UV_TOOL_BIN_DIR` is deliberately not added to `PATH`,
so a bare `fitdocs` resolves through `PATH` to whatever copy (if any) is
already installed globally on the maintainer's machine, silently exercising
the wrong binary instead of the one just built.

```
"$UV_TOOL_BIN_DIR/fitdocs" --version
"$UV_TOOL_BIN_DIR/fitdocs" --help
```

**Stop if:** the install fails, `"$UV_TOOL_BIN_DIR/fitdocs" --version` does
not print `X.Y.Z`, or `"$UV_TOOL_BIN_DIR/fitdocs" --help` exits nonzero. A
file missing from the wheel fails here, not for the first user (Req 5.3).

The automated equivalent of this whole step is
`uv run pytest tests/test_release_artifacts.py -k checkpoint`
(see [`tests/test_release_artifacts.py`](../tests/test_release_artifacts.py)),
which installs
the real built wheel into an isolated `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, runs
`fitdocs --version`, and drives a full `sync` over a synthetic source. Run it
with `FITDOCS_FORBIDDEN_STRINGS` set — as in step 5 — or its own encumbered-
content assertions skip rather than run.

**Automation:** the `verify-artifact` job runs the same install-and-run
sequence against the artifact the `build` job produced.

## 7. Tag

Record the released revision with a version tag matching the released
version number (Req 5.5):

```
git tag -a vX.Y.Z -m "fitdocs vX.Y.Z"
git push origin vX.Y.Z
```

**Stop if:** the push is rejected (for example, the tag already exists).
Never force-push a release tag over an existing one.

**Automation:** none directly — pushing this tag is what *triggers* the tag-
triggered gate and verification chain (task 6.3), which independently
re-runs steps 1, 3, 4, 5, and 6 against the tagged revision before any
publication job becomes reachable.

## 8. Rehearsal publication

There is no manual command for this step: no long-lived publishing
credential exists on a maintainer's machine, in the repository, or in any
secret store for either index (Req 5.7; design.md "Security
Considerations"). Pushing the tag in step 7 already triggered the release
workflow; once its earlier jobs (`gates`, `version`, `build`, `check`,
`verify-artifact`) have all passed, the `publish-testpypi` job publishes to
the rehearsal index (`https://test.pypi.org/legacy/`) automatically, with no
approval required, authenticating by a short-lived, per-release OIDC token
exchange scoped to that job alone (`permissions: id-token: write`) via
`pypa/gh-action-pypi-publish`. This is what makes the rehearsal path exercise
building and publishing without affecting the public index (Req 5.6): watch
the workflow run to confirm this job's outcome.

**Stop if:** the job fails, or reports the version already present on the
rehearsal index (a spent rehearsal version is not reused).

**Automation:** the `publish-testpypi` job.

## 9. Public publication

Publication to the public index happens only after the whole gate chain
above has passed, including the rehearsal, and only behind the
public-publication environment's manual approval gate (task 6.1's
environment configuration). **Approving that pending deployment in the
repository's Actions UI is the maintainer's only manual action in this
step** — there is no `uv publish` command to run by hand, and it must never
be run with a long-lived API token stored in the repository or on a
maintainer's machine. Once approved, the `publish-pypi` job authenticates by
its own short-lived, per-release OIDC token exchange, scoped to that job
alone (`permissions: id-token: write`), and publishes via
`pypa/gh-action-pypi-publish`; there is no API token anywhere in or
alongside the project (Req 5.7).

**Stop if:** the publish job reports the version already present on the
public index — a re-run of a spent version fails rather than silently
skipping (Req 2.5).

**Automation:** the `publish-pypi` job.

## 10. Post-publication verification

Confirm the published version installs from the public index and reports
the expected version, in a fresh, isolated tool environment (Req 5.9).
Isolate exactly as in step 6, and invoke by path for the same reason:

```
export UV_TOOL_DIR=$(mktemp -d)
export UV_TOOL_BIN_DIR=$(mktemp -d)
uv tool install --no-cache fitdocs==X.Y.Z
"$UV_TOOL_BIN_DIR/fitdocs" --version
```

The rehearsal equivalent, run against the TestPyPI index right after step 8.
Use a single `--index` (not the deprecated, priority-inverted
`--index-url`/`--extra-index-url` pair — under uv's default `first-index`
strategy, `--extra-index-url` takes priority over `--index-url`, which is
the opposite of what a rehearsal check needs): the named TestPyPI index is
tried first for `fitdocs` itself, and the default index (`pypi.org`) falls
through to supply the dependencies TestPyPI does not carry:

```
export UV_TOOL_DIR=$(mktemp -d)
export UV_TOOL_BIN_DIR=$(mktemp -d)
uv tool install --no-cache --index https://test.pypi.org/simple/ fitdocs==X.Y.Z
"$UV_TOOL_BIN_DIR/fitdocs" --version
```

**Stop if:** the install fails, or the reported version does not equal
`X.Y.Z`. This is the only step that runs after the version is spent — its
failure is a defect report, not a rollback; a released version is never
altered after the fact (Req 2.5).

**Automation:** the `verify-published` job runs the same install-and-check
sequence against the public index once `publish-pypi` succeeds.
