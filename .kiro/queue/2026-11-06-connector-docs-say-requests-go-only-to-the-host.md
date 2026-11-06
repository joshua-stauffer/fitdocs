---
id: 2026-11-06-connector-docs-say-requests-go-only-to-the-host
title: docs/connectors.md says connector requests go only to their host, but the transport follows redirects
status: open
importance: low
importance_why: The key is safe, since it is never sent to a redirect target; the gap is that a network statement is stricter than the code, and only shows if a service redirects.
effort: S
kind: inconsistency
area: connectors, docs/connectors.md, src/fitdocs/connectors/http.py
created: 2026-11-06
surfaced_by: website copy for the new connectors (draft PR 5)
pinned_at: f4bc152a
resume_command: "do: decide whether the connector transport should refuse redirects to another host or docs/connectors.md should state them, then make the code and page agree [queue: .kiro/queue/2026-11-06-connector-docs-say-requests-go-only-to-the-host.md]"
context:
  - docs/connectors.md
  - src/fitdocs/connectors/http.py
  - .kiro/specs/connectors/requirements.md
blocked_by: []
---

## What
`docs/connectors.md` says "Requests go to intervals.icu only" (line 194) and that a relay instance's requests "go only to the instance's `url`" (line 800). `urllib_transport` calls `urllib.request.urlopen` with the default opener (`src/fitdocs/connectors/http.py:174`), which follows redirects, so a service's redirect sends a second request to whatever host it names.

## Why it matters
The page is a statement of where a user's traffic goes. What the second request carries is limited: secret headers are added unredirected (`http.py:172`), so the key does not go, and line 196 of the page says so correctly. The address, the User-Agent and the other non-secret headers do go, and a POST answered with 301, 302 or 303 arrives as a GET without its body.

## Evidence
- The stdlib rule, printed from `urllib.request.HTTPRedirectHandler.redirect_request` on Python 3.11: it follows `code in (301, 302, 303, 307, 308) and m in ("GET", "HEAD") or code in (301, 302, 303) and m == "POST"`, and otherwise raises.
- This was read, not run against a redirecting server.
- Draft PR 5 describes this behaviour on the website's privacy page, so the site and `docs/` differ if it merges first.

## How to pick it up
1. Check whether any supported service redirects legitimately. A signed download link might.
2. Choose: state the redirect in `docs/connectors.md` in the same terms as the site, or add a redirect handler that refuses another host, which needs a connectors amendment if a real download depends on redirects.
3. Done when the page and the transport agree, with a transport test if the code changed.
