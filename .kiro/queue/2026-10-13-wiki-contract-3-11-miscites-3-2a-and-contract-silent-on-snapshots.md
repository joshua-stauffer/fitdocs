---
id: 2026-10-13-wiki-contract-3-11-miscites-3-2a-and-contract-silent-on-snapshots
title: Wiki-contract Req 3.11 says 3.2a carves out the tool-owned elements for dashboards, but 3.2a carves out only re-derivability and user-owned regions; and the published contract never says snapshots are the one non-re-derivable fitdocs-written file
status: open
importance: low
importance_why: A spec cross-reference that does not say what it cites, and a contract section (Commit Ordering and Re-Derivability) that stays silent about the one file fitdocs writes that cannot be rebuilt; neither changes behaviour, both mislead a reader.
effort: S
kind: docs
area: wiki-contract, dashboards, docs/ownership-contract.md, src/fitdocs/contract.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.1 reviewer)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-requirements wiki-contract [queue: .kiro/queue/2026-10-13-wiki-contract-3-11-miscites-3-2a-and-contract-silent-on-snapshots.md] correct Req 3.11's citation of 3.2a and state in the contract that snapshots are not re-derivable"
context:
  - .kiro/specs/wiki-contract/requirements.md
  - .kiro/specs/wiki-contract/design.md
  - docs/ownership-contract.md
  - src/fitdocs/contract.py
blocked_by:
  - dashboards
---

## What
Two small accuracy problems in the dashboards additions to the ownership
contract.

1. **Mis-citation.** Req 3.11 (added by Amendment 5) says the dashboards
   location is the inverse of the other declared directories: "the elements of
   3.2 that state the directory's contents are tool-owned, and re-derivable from
   other files, do not apply to it, as 3.2a carves them out for the archive."
   Req 3.2a carves out only "the re-derivability and user-owned-region elements
   of 3.2" for the source archive. The "written and tool-owned" element of 3.2
   is not carved out by 3.2a, so the sentence cites 3.2a for something it does
   not say.
2. **Silent contract.** The "Commit Ordering and Re-Derivability" section of the
   published contract says every workout document's generated content is
   re-derivable and says a dashboard run writes snapshots first, but never
   says that a snapshot is the one fitdocs-written file that cannot be rebuilt
   (it holds the rows at one moment).

## Why it matters
Anyone reconciling the declaration text with the requirements follows the 3.2a
citation and finds a different carve-out. Anyone deciding what is safe to delete
under `dashboards/assets/` learns from the contract that images are rebuilt but
reads nothing about snapshots in the section that is about exactly that.
`docs/dashboards.md` says it ("A snapshot is the only copy of the rows"), so the
two documents disagree by omission.

## Evidence
- `.kiro/specs/wiki-contract/requirements.md:322` (Req 3.11, "as 3.2a carves them out for the archive") against `:312` (3.2: "written and tool-owned ... additionally ... re-derivable by regeneration") and `:313` (3.2a: "The re-derivability and user-owned-region elements of 3.2 shall not apply to the source archive").
- `docs/ownership-contract.md:1085-1125`: the section never mentions snapshots; the dashboard paragraph at `:1104-1108` covers write order only. Snapshot rules appear elsewhere (`:205-210`, never modified or deleted).
- `docs/dashboards.md:632-635` says a snapshot is the only copy of its rows.

## How to pick it up
1. Amend Req 3.11 so it states its own carve-out ("do not apply to the dashboards location") instead of citing 3.2a, or add the missing words to 3.2a; keep the 3.2a text for the archive intact.
2. Add one sentence to the contract's re-derivability section: relative-chart regions and images are re-derivable from the pages and the index; snapshot files are not. The text lives in `src/fitdocs/contract.py` (the generated source of `docs/ownership-contract.md`; confirm which file is the source) and any golden that pins it.
3. If the contract text changes, check whether `CONTRACT_VERSION` needs advancing under the change protocol.

## Open questions
Whether a wording-only clarification of the contract advances `CONTRACT_VERSION`.
