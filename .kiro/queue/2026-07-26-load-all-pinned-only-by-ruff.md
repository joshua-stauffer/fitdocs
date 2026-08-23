---
id: 2026-07-26-load-all-pinned-only-by-ruff
title: `fitdocs.load.__all__` membership is enforced only by ruff F401, not by the plugin-surface test
status: open
importance: low
importance_why: Nothing is broken today and ruff is a canonical gate, but the surface test reads as the `__all__` pin and is not one, so a session trusting it could drop a name from the published surface.
effort: S
kind: gap
area: plugin-api, tests/test_public_api.py, src/fitdocs/load/__init__.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 4.1, both review rounds independently)
pinned_at: c3d2201
resume_command: "do: decide whether tests/test_public_api.py should assert fitdocs.load.__all__ membership for the enumerated plugin-surface names, rather than leaving it to ruff F401 [queue: .kiro/queue/2026-07-26-load-all-pinned-only-by-ruff.md]"
context:
  - tests/test_public_api.py
  - src/fitdocs/load/__init__.py
blocked_by: []
---

## What
`test_every_load_plugin_surface_name_is_importable_and_correct` checks each
enumerated name with `hasattr` / `getattr` on the module. Module attributes
exist because of the `from ... import` statements, not because of `__all__`, so
removing a name from `fitdocs.load.__all__` while keeping its import leaves the
whole suite green. What actually catches it is ruff `F401` ("imported but
unused"), which fires with the help text *"Add unused import X to `__all__`"*.

This is pre-existing behavior of that test, not something task 4.1 introduced —
but 4.1 added five names to the published surface, so there is now five times
more of it.

## Why it matters
`__all__` is what `from fitdocs.load import *` honors and what documentation
generators and IDEs read as the published surface. The gap is narrow because
ruff is in the change-protocol DoD, so a dropped name does get caught — but it
is caught by a *lint* rule about unused imports, incidentally, and only while
the name has no other use in the module. A session reading the test would
reasonably believe `__all__` is pinned there. Worth an explicit decision rather
than leaving it implicit.

## Evidence
At `9a22c87`, remove `"BenchmarkRef"` from `src/fitdocs/load/__init__.py`'s
`__all__` while keeping its import:

```
uv run pytest -p no:cacheprovider   # 1998 passed
uv run ruff check .                 # F401 [*] `fitdocs.load.types.BenchmarkRef` imported but unused
                                    #   help: Add unused import `BenchmarkRef` to `__all__`
```

Verified independently by both task 4.1 reviewers. The same reviewer also
confirmed the complementary direction *is* well pinned: deleting any one of the
five re-exports outright reds two tests in `test_public_api.py`, and all five
are individually load-bearing.

Note the test's own comment (above `_LOAD_EXPECTED`) deliberately documents it
as an *inclusion* check rather than an `__all__`-equality pin — the plugin-api
design excludes `registry` from the plugin-author surface, so equality would be
wrong. Any fix must preserve that.

## Open questions
Is ruff F401 sufficient? Argument for leaving it: it is a canonical DoD gate and
the failure mode is loud. Argument against: it depends on the name having no
other module-level use, so it is not a general guarantee.

## How to pick it up
1. Read `tests/test_public_api.py` around `_LOAD_EXPECTED` (~line 147) including the comment explaining why it is an inclusion check.
2. If closing: add `assert name in fitdocs.load.__all__` inside the existing loop — one line, preserves the inclusion semantics, and does not forbid `registry`.
3. Done looks like: removing a name from `__all__` while keeping its import reds the suite, and `registry` is still allowed to be absent from `_LOAD_EXPECTED`.

Same "the pin is not where you would look for it" species as
[[2026-07-26-publicsurfacepin-names-wrong-test-module]].
