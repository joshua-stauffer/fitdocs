# Requirements Document

## Project Description (Input)

fitdocs is about to be installed into markdown wikis it does not control, and
updated independently of the content those wikis hold. Today its ownership
contract is implicit in code: the region-marker grammar lives in one module,
the frontmatter schema and the `uuid`/`sources` identity are re-parsed in three
more, `doc_version` is a bare integer with no migration story, and nothing in
the generated tree tells a human — or an LLM agent maintaining the wiki — which
files fitdocs owns and which zones belong to the author. In an LLM-managed wiki
that last gap is acute: agents will happily "improve" generated documents
unless the boundary is declared where they read it.

This feature formalizes the contract rather than re-architecting it. One
document-contract definition becomes the single source of truth for the
frontmatter schema, document identity, and region ownership policy, and every
command that reads or rewrites documents uses it. A written, versioned
ownership contract is published in the documentation and restated inside the
directories fitdocs owns as an agent-instruction file that LLM agents will read
before editing. Generated documents carry a provenance stamp naming their
generator and pointing at that declaration. `doc_version` gains a defined
migration story — documents are re-derivable from the archive, so migration is
regeneration — plus drift detection and a refusal to downgrade documents
written by a newer fitdocs. The guarantee for user-added frontmatter keys stops
being accidental and becomes stated and enforced, and a read-only inspection
command lets a maintainer or an automation check the owned tree against the
current contract.

In scope: the single document-contract definition and the refactor of its
consumers; the published ownership contract; the emitted per-directory
ownership declaration; provenance stamping; document-format versioning, drift
detection and regenerate-as-migration; the frontmatter-key ownership contract;
the labeled overwrite/destructive semantics; the read-only inspection command.
Out of scope: user-configurable region sets or document templates; enforcement
beyond declaration (no filesystem-permission games); any change to the region
merge algorithm or marker grammar; ingestion/inbox configuration and plugin
discovery (sibling specs); packaging and release (sibling spec).

Full discovery context: `brief.md` in this directory.

## Introduction

wiki-contract turns fitdocs' implicit sole-writer arrangement into a published,
versioned, machine-legible contract. It changes almost nothing about what
fitdocs does and everything about what fitdocs *states*: that a fixed set of
paths under the data root is tool-owned and regenerated, that a fixed set of
document regions is user-owned and carried over verbatim, that the frontmatter
block belongs to the tool, that documents are always re-derivable from the
archived sources, and that no operation — including forced re-processing —
discards user-authored region content.

The contract is declared in three places at once so it cannot be missed: in the
project documentation, inside every directory fitdocs owns (as an
agent-instruction file that LLM wiki agents read before editing), and on each
generated document itself (as a provenance stamp). Behind those declarations,
one authoritative definition of the frontmatter schema, the document identity,
and the region ownership policy replaces the copies scattered across the sync,
load, and render paths, so that every command interprets a document the same
way. Document-format versioning gains the missing half of its story: drift is
detected and reported, regeneration is the migration, and a document written by
a newer fitdocs is left alone rather than silently downgraded.

## Boundary Context

- **In scope**: one authoritative interpretation of a workout document's
  frontmatter, identity, and region ownership, applied by every command that
  reads or rewrites documents; the published, versioned ownership contract and
  its version-control guidance; the ownership declaration emitted into each
  owned directory; the provenance stamp on generated documents; the
  document-format version, its drift detection, its regenerate-as-migration
  path, and its refusal to downgrade; the stated and enforced guarantee for
  frontmatter keys fitdocs does not manage; the stated limits of every
  overwriting operation; a read-only command that inspects the owned tree
  against the current contract.
- **Out of scope**: any change to the region marker grammar or the merge
  algorithm (declared as-is, not modified); user-configurable region sets,
  document templates, or renderers; preserving frontmatter keys fitdocs does
  not manage (the contract states they are not preserved); enforcing ownership
  by filesystem permissions, hooks, or version-control automation; writing
  version-control configuration files on the user's behalf; stamping a tool
  version or a generation timestamp into documents; in-place transformation of
  older documents (migration is regeneration); how `.fit` files arrive and how
  failing ones are quarantined (inbox spec); third-party extension discovery
  (plugin-api spec); packaging, release, and install mechanics (distribution
  spec); resolving the third party's licensing gate.
- **Adjacent expectations**: workout-docs owns document structure, the region
  mechanism, the archive, and the write pipeline — this feature republishes
  those behaviors as a contract and elevates its Requirement 10 (user-content
  preservation) from behavior to published guarantee, without changing them.
  training-load owns the content of the `load` region and its three frontmatter
  keys — this feature counts them among the managed keys and leaves their
  behavior untouched. route-maps contributed the document-scoped warning
  channel that this feature's new warnings ride on. fit-ingest supplies the
  recorded session identity that document identity is derived from. Apart from
  the provenance stamp and the document-format version bump required here,
  generated output for unchanged inputs stays byte-identical. inbox adds a
  third engine entry point and one configured intake location — this feature
  states the rules those must satisfy (declaration refresh on every writing
  entry point, confinement to owned plus configured locations, archive presence
  as the completed-file discriminator) but implements none of inbox's own
  behavior.

## Amendment 1 (2026-09-11): user-owned frontmatter keys, landed by effort-tags

`effort-tags` adds a second class of user-owned frontmatter key alongside the
user-owned regions this spec already names: the four keys of its effort tag
(`effort`, `effort_distance_m`, `effort_time_s`, `effort_event`), published in
code as `contract.USER_KEYS`. That spec owns the vocabulary, the validation,
and the typed reader; this spec owns only the frontmatter-key-ownership
contract it extends -- the publication of the class as disjoint from the
managed set, the byte-for-byte carry-forward and its placement, the
exclusion from the unmanaged-key warning and finding, and the declaration
text -- recorded here as Requirement 6 criteria 6.5-6.8. The published
contract's version identifier changes on account of it (`CONTRACT_VERSION`
`"1"` to `"2"`), because a stated guarantee -- what regeneration preserves in
the frontmatter block -- has changed; that version bump and its own document
are effort-tags' to make, not restated by this amendment. Nothing existing is
renumbered.

## Requirements

### Requirement 1: Consistent Document Interpretation Across Operations
**Objective:** As a user whose documents are read by several fitdocs operations,
I want every operation to interpret a document identically, so that a document
one command recognizes is never invisible to, or differently understood by,
another.

#### Acceptance Criteria
1. The fitdocs CLI shall interpret a document's frontmatter block, its document-type marker, its recorded activity identity, and its source history identically in every command that reads documents.
2. When a document's frontmatter is absent, unterminated, unparseable, or not a key-value mapping, the fitdocs CLI shall treat that document as not a fitdocs document in every command and shall continue the run without failing.
3. When a document is a fitdocs workout document, every command that needs its current source file shall resolve the same archived source from its source history.
4. The fitdocs CLI shall apply one region-ownership policy — the same region identifiers, the same owner for each region, and the same preserved set — in every command that reads or rewrites documents.
5. The fitdocs CLI shall produce, for unchanged inputs, document and asset output that differs from the previous release only by the provenance stamp required in Requirement 4 and the document-format version required in Requirement 5.
6. When the same inputs are rendered repeatedly, the fitdocs CLI shall continue to produce byte-identical output on every invocation.

### Requirement 2: Published Ownership Contract
**Objective:** As a person or agent maintaining a wiki that fitdocs writes into,
I want a written, versioned statement of what fitdocs owns and what I own, so
that I can rely on the boundary instead of inferring it from behavior.

#### Acceptance Criteria
1. The fitdocs documentation shall publish an ownership contract naming every path under the data root that fitdocs creates, writes, or deletes, and stating that fitdocs writes nowhere else.
2. The ownership contract shall name every user-owned region of a generated document and state that regeneration carries each region's content over verbatim.
3. The ownership contract shall state which parts of a generated document are replaced on regeneration and which are preserved.
4. The ownership contract shall state what happens to frontmatter keys fitdocs does not manage, and shall name the supported place for hand-authored content.
5. The ownership contract shall describe the effect of every fitdocs operation that overwrites existing content, including the forced re-processing option, and shall state that no fitdocs operation discards user-owned region content.
6. The ownership contract shall state that generated documents are re-derivable from the archived sources and the athlete profile alone, and that regeneration is the migration path when the document format changes.
7. The ownership contract shall state which files under the data root are user-owned and read-only to fitdocs, and which are shared files where fitdocs writes only its own keys and preserves the rest.
8. The ownership contract shall carry a version identifier that changes whenever the stated guarantees change.
9. The fitdocs documentation shall describe how to mark generated files as generated in a wiki kept under version control, and shall state that fitdocs does not write that configuration itself.
10. The ownership contract shall state that a location the user configures fitdocs to write into grants fitdocs the right to create and write within that location, that such locations are named in the user's settings file rather than fixed by the contract, and that fitdocs writes nowhere outside the contract's named owned paths and the locations the settings configure.

### Requirement 3: In-Tree Ownership Declaration
**Objective:** As an LLM agent maintaining a markdown wiki, I want the ownership
boundary declared inside the directories fitdocs owns, so that I read it where I
work and do not "improve" generated files.

#### Acceptance Criteria
1. When writing into the data root, the fitdocs CLI shall place an ownership declaration file, named by the conventional agent-instruction filename, in each top-level directory it owns.
2. The ownership declaration shall state that the directory's contents are written and tool-owned, identify fitdocs as the owner, carry the ownership contract's version identifier, and point to the published ownership contract. For a directory holding generated documents, it shall additionally name the user-owned regions and state that the directory's contents are re-derivable by regeneration.
2a. The re-derivability and user-owned-region elements of 3.2 shall not apply to the source archive, which holds primary, non-derived inputs; for that directory 3.3 governs instead. A declaration shall state no claim that is false of the directory it is placed in, and shall make no claim about generated documents in general that is not true of every generated document.
3. The ownership declaration for the source archive shall state that archived sources are immutable inputs that must not be edited, renamed, or deleted while documents reference them.
4. The ownership declaration shall be plain markdown that is readable without fitdocs installed and renders correctly in common markdown renderers.
5. When an ownership declaration fitdocs previously wrote is already present and its content matches what fitdocs would write, the fitdocs CLI shall leave the file untouched.
6. If a file with the declaration's name exists and does not carry fitdocs' provenance stamp, the fitdocs CLI shall leave that file unchanged, report that the declaration could not be placed, and complete the run.
7. The fitdocs CLI shall never treat an ownership declaration as a workout document in any document scan, identity match, regeneration, or training-load operation.
8. When a sync run discovers no new files and every ownership declaration is already current, the fitdocs CLI shall leave the data root unchanged.

### Requirement 4: Generated-Document Provenance
**Objective:** As a human or agent opening a workout document, I want the file
itself to say what produced it and where the editable boundary is, so that
ownership is obvious without consulting anything else.

#### Acceptance Criteria
1. The fitdocs CLI shall stamp every generated workout document with a machine-readable marker identifying fitdocs as its generator, distinguishable from a hand-authored document that merely looks similar.
2. The fitdocs CLI shall include in every generated workout document a human-readable provenance statement naming the tool, stating that content outside the marked regions is replaced on regeneration, and pointing to the in-tree ownership declaration.
3. The provenance statement shall not be visible in rendered markdown output while remaining plainly visible in the document's source text.
4. The fitdocs CLI shall place the provenance statement outside every preserved region, so that regeneration always refreshes it and a user can never accidentally own it.
5. The fitdocs CLI shall not include in the provenance stamp any value that varies between runs or between tool versions.

### Requirement 5: Document-Format Version and Migration
**Objective:** As a user upgrading fitdocs in a wiki already full of generated
documents, I want format drift detected and resolvable, so that an upgrade never
leaves me guessing whether my documents are current.

#### Acceptance Criteria
1. The fitdocs CLI shall record a document-format version in every generated workout document.
2. When the format of generated documents changes, the fitdocs CLI shall record a higher document-format version than the previous format used.
3. When the fitdocs CLI encounters an existing workout document whose recorded format version is older than the current one, it shall report that document as out of date and shall name regeneration as the action that brings it current.
4. When regenerating an out-of-date document, the fitdocs CLI shall rewrite it at the current format version while carrying its user-owned regions over verbatim.
5. If an existing workout document records a format version newer than the installed fitdocs produces, the fitdocs CLI shall leave that document unchanged, report it as written by a newer fitdocs, and continue the run rather than rewriting it at an older format.
6. The fitdocs CLI shall be able to bring every document to the current format version using only the archived sources and the athlete profile, without the original source directory.
7. If a workout document records no document-format version or an unusable one, the fitdocs CLI shall treat it as out of date rather than as newer.
8. When the fitdocs CLI leaves an existing document unchanged because it records a newer document-format version, it shall leave the corresponding source unarchived and shall not record that source as processed, so that a later run retries it.
9. The fitdocs CLI shall make the presence of a source in the archive — and not any report label such as "skipped" — the authoritative record that the source has been fully processed, so that any downstream policy acting on processed files uses archive presence as its discriminator.

### Requirement 6: Frontmatter Key Ownership
**Objective:** As a user who adds keys to my documents' frontmatter, I want to
know exactly what happens to keys fitdocs does not manage, so that I never lose
data silently.

#### Acceptance Criteria
1. The fitdocs CLI shall treat the frontmatter block of a generated workout document as tool-owned and shall rewrite it in full whenever it regenerates the document.
2. The fitdocs CLI shall publish the complete set of frontmatter keys it manages, including the keys written by the training-load pass.
3. If regenerating a document would drop frontmatter keys that fitdocs does not manage, the fitdocs CLI shall report the affected document and the dropped key names as a warning and shall complete the run successfully.
4. The fitdocs CLI shall continue to preserve unknown keys and sections in the user-editable configuration and athlete-profile files under the data root, and shall state that guarantee in the ownership contract.
5. _(added by Amendment 1)_ The fitdocs CLI shall publish the complete set of user-owned frontmatter keys as a class distinct from, and disjoint with, the managed key set (6.2), and shall never write a user-owned key into a document.
6. _(added by Amendment 1)_ The fitdocs CLI shall carry every user-owned key's frontmatter line, including any continuation lines its value spans, byte-for-byte through every operation that rewrites the document. When the fitdocs CLI rebuilds a document's frontmatter block in full, it shall place the carried lines after every managed key and before the closing fence, in the order they appeared in the document being regenerated, and this placement shall be stated as part of the published contract.
7. _(added by Amendment 1)_ A user-owned key shall be excluded from the unmanaged-key warning (6.3) and from the unmanaged-key finding (8.4); a user-owned key carrying a malformed value shall instead be reported as a finding of its own kind, distinct from the unmanaged-key finding, naming the affected document and the offending key.
8. _(added by Amendment 1)_ The ownership declaration placed in the generated-documents directory shall name the user-owned frontmatter keys and shall state that fitdocs never writes them and carries them through regeneration.

### Requirement 7: Regeneration and Overwrite Guarantees
**Objective:** As a user whose documents fitdocs rewrites, I want the destructive
limits of every operation stated and enforced by tests, so that regeneration is
never a risk to what I wrote.

#### Acceptance Criteria
1. When regenerating an existing document, the fitdocs CLI shall carry every user-owned region's content over verbatim and shall replace all content outside those regions.
2. If an existing document's region markers are damaged, or if it holds a region the fresh render does not, the fitdocs CLI shall leave that document unchanged and report a per-document error.
3. While forced re-processing is in effect, the fitdocs CLI shall still carry user-owned regions over verbatim.
4. The fitdocs CLI shall provide no operation that discards user-owned region content.
5. The fitdocs CLI shall create, modify, and delete files only within the paths the ownership contract names as fitdocs-owned, together with the locations the user's settings explicitly configure fitdocs to write into.
6. Every fitdocs entry point that writes into the data root shall observe the same confinement, so that adding a new writing entry point does not widen the owned path set.

### Requirement 8: Contract Inspection
**Objective:** As a wiki maintainer or an automation acting on my behalf, I want
a read-only command that reports whether the owned tree matches the current
contract, so that I can check health and gate further action without writing
anything.

#### Acceptance Criteria
1. The fitdocs CLI shall provide a command that inspects the resolved data root and creates, modifies, or deletes nothing.
2. The inspection shall report each workout document whose recorded format version differs from the current one, distinguishing out-of-date documents from documents written by a newer fitdocs.
3. The inspection shall report each workout document whose region markers are damaged.
4. The inspection shall report each workout document carrying frontmatter keys fitdocs does not manage.
5. The inspection shall report each owned directory whose ownership declaration is missing, out of date, or occupied by a file fitdocs did not write.
6. The inspection shall name, for each finding, the affected path and the action that resolves it.
7. When the inspection finds nothing to report, the fitdocs CLI shall exit with the success status; when it reports findings, it shall exit with the existing per-document failure status; when the data root cannot be resolved, it shall exit with the existing configuration-error status.
8. The inspection shall complete without network access and without reading any `.fit` source file.
