---
id: 2026-10-17-website-runbook-annotations-and-dns-proxy
title: docs/website.md runbook still says annotation blocks may stay, and says nothing about proxied DNS records
status: open
importance: low
importance_why: The next import or page edit following the runbook would put iA Writer authorship data back into the public repo against the maintainer's decision.
effort: S
kind: docs
area: docs-site, docs/website.md (Maintainer runbook), tests/sitebuild/test_website_doc.py
created: 2026-10-17
surfaced_by: site-publish session (fitdocs.ai content import and Pages/Cloudflare setup)
pinned_at: 399fe7f
resume_command: "do: Amend docs/website.md Maintainer runbook step 5 to say pages are committed without iA Writer annotation blocks (maintainer decision 2026-10-17), and step 3 to say records at a proxying DNS host (Cloudflare) must be DNS-only; decide whether the build or check_site should refuse an annotation block under website/content/; update any pinned sentences in tests/sitebuild/test_website_doc.py"
context:
  - docs/website.md
  - scripts/sitebuild/content.py
  - scripts/sitebuild/model.py
  - tests/sitebuild/test_website_doc.py
blocked_by: []
---

## What
On 2026-10-17 the maintainer had the iA Writer annotation blocks removed
from `website/content/` and `main` rewritten so they are not at the tip
(5a367cc → 399fe7f). The runbook still invites them, and nothing refuses
them: the build strips a block silently (`strip_annotation`,
`scripts/sitebuild/content.py`), so a re-added block publishes nothing but
lands in the public repo.

The DNS step names "the domain's DNS host" generically. `fitdocs.ai` is on
Cloudflare, whose records can be proxied; a proxied apex resolves to
Cloudflare addresses, not GitHub's, so GitHub's DNS check and certificate
issuance depend on the records being DNS-only.

## Why it matters
Following the runbook as written undoes a maintainer decision about public
authorship data.

## Evidence
- `docs/website.md:289`: "The annotation blocks may stay when the files use
  LF line endings ..."
- `docs/website.md:262`: "At the domain's DNS host, point the apex ..." with
  no mention of proxying.
- `git grep -c "Annotations:" 399fe7f -- website/content` prints nothing (0
  blocks at the tip).
- `dig +short NS fitdocs.ai` → `dana.ns.cloudflare.com.`, `jim.ns.cloudflare.com.`

## How to pick it up
Edit the two runbook steps, run `FITDOCS_REQUIRE_SITE_TOOLING=1 uv run
--group docs pytest tests/sitebuild` for pinned sentences. Optionally add a
refusal for an annotation block under the default content directory only
(the out-of-repo preview of an iA Writer library must keep working).

## Open questions
Whether to enforce (refuse in `check_site` / the build for `website/content`)
or only document.
