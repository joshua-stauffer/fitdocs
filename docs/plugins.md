# The plugin platform

fitdocs discovers third-party training-load calculators through two channels
— an installed Python distribution advertising an entry point, or a local
plugin file/directory you point fitdocs at — without ever forking or editing
core code. This page covers **discovery and distribution**: how fitdocs finds
a calculator, how to package or drop one in, and what to do when it doesn't
show up. It does not re-teach the calculator contract itself — see
[`docs/contributing-calculators.md`](contributing-calculators.md) for that
(the `LoadCalculator` protocol, outcome semantics, the interaction session,
and registration).

## Quick start: `fitdocs plugins`

At any time, run:

```
fitdocs plugins
```

This lists every registered calculator (built-in, packaged, and local) with
its id, display name, version, origin, and supported modalities, followed by
a block of any plugin load errors (or "No plugin load errors." when there are
none). It works even outside a configured data root — in that case it lists
built-ins and packaged plugins only, and states that no local plugin
configuration was consulted. Read-only: no network access, nothing written.

## Two ways to add a calculator

| | Packaged distribution | Local plugin file |
|---|---|---|
| Install | `pip install fitdocs-mycalc` (or your tool's equivalent) | Drop a `.py` file/directory next to your vault; point `[plugins].path` at it |
| Discovery | Automatic — advertises the `fitdocs.load_calculators` entry-point group | Configured — you name the path |
| Best for | Sharing a methodology with others, versioned releases | A one-off, bespoke, or unpublishable methodology |
| Distribution | PyPI (or a private index), `fitdocs-*` name | None — stays local to your machine |

Choose the **packaged** route if you intend to publish or reuse the
calculator across machines/vaults, want it to carry its own version, and are
comfortable with the packaging overhead. Choose the **local** route for a
quick, personal, non-published methodology, or when you don't want to publish
anything at all — a single file next to your data root is enough.

## The packaged example, end to end

This mirrors a real, working fixture in this repository's test suite
(`tests/fixtures/plugin_pkg/`), so it is a genuine worked example, not
pseudocode.

### 1. Source layout

```
fitdocs-mycalc/
├── pyproject.toml
└── fitdocs_mycalc.py
```

### 2. The calculator

`fitdocs_mycalc.py`:

<!-- doctest: worked-example start -->
```python
from __future__ import annotations

from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs.load import (
    AthleteField,
    InteractionSession,
    LoadCalculator,
    LoadContext,
    LoadOutcome,
    ProfileView,
    Unsupported,
)


class MyCalculator:
    calculator_id = "mycalc"
    display_name = "My Training Load Method"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        if activity.modality not in self.supported_modalities:
            return Unsupported(reason="mycalc supports running only")
        raise NotImplementedError  # your methodology here


def _conformance_check() -> None:
    """Not needed in your own calculator -- delete it when you copy this
    example. It exists only so fitdocs' own test suite can prove this page's
    worked example has not drifted from the shipped contract: mypy --strict
    only accepts this assignment if MyCalculator's members structurally
    satisfy LoadCalculator's signatures, so a drifted `compute` parameter (a
    removal, an addition, or a changed type) or a covariance-violating
    `required_athlete_fields` return type fails right here."""
    _c: LoadCalculator = MyCalculator()
```
<!-- doctest: worked-example end -->

`compute` takes a fifth, required parameter, `context: LoadContext` — the
only route to the resolved `[load]` configuration for this pass and the
activity's own recorded date. See
[`docs/contributing-calculators.md`](contributing-calculators.md) for the
full contract (outcome variants, `LoadContext`, the interaction session,
athlete-field prompting).

### 3. The extension-group declaration

`pyproject.toml`:

```toml
[project]
name = "fitdocs-mycalc"
version = "0.1.0"
description = "A training-load calculator for fitdocs."
requires-python = ">=3.11"
dependencies = ["fitdocs"]

[project.entry-points."fitdocs.load_calculators"]
mycalc = "fitdocs_mycalc:MyCalculator"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

The entry-point **group** name, `fitdocs.load_calculators`, is fixed — that
is what fitdocs scans for. The entry-point **name** on the left of `=`
(`mycalc` above) is yours to choose; it appears in diagnostic messages but is
not itself the calculator id. The value on the right names the class (or a
zero-argument factory function, or a ready instance) that fitdocs will load.

### 4. Install

```
pip install ./fitdocs-mycalc   # or: pip install fitdocs-mycalc, once published
```

Nothing else is required — no fitdocs configuration, no registration call.
Installing the distribution is the entire installation procedure.

### 5. Verify

```
fitdocs plugins
```

Your calculator's row shows its id (`mycalc`), display name, version (read
from the installed distribution's metadata), an origin of
`fitdocs-mycalc mycalc` (`<distribution name> <entry point name>`), and its
supported modalities. If it does not appear, see **Diagnosis** below.

## Local plugin files: the alternative

Instead of packaging, point fitdocs at a file or directory of files:

```toml
# <data-root>/fitdocs.toml
[plugins]
path = "plugins"   # relative to the data root, or an absolute path
```

- A **single file** path is loaded as itself.
- A **directory** path contributes its top-level `*.py` files, in
  alphabetical order. Files whose name starts with `_` are skipped (private
  helpers). Subdirectories are never descended into.
- Each file is executed under a reserved module namespace
  (`fitdocs_local_plugins.<stem>`); `sys.path` is never modified, so **each
  file must be self-contained** — it cannot `import` a sibling file in the
  same directory as if the directory were a package. Instead of registering
  through packaging, the file calls `fitdocs.load.register()` itself, exactly
  as [`docs/contributing-calculators.md`](contributing-calculators.md#8-register-it)
  teaches:

```python
# <data-root>/plugins/mycalc.py
from fitdocs.load import register


class MyCalculator:
    ...


register(MyCalculator())
```

A relative `path` resolves against the data root (so a vault stays portable
between machines); an absolute path is used as given. There is **no implicit
default location** — nothing local loads until you set `path` yourself.

### `[plugins]` settings reference

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `enabled` | bool | `true` | `false` disables **both** channels (entry-point and local) entirely. |
| `path` | str | absent (no local plugins) | A file or directory; relative resolves against the data root, absolute is used as-is. |

### Executing local files: no sandboxing

**A local plugin file is executed as ordinary Python code, with your own
user privileges, the moment fitdocs discovers it.** fitdocs applies **no
sandboxing**, no permission prompting, and no signature verification. It can
read and write anything your user account can, exactly like any other script
you run. Only point `[plugins].path` at code you trust — treat it the same
way you would treat any script you choose to execute. (Installing a packaged
distribution is no different in this respect: `pip install` already ran that
package's build and import machinery before fitdocs ever sees it.)

## Naming convention and id uniqueness

Published calculator distributions should be named `fitdocs-*` on PyPI (for
example, `fitdocs-mycalc`), matching the project's own naming so they are
discoverable and recognizable as fitdocs extensions.

A calculator's `calculator_id`, however, is a separate value from the
distribution name — it is the short, stable string written into a document's
`load_methodology` frontmatter and passed to `--calculator`. It must be:

- **short** — it appears in prompts, results, and `--calculator <id>`;
- **stable** — changing it later breaks any document that already recorded
  it;
- **unique across everything the user has installed** — built-ins, every
  packaged plugin, and every local file share one namespace. A duplicate id
  is rejected: the **incumbent calculator is kept** (registered first —
  built-ins, then packaged plugins, then local files, in that order), and
  the later registration is reported as a load error naming the contested
  id and **both origins** — the rejected newcomer (the error's subject) and
  the incumbent that was kept (in the detail).

## The public import surface

Plugin authors may depend on exactly the following names. Everything else in
fitdocs is internal and may change without notice — including the
`fitdocs.plugins` module itself, which is not public surface. fitdocs ships
one built-in calculator, `threshold`, registered the same way — through the
same `register()`/`validate_calculator()` gate — any other calculator is,
including the ones registered during fitdocs' own test suite.

From `fitdocs`:

```
Activity, Samples, SessionSummary, Lap, StrengthSet, DeviceInfo, Provenance,
Sport, Modality, SCHEMA_VERSION, fit_datetime, AthleteInputs, ZoneSpec,
DerivedMetrics, TrimpWeighting, parse_fit, compute_metrics, FitDecodeError,
NotFitFileError, FitIntegrityError
```

From `fitdocs.load`:

```
LoadCalculator, AthleteField, ProfileView, InteractionSession, LoadOutcome,
LoadResult, Computed, Unsupported, MissingInputs, NotComputed, LoadContext,
LoadSettings, LoadSettingsError, DEFAULT_LOAD_SETTINGS, NonSelectedValue,
QualityFlag, supports_activity, register, get, available, for_modality,
UnknownCalculatorError, InvalidCalculatorError, DuplicateCalculatorIdError,
Benchmark, BenchmarkKind, BenchmarkRef, BenchmarkAge, benchmark_age,
THRESHOLD_CALCULATOR
```

`Benchmark`, `BenchmarkKind`, `BenchmarkRef`, `BenchmarkAge` and
`benchmark_age` are the dated-measurement vocabulary. A calculator asks the
profile view for a benchmark *as of a date* — `profile.benchmark(kind,
discipline, on=context.activity_date)` returns the measurement current at that
date, or `None` — and `profile.has_benchmark(...)` answers the undated question
"is anything on file at all", so "none recorded" and "none applicable yet" stay
distinguishable. Declare a `BenchmarkRef` on an `AthleteField` to have the
prompt flow collect and persist one. `benchmark_age` compares a measurement
date against the activity date and returns a `BenchmarkAge` carrying the age in
days, the window it was compared against, and whether it is stale; the window
comes from `context.settings.benchmark_staleness_days`, never from the view.

`LoadContext` is `compute`'s required fifth parameter (see the worked
example above and [the `LoadContext` section][loadcontext-section]) — it is
the only route to the resolved `[load]` configuration and the activity's own
recorded date; a calculator never opens `fitdocs.toml` or reads a clock
itself. `supports_activity` is the module-level function the engine actually
asks through to determine whether a calculator covers a given activity; a
calculator may optionally narrow that answer with its own `supports` method,
but never calls `supports_activity` itself — see
[`docs/contributing-calculators.md`](contributing-calculators.md#2-answer-the-support-question-optional)
for how. `fitdocs.load` also re-exports its own `registry` submodule for
internal wiring; it is not part of this depend-on list — use the
module-level functions above (`register`, `get`, `available`,
`for_modality`) instead of importing `fitdocs.load.registry` directly.

`THRESHOLD_CALCULATOR` is fitdocs' own built-in `LoadCalculator` instance
(id `"threshold"`), registered by `fitdocs.load`'s package initializer
through the same `register()`/`validate_calculator()` gate this document
describes for a third-party calculator — it needs, and gets, no privileged
path. It is exported here for introspection (e.g. identity checks in a
plugin's own tests); look it up through `available()` or `get("threshold")`
rather than importing this name directly if all you need is "is the built-in
registered."

[loadcontext-section]: contributing-calculators.md#6-reading-configuration-and-the-activitys-date-only-through-loadcontext

fitdocs ships a `py.typed` marker, so these names carry inline type
annotations your own `mypy`/`pyright` can check against.

## Compatibility policy

**Before `1.0`, this surface is unstable and carries no
backward-compatibility obligation.** Within any `0.x` release, names may be
added, removed or renamed, and signatures may change. This is deliberate: the
contract is still being designed, and the alternative — bolting optional
fields onto a shape we already know is wrong — would make the surface worse
permanently in order to keep a promise made too early. From `1.0` onward the
surface follows SemVer, and removals are confined to **major** releases. (The
release mechanics that enforce that — versioning, changelog discipline —
belong to the project's distribution process, not to this guide.)

In practice, before `1.0`: pin the fitdocs version your calculator is built
against, and expect to make changes when you upgrade. `tests/test_public_api.py`
pins the surface inside this repository, so a change is always deliberate and
visible in the diff rather than accidental — but it is a guard against drift,
not a freeze.

<!-- historical-note: pre-1.0 rename; NotConfirmed here is a record of what
     changed, not published surface. A name-absence guard scanning this
     corpus should exempt this paragraph. -->

This has already happened at least once, and the guide you are reading
reflects the result: the load result contract was redefined and the
`NotConfirmed` outcome renamed to `NotComputed`. A calculator written against
the earlier shape does not run against this one.

## Diagnosis: what each failure looks like

Every discovery failure is isolated per plugin — one broken plugin never
aborts the run or affects the exit code. It appears both at the end of a
`sync`/`regen`/`load` run and in `fitdocs plugins`' error block, as a
`subject` (what failed) and a `detail` (why):

**Contract violation** — a required member is missing, blank, or the wrong
shape:

```
Plugin errors:
  fitdocs-mycalc: mycalc
    calculator <MyCalculator object at 0x...> does not satisfy the
    contract: calculator_id must be a non-empty str
```

**Duplicate id** — another calculator already claimed this id; the
incumbent (registered earlier — built-ins, then packaged, then local) is
kept, and the error names both origins: the rejected newcomer (the subject
line) and the incumbent that was kept (the detail). Here a packaged plugin
loses the id to one registered earlier:

```
Plugin errors:
  fitdocs-othercalc: other
    a calculator is already registered under id 'mycalc'; kept the registration from fitdocs-mycalc: mymethod
```

When the incumbent is a built-in the detail reads `kept the built-in
registration`; when it is a local file, `kept the registration from local
file <path>`.

**Entry-point import raises** — the distribution's module itself raised
while importing:

```
Plugin errors:
  fitdocs-mycalc: mycalc
    No module named 'numpy'
```

**Entry point resolves to the wrong shape** — commonly, pointing the entry
point at a module instead of a class/factory/instance:

```
Plugin errors:
  fitdocs-mycalc: mycalc
    entry point value must be a calculator class, a zero-argument factory
    callable, or a calculator instance satisfying the contract; got
    <module 'fitdocs_mycalc' ...>
```

**Configured local path missing or unreadable**:

```
Plugin errors:
  /Users/you/vault/plugins
    local plugin path does not exist or cannot be read
```

**Local file raises mid-import** — any calculators the file registered
*before* the raise stay registered:

```
Plugin errors:
  /Users/you/vault/plugins/broken.py
    bad lookup table row 12
```

In every case above, the run (or `fitdocs plugins`) still completes and
still exits `0` on account of the plugin failure alone — plugin load errors
are **warnings**, never failures, and never change the exit code. A separate,
unrelated per-file or per-document failure (e.g. a registered plugin's
`compute()` raising while scoring one specific activity) is the one case that
does affect the exit code (exit `1`), because that is an existing per-document
failure channel, not a plugin *load* error.

A malformed `[plugins]` table itself (e.g. `enabled` set to something other
than a boolean) is different in kind from all of the above: it is a
**configuration** error, reported before anything is written, and does exit
`2` — the same treatment `fitdocs` gives a malformed `[tiles]` table (see
[`README.md`](../README.md#choosing-a-provider)), rather than a
silently-ignored setting.
