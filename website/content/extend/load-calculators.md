---
title: Write a load calculator
description: Add your own training-load method as a plugin, either packaged on PyPI or as a single local file, without forking fitdocs.
section: Extend
order: 1
---

# Write a load calculator

Coaches, sports scientists, and athletes disagree about how to measure training load, and there's room for more than one answer. fitdocs ships one built-in method (`threshold`) and treats every other method as a **plugin**. A running system, a cycling model, a strength-training load: you can add any of them without touching fitdocs' code.

## The contract, in one screen

A calculator is any object with this shape. There's no base class to inherit from.

```python
from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs.load import (
    AthleteField, InteractionSession, LoadContext, LoadOutcome,
    ProfileView, Unsupported,
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
        ...  # your method here
```

`compute` returns exactly one of four outcomes:

| Outcome | When |
|---|---|
| `Computed(result=LoadResult(...))` | You have a real number. |
| `Unsupported(reason=...)` | This sport is outside your method. |
| `MissingInputs(fields=...)` | An athlete input is still missing after fitdocs asked for it. |
| `NotComputed(reason=...)` | Nothing could be computed, and here's why. |

## The rules that matter

fitdocs' own calculator follows these, and plugins are expected to as well:

1. **Never make up a value.** Missing data leads to a typed "not computed" outcome. `compute` must never raise because athlete data is missing or bad.
2. **One number counts.** `LoadResult.value` is *the* load. Other channels you computed go in `non_selected`, each with the reason it wasn't chosen. A candidate you couldn't compute gets `value=None`, never `0`.
3. **Warnings never change the number.** Quality checks go in `flags`, each saying `detected`, `not-detected`, or `not-assessed`. Only say `not-detected` if the check actually ran.
4. **Talk to the user only through `session`.** fitdocs handles prompting, including non-interactive runs.
5. **Test against published numbers.** Pin your tests to the worked examples in your method's own source (a paper, a workbook, a reference implementation), not just to what your code currently outputs.
6. **Only bundle data you're allowed to share.** If lookup tables aren't yours to share freely, leave them out.

## Two ways to ship it

**As a package on PyPI**, so anyone can `pip install` it:

```toml
# pyproject.toml
[project]
name = "fitdocs-mycalc"
dependencies = ["fitdocs"]

[project.entry-points."fitdocs.load_calculators"]
mycalc = "fitdocs_mycalc:MyCalculator"
```

Installing the package is all it takes. No configuration is needed. (For `uv tool` or `pipx` installs, add it to fitdocs' environment: `uv tool install fitdocs --with fitdocs-mycalc`, or `pipx inject fitdocs fitdocs-mycalc`.)

**As a local file**, for a personal method you won't publish:

```python
# <data-root>/plugins/mycalc.py
from fitdocs.load import register

class MyCalculator: ...

register(MyCalculator())
```

```toml
# <data-root>/fitdocs.toml
[plugins]
path = "plugins"
```

Local plugin files run as ordinary Python code with your permissions. There's no sandbox.

## Check that it loaded

```sh
fitdocs plugins
```

Your calculator should be listed with its id, version, where it came from, and its sports. If it failed to load, the error appears below the list. A broken plugin is always a warning, never a failed run. Then:

```sh
fitdocs load --calculator mycalc --recompute
```

## Go deeper

- [The plugin platform](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/plugins.md): discovery, the public import surface, and what to do when a plugin is rejected
- [Contributing a load calculator](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/contributing-calculators.md): the full contract, `LoadContext`, the interaction session, and registration
- [Compatibility policy](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/compatibility.md): what the plugin API promises between versions

Built a calculator? Open an issue and it can be listed here.
