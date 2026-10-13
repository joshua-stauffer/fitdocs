---
id: 2026-10-13-boundary-guard-clock-and-network-lists-narrow
title: The clock spelling lists in the dashboards and compose guards omit time.strftime, ctime and asctime, and the packages' network lists omit ftplib, smtplib, xmlrpc, imaplib, asyncio and subprocess
status: open
importance: low
importance_why: Each omitted name is a way to read the clock or reach a network or subprocess from a package that promises neither; today only a repo-wide connectors allow-list catches three of the six network modules.
effort: S
kind: gap
area: dashboards, tests/dashboards/test_boundary.py, tests/compose/test_boundary.py, tests/connectors/test_boundary.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.4 reviewer)
pinned_at: 0a98d5c
resume_command: "do: add time.strftime, time.ctime and time.asctime to _CLOCK_SPELLINGS and ftplib, smtplib, xmlrpc, imaplib, asyncio and subprocess to the forbidden roots in tests/dashboards/test_boundary.py and tests/compose/test_boundary.py (update the literal-list tests), and widen tests/connectors/test_boundary.py _NETWORK_FORBIDDEN_PREFIXES with imaplib, asyncio and subprocess if the repo-wide rule should cover them [queue: .kiro/queue/2026-10-13-boundary-guard-clock-and-network-lists-narrow.md]"
context:
  - tests/dashboards/test_boundary.py
  - tests/compose/test_boundary.py
  - tests/connectors/test_boundary.py
  - .kiro/specs/dashboards/design.md
blocked_by:
  - dashboards
---

## What
The dashboards guard was modelled on the compose one, and both carry the same
short lists.

- **Clock.** `_CLOCK_SPELLINGS` (`tests/dashboards/test_boundary.py:134-144`,
  `tests/compose/test_boundary.py:117-127`) names `datetime.now`, `date.today`,
  `time.time`, `datetime.utcnow`, `datetime.today`, `time.monotonic`,
  `time.perf_counter`, `time.localtime` and `time.gmtime`. `time.strftime`,
  `time.ctime` and `time.asctime` read the clock when called with no argument
  and are absent from both lists.
- **Network and process.** The dashboards forbidden roots are `socket`,
  `urllib`, `http`, `ssl` (lines 113-131); compose forbids `urllib`, `socket`
  (lines 82-100). `ftplib`, `smtplib`, `xmlrpc`, `imaplib`, `asyncio` and
  `subprocess` are in neither. The repo-wide connectors rule
  (`tests/connectors/test_boundary.py:526-535`, `_NETWORK_FORBIDDEN_PREFIXES`)
  covers `socket`, `ssl`, `http`, `urllib.request`, `urllib.error`, `ftplib`,
  `smtplib` and `xmlrpc`, so it catches three of the six; `imaplib`, `asyncio`
  and `subprocess` are caught nowhere.

## Why it matters
Dashboards output must be byte-identical for identical inputs (Req 17.2) and the
package promises no clock and no network (design § Allowed Dependencies). The
guards are the only enforcement of both promises.

## Evidence
Probes at 0a98d5c against the dashboards guard (`engine` module):

```
import ftplib | smtplib | xmlrpc.client | imaplib | asyncio | subprocess   -> external=[]   (not flagged)
import socket                                                              -> external=['socket']
x = time.ctime()      -> clock=[] forbidden=[]
x = time.asctime()    -> clock=[] forbidden=[]
import time; x = time.strftime('%Y')  -> clock=[] forbidden=['time']   (caught only via the forbidden root)
import os; x = os.times()             -> clock=[] forbidden=[]
```

A correction to the reviewer's note: it said the compose clock guard "leaves
`time` unpinned". That does not hold as stated: `time` is in compose's
`_FORBIDDEN_TARGETS` (`tests/compose/test_boundary.py:98`), pinned by the case
at lines 323-324, and in dashboards' `_FORBIDDEN_ROOTS` pinned by
`test_the_forbidden_roots_are_the_literal_ones` (line 729 onward). What is
missing is the three spellings above and the six modules.

## How to pick it up
1. Add the three spellings to both `_CLOCK_SPELLINGS` tuples and to the literal-list tests (`test_the_clock_name_and_spelling_lists_are_the_literal_ones` in dashboards).
2. Add the six module roots to the forbidden roots of both guards and to the literal-roots tests; add a detection case for each.
3. Decide whether `tests/connectors/test_boundary.py` should also forbid `imaplib`, `asyncio` and `subprocess` repo-wide. `grep -rn "subprocess\|asyncio\|imaplib" src/fitdocs` finds no use at 0a98d5c, so a tree-wide rule would pass today; confirm that again before widening.
4. Consider a clock source the spellings cannot name, such as `os.times()`; decide whether that is worth a rule.

## Open questions
Whether `os.times()` and similar belong in the clock guard; the design says "never a clock" without enumerating.
