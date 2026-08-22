---
id: 2026-07-26-second-load-reader-spellings-escape-guards
title: Four spellings of a second [load] reader still escape the single-reader guards
status: done
importance: medium
importance_why: Four sibling specs add [load.*] sub-tables; an unguarded second reader is the cross-spec failure Req 14 exists to prevent. Reopened 2026-07-27 — the closure's evidence never reached main.
effort: M
kind: gap
area: training-load, tests/load/test_settings.py
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-second-load-reader-spellings-escape-guards.md] Close or formally accept the four remaining second-reader spellings"
context:
  - .kiro/specs/training-load/requirements.md
  - .kiro/specs/training-load/tasks.md
  - tests/load/test_settings.py
  - src/fitdocs/load/settings.py
blocked_by: []
---

## What
Task 6.4 built three guards for Req 14.1 (an AST call-site walk with per-file ImportFrom alias resolution, a package-wide literal-key parse walk, and a `sys.modules` reader spy). Four spellings of a real second reader still pass all three plus ruff and mypy: (1) dict iteration -- `for k, v in load_settings_document(root).items(): if k == "load"`; (2) `dict.get(document, "load")`, where the first Call arg is the mapping not the key; (3) `document.pop("load")`, a Call on `.pop` not `.get`; (4) a default-parameter capture `def f(..., _r=load_load_settings)`, which never becomes a module attribute so the sweep's `vars(module)` walk misses it.

## Why it matters
`tasks.md`'s accepted residual is the *aliased-key* spelling only (`_T = "load"; doc.get(_T)`), and it tells 6.4 not to chase the family with more pattern-matching. Spelling (1) is more plausible than the accepted one and is not covered by that acceptance. Either the acceptance should be widened explicitly -- so a future reader knows the guard's real perimeter -- or a runtime approach (instrument the settings-document reader itself and attribute reads by caller frame) should replace pattern-matching.

## Evidence
Spelling (1) measured by the task 6.4 round-4 reviewer: a validating second reader using dict iteration in `src/fitdocs/audit.py` left the suite at 1852 passed, ruff and mypy clean. Spelling (4) measured in round 3, same result. Spellings (2) and (3) derived by reading the clause bodies at `tests/load/test_settings.py:353-367` (`func.attr == "get"` only) -- not individually run.

## How to pick it up
Read `tests/load/test_settings.py:346-400` (the literal-key walk) and `:435-470` (the spy), then `.kiro/specs/training-load/tasks.md`'s task 4.2 Implementation Note on why pattern-matching has a ceiling. Decide first whether to widen the guard or widen the documented acceptance -- both are legitimate; what is not legitimate is a docstring claiming a perimeter the guard does not have. Done when the guard's real perimeter and its docstring agree, verified by running each of the four spellings.

## Resolution (2026-07-27 — CLOSED against the shipped tree)

**Done 2026-07-27.** Verified against the item's own done-condition ("the
guard's real perimeter and its docstring agree, verified by running each of the
four"), measured on `main` at `56012ca`, not on any worktree commit.

The work that actually closes this landed via `impl/load-second-reader` →
`main` (`0a48591` + `189ea70`, merged 2026-07-27T06:59Z), **not** the
superseded `8688dcc` the 2026-07-26 closure cited. The reopening below was
correct at the time it was written and is now itself superseded: it was
resolved by the narrower guard `main` kept, plus the perimeter documentation
that shipped with it.

**Measured perimeter** of `_reads_load_table_literally` as shipped
(`tests/load/test_settings.py:407-485`), by importing the helper and feeding
it ASTs:

```
d["load"]                 -> True
d.get("load")             -> True
dict.get(d, "load")       -> True     # spelling (2)
d.__getitem__("load")     -> False
d.pop("load")             -> False    # spelling (3)
d.setdefault("load", {})  -> False
o.get("mode", "load")     -> False    # negative control
regions.pop("load")       -> False    # negative control
```

Per-spelling disposition, each matching what the shipped docstrings claim:

- **(2)** `dict.get(document, "load")` — **closed**, matched at `args[1]` and
  only when the receiver is the literal name `dict`
  (`test_settings.py:472-478`), with a fixture offender at `:638`.
- **(4)** default-parameter capture — **closed**, the `sys.modules` spy sweeps
  each swept function's own `__defaults__`/`__kwdefaults__`
  (`test_settings.py:806-821`), covering both positional and keyword-only
  forms.
- **(1)** dict iteration and **(3)** `document.pop("load")` — **formally
  accepted residuals**, which is the resolution the reopening asked for. The
  reasoning is stated in the guard's own docstring
  (`test_settings.py:431-455`, `:582-594`) and is the measured one: `"load"`
  names three unrelated things in this tool at once — the settings table,
  `fitdocs.contract.LOAD_REGION`, and the `@app.command("load")` CLI verb — so
  `ast.Compare(==)` and `.pop` were **dropped, not narrowed**, because no
  argument-position rule separates them from legitimate code. All three
  false-positive constructs ship as **negative controls** (`:662-676`) so a
  future widening reddens rather than silently reintroducing them.
- The aliased-key spelling (`_T = "load"; doc.get(_T)`) remains the
  pre-existing documented residual, closed only by the behavioural spy.

The reopening's specific complaint is answered: the guard does **not** claim to
catch `__getitem__`, `.pop` or `.setdefault` anywhere in its docstrings, so no
shipped prose asserts a perimeter the guard lacks. `main`'s deliberate
narrowing was not re-widened.

`tests/load/test_settings.py` — 26 passed.

**Carried forward, not fixed here:** `document.__getitem__("load")` and
`document.setdefault("load", {})` escape the walk and are the only two
spellings surfaced by this item's history that appear in *neither* the closed
set nor the documented-residual set. Filed as
[[2026-07-27-getitem-setdefault-residuals-undocumented]].

Also still open and still needing the correction this item's reopening
identified: [[2026-07-26-class-scoped-second-reader-bindings]], whose "shipped
docstrings now name both" claim also rode `8688dcc`.

## REOPENED 2026-07-27 — the closure below was written against a commit that never reached `main` (SUPERSEDED by the Resolution above)

**Read this before the Resolution section; parts of it are false against the
shipped tree.**

The 2026-07-26 closure cited commit `8688dcc`, made on the
`impl/athlete-benchmarks` worktree. That branch's edits to
`tests/load/test_settings.py` conflicted with `training-load`'s own landing of
the same work, and on 2026-07-27 the conflict was **resolved in `main`'s
favour** — deliberately, because `main`'s version narrowed the accessor
perimeter that `8688dcc` had widened, having measured `.pop` and `__getitem__`
matching legitimate code (`regions.pop("load")`, CLI dispatch
`command_name == "load"`) and documented negative controls for them across two
review rounds. `main`'s narrower guard is the better one and was kept.

`git merge-base --is-ancestor 8688dcc HEAD` and `... 8688dcc main` both report
**NOT an ancestor** — the commit exists on neither branch.

**What is still genuinely closed** (verified against the shipped tree):

- Spelling **(4)**, the default-parameter capture — `main`'s version retains the
  `__defaults__`/`__kwdefaults__` sweep. Confirmed present.

**What is NOT closed, contrary to the Resolution below:**

- `document.__getitem__("load")`, `document.pop("load")` and
  `document.setdefault("load", {})`. Measured by importing the shipped helper
  and feeding it ASTs:

  ```
  d["load"]                 -> True
  d.get("load")             -> True
  d.__getitem__("load")     -> False
  d.pop("load")             -> False
  d.setdefault("load", {})  -> False
  ```

  `main`'s guard deliberately drops `.pop` and never adds `__getitem__` or
  `setdefault`. So the Resolution's sentence "closed by naming it in the
  literal-key walk's accessor set … `.pop` and `.setdefault` closed with it" is
  **false against the shipped guard**.

**The open question is therefore narrower than the original item, and is a real
design decision rather than an oversight**: `training-load` measured that
widening to `.pop`/`__getitem__` produces false positives on legitimate code.
So either these three spellings are *formally accepted* with that reasoning
stated in the guard's docstring, or a construction-closure approach is needed
that does not rely on pattern-matching. Do not simply re-widen the accessor
set — that is the change `main` deliberately reverted, and re-applying it would
reintroduce the false positives they measured.

Related: the still-open `2026-07-26-class-scoped-second-reader-bindings` asserts
that the shipped docstrings "now name both as measured, open residuals"; that
claim also rode `8688dcc` and does not hold against the shipped tree
(`grep "class-scoped\|PEP 562\|functools.partial" tests/load/test_settings.py`
returns nothing). That item needs the same correction.

## Resolution (2026-07-26 — SUPERSEDED, see above)

**Done 2026-07-26**, commit `8688dcc`, verified against the item's own
done-condition ("the guard's real perimeter and its docstring agree, verified
by running each of the four").

All four spellings were run as real, validating second `[load]` readers in
`src/fitdocs/audit.py` and reverted. Spellings (2) `dict.get(document, "load")`
and (3) `document.pop("load")` had only ever been *derived by reading* the
clause bodies, as this item noted; both were executed and both escaped as
predicted. Two independent reviewers reproduced all four.

**Closed, not accepted:**
- The default-parameter capture, by sweeping `__defaults__`/`__kwdefaults__`
  alongside module attributes. The item's stated reason for this escape was
  wrong: it said the reader "never becomes a module attribute". It does — the
  sweep patches it — but a def-time default binds the *original* at import,
  before any spy runs, so the read goes uncounted. Both facts were measured
  simultaneously.
- `document.__getitem__("load")`, found during review and closed by naming it
  in the literal-key walk's accessor set, where its `Subscript` twin
  `document["load"]` was already caught. `.pop` and `.setdefault` closed with it.

**Accepted, with the perimeter stated:** dict iteration, the unbound-method
form, and the aliased-key spelling. The item asked whether to widen the guard
or widen the acceptance; the answer is *both, split by whether closure
terminates*. Construction-closure — instrumenting the settings-document reader
and attributing reads by caller frame — is unavailable, because a module can
bypass that reader entirely with a direct `tomllib.load` of the settings path,
and `quarantine.py`, `athlete.py` and `load/profile.py` all call `tomllib.load`
legitimately, so no blanket rule works. Filed as
[[2026-07-26-load-table-read-bypasses-settings-reader]].

**Method note, the durable lesson.** Two rejection rounds were spent on the
same defect the item was opened to fix: a docstring asserting a perimeter the
guard does not have. Both times the claim took the form "a bounded, complete
enumeration" — of where a def-time binding can hide, and of the `Mapping`
methods taking a key at `args[0]` — and both were disproven by a shippable
second reader at a green suite, ruff and mypy clean (class-body bindings and
class-held `__defaults__`; `dict.__getitem__`). The framing originated in the
dispatching session's own brief, not the implementer's. A guard docstring must
describe the perimeter it *measured* and never assert enumerative completeness
over a language's binding forms or a protocol's method set. Remaining escapes
of that kind, including a PEP 562 module `__getattr__` attribute and a
`functools.partial` wrapper found in final review, are recorded in
[[2026-07-26-class-scoped-second-reader-bindings]].

