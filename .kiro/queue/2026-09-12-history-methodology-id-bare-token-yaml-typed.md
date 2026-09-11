---
id: 2026-09-12-history-methodology-id-bare-token-yaml-typed
title: The history page's bare-token rule admits methodology ids YAML reads back as non-strings
status: open
importance: medium
importance_why: A plugin calculator id like "1991", "true", "null" or "2024-01-01" is emitted bare and parses back as int/bool/None/date, breaking the frontmatter's round-trip type guarantee (Req 5.8) for a value the athlete never typed.
effort: S
kind: bug
area: load-history, src/fitdocs/history/page.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 4.2 (reviewer round 1)
pinned_at: 8cd0062
resume_command: "do: change page._IDENTIFIER_PATTERN (design.md ~1219-1221) to quote unless the token starts with a letter and is not a YAML 1.1 bool/null word -- or quote always -- add round-trip tests for '1991', 'true', 'null', '2024-01-01', '0x1F', '1_000', and amend the design rule"
context:
  - src/fitdocs/history/page.py
  - tests/history/test_page.py
  - .kiro/specs/load-history/design.md
blocked_by: []
---

## What
design.md fixes the regex `[A-Za-z0-9_.-]+` for "plain token" identifiers;
the implementer followed it. `contract.parse_frontmatter` (PyYAML) reads
`methodology: 1991` as `int`, `true` as `bool`, `null` as `None`,
`2023-01-05` as `date`, `0x1F` as 31, `1_000` as 1000. Calculator ids are
unconstrained (`load/registry.py`, `load/settings.py`) and plugin-writable.

## Evidence
4.2 review round 1, finding A: each token above probed through
`contract.parse_frontmatter` on an emitted block.

## How to pick it up
Read `page.py::_format_identifier` and the 4.2 tests. Tighten the rule,
pin the six tokens by round-trip type, amend design.md's quoting rule.
