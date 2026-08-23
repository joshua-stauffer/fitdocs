---
id: 2026-08-23-sync-emits-nothing-until-the-run-ends
title: A large `fitdocs sync` prints nothing until it finishes, so a slow run and a hung run look identical for hours
status: open
importance: medium
importance_why: An operator draining a real-sized inbox has no signal for the whole run; the only way to tell progress from a hang is to stat the output directory by hand.
effort: S
kind: gap
area: inbox, src/fitdocs/cli.py
created: 2026-08-23
surfaced_by: full-archive demo rebuild of 2478 real .fit files into ~/code/fitdocs-demo
pinned_at: 87ce085
resume_command: "/kiro-spec-requirements inbox [queue: .kiro/queue/2026-08-23-sync-emits-nothing-until-the-run-ends.md] Emit incremental progress during a long inbox drain instead of only an end-of-run summary"
context:
  - .kiro/specs/inbox/requirements.md
  - .kiro/specs/inbox/design.md
  - src/fitdocs/cli.py
blocked_by: []
---

## What

`sync` reports only at the end. `_print_sync_summary` (`src/fitdocs/cli.py:708`)
and the drain summary (`:756`) run after every file has been processed; nothing
in the per-file pipeline emits a line as it goes. The module docstring states
the intended behaviour plainly at `src/fitdocs/cli.py:26`: "``sync``/``regen``
end with a summary". No `rich.progress` bar exists anywhere in the package.

At the scale the tool was previously exercised — the demo's 74-file inbox —
this is invisible, because the run finishes in well under a minute. At real
archive scale it means hours of total silence.

## Why it matters

A drain of a real personal archive runs for tens of minutes (measured: 2478
files in 27:58 wall clock, ~1.5 documents/second). For that entire window the
operator cannot distinguish a working run from a wedged one — a stalled network
fetch, an `.fit` file the parser is spinning on, or a completed run whose shell
died. The only available signal is manually counting files in `wiki/workouts/`,
which is what this session had to do, repeatedly, for 28 minutes.

This also weakens the quarantine story: a file that fails is reported only in
the final summary, so an operator who kills a seemingly-hung run loses the
report for everything already processed.

## Evidence

Code, `src/fitdocs/cli.py`:

```
26:dates read in the user's own zone. ``sync``/``regen`` end with a summary of
708:    """Print the end-of-run summary: a counts table plus the per-file detail (1.4).
756:    """Print the drain summary: the inbox path, an extended counts table, and
```

No progress UI is available to use:

```
$ grep -rn "rich.progress\|Progress(" src/fitdocs
(no matches)
```

Observed 2026-08-23, `~/code/fitdocs-demo`, `fitdocs sync inbox --no-prompt`
over 2478 files with stdout redirected to a file. Seven minutes in, with 1220+
documents already written to `wiki/workouts/`, the redirected log was still
empty — and stayed empty until the run ended at 27:58, when the whole summary
appeared at once:

```
$ wc -c < sync.log
       0
```

Caveat, stated rather than assumed: this run was **non-interactive** (stdout
redirected), so it does not by itself prove a TTY run is equally silent. The
code above shows the summary printers are end-of-run in both cases, but the
TTY path was not exercised in this session.

## How to pick it up

1. Read `.kiro/specs/inbox/requirements.md` for what the drain is required to
   report, and whether "report" is specified as end-of-run by intent.
2. Read `src/fitdocs/cli.py:208` (`sync_command`) and the two summary printers
   at 708 and 756 — the question is whether a per-file callback belongs in the
   engine's seam or only in the CLI's rendering.
3. Decide the shape: a `rich.progress` bar for a TTY, and — the part that
   matters for this evidence — a plain periodic line for a redirected stream,
   since a progress bar writes nothing useful to a log file.
4. Done looks like: a redirected two-hour drain writes something legible while
   it runs, and killing it mid-run still leaves a record of what was processed.

## Open questions

- Should partial results be summarised on SIGINT, or is that a separate item?
  This item covers visibility during the run, not crash-safety of the report.
