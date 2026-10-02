---
id: 2026-10-02-connectors-boundary-and-neutrality-guard-gaps
title: Three connectors guards are narrower than the rules they enforce -- no guard for "only cli imports fitdocs.connectors", a short network-module list, and a URL-only neutral scan -- and the folder unit tests never assert that no request was sent
status: open
importance: medium
importance_why: Items 1-3 are what keep network access, service names and the connectors package confined as intervals-connector (the first network connector) lands; each gap is a route a later change can take with the suite green.
effort: S
kind: gap
area: connectors, tests/connectors/test_boundary.py, tests/connectors/test_docs.py, tests/connectors/test_folder.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-connectors-boundary-and-neutrality-guard-gaps.md] Add the cli-only-importer guard, widen the network list, make NeutralScan see bare host constants, and assert the folder connector sends no request"
context:
  - tests/connectors/test_boundary.py
  - tests/connectors/test_docs.py
  - tests/connectors/test_folder.py
  - tests/test_confinement.py
  - src/fitdocs/connectors/folder.py
  - .kiro/specs/connectors/design.md
  - .kiro/specs/connectors/requirements.md
  - .kiro/queue/2026-09-12-import-guards-scope-gaps.md
  - .kiro/queue/2026-09-30-repo-wide-no-stryd-address-guard.md
blocked_by: []
---

## What
1. **"Only `fitdocs.cli` imports the package" has no guard.** design.md:120
   states "`fitdocs.cli` imports the package; nothing else in `src/` does."
   `tests/connectors/test_boundary.py` guards what the package imports
   (layers 1-2, `:374-500`) and the tree-wide network allow-list (layer 3,
   `:505-668`), but no test scans `src/fitdocs/` for importers *of*
   `fitdocs.connectors` (the repo has this shape elsewhere, e.g.
   `tests/plans/test_boundary.py:2792`
   `test_exactly_the_registered_contract_importers_import_fitdocs_contract`).
2. **Layer 3's network list is short.** `_NETWORK_FORBIDDEN_PREFIXES`
   (`test_boundary.py:517-526`) is `socket, ssl, http, urllib.request,
   urllib.error, ftplib, smtplib, xmlrpc` -- exactly design.md:1543-1546.
   `asyncio` (open_connection), `socketserver`, `imaplib`, `poplib`,
   `webbrowser`, and any third-party HTTP client (`requests`, `httpx`,
   `aiohttp`) pass outside the two allowed modules.
3. **NeutralScan sees only URLs.** `_URL_PATTERN = re.compile(r"https?://...")`
   (`tests/connectors/test_docs.py:609`) finds scheme-prefixed URLs only; a
   bare host constant such as `_API_HOST = "api.vendor.net"` escapes Req
   14.6's service-neutrality scan.
4. **Folder unit tests never assert "no request" (Req 13.9).**
   `tests/connectors/test_folder.py:68-80` builds every session over
   `FakeTransport([])`; an unexpected request raises inside the connector,
   and a connector that swallows it still passes those tests. One
   end-to-end check exists: `tests/test_confinement.py:978`
   (`assert calls == []`, transport wrapper at `:880-893`) covers the single
   pull scenario the confinement guard stages. No folder unit test asserts
   `transport.requests == []` (that appears only in
   `tests/connectors/test_registry.py:921,1076`, for the scripted puller), so
   folder paths outside that one scenario (deferrals, `--since`, a missing
   source) are unguarded.

The dynamic-import route past layer 3 (`importlib.import_module("socket")`,
`__import__`) is the same class as
`2026-09-12-import-guards-scope-gaps` and is recorded there.

## Why it matters
intervals-connector will add the first real network connector, its host
constant, and new CLI wiring. Item 1 is what stops another module from
calling connector code directly; 2 and 3 are what keep network access and
service names confined; 4 widens the evidence that the shipped `folder`
connector is offline beyond the one scenario the confinement guard stages.

## Evidence
- Lines above read at `ad985b3`; `grep -rn "fitdocs.connectors" tests/connectors/test_boundary.py`
  shows no importer scan. The rule holds today: outside the package, only
  `src/fitdocs/cli.py` imports it (other hits of `fitdocs.connectors` in
  `sync.py`, `tiles.py`, `layout.py`, `contract.py`, `version.py` are
  docstrings/comments).
- Mutation T1 (folder connector issues a request and swallows the
  `FakeTransport` error) was reported green on the full suite by the task 6.3
  reviewer subagent; not re-run in this session, and
  `tests/test_confinement.py:978` now catches at least an unconditional
  request in the staged pull, so T1 may have been conditional or may predate
  that assertion -- re-run it before relying on this point. Items 1-3 were reported by
  the task 6.1 and task 7 reviewer subagents; the guard code was re-read here.

## How to pick it up
1. Read `test_boundary.py` (layers and their positive/negative controls) and
   `test_docs.py`'s NeutralScan section (`:601-700`).
2. Add a layer that walks `src/fitdocs/**/*.py` outside
   `fitdocs/connectors/` and asserts the set of modules importing
   `fitdocs.connectors*` equals `{"fitdocs/cli.py"}`, with a synthetic
   positive control.
3. Extend the network prefixes with the modules above (update design.md:1543
   in the same change) and add a "no non-stdlib top-level import outside an
   allow-list" check for third-party clients.
4. Give NeutralScan a second pattern for dotted host literals inside string
   constants (allow-list the project's own hosts and `example`/`invalid`
   test domains); coordinate with the Stryd-address item listed in context.
5. In `test_folder.py`, keep the `FakeTransport` and assert
   `transport.requests == []` after every pull scenario (or once in a shared
   fixture teardown).
6. Done when each new check has a synthetic positive control that goes red
   and the real tree is clean.
