# Compatibility policy

This page states what fitdocs' version number promises, contract by contract.
It is the single statement the [readme](../README.md), the
[plugin-author documentation](plugins.md), and the contribution guide all
point at rather than each forming its own notion of "public" or "stable."

## The governed contracts

Version numbering governs exactly three contracts, plus one named schema:

1. **The generated-document and ownership contract** — the frontmatter a
   workout document carries, the managed keys and region-ownership policy,
   and the document-format version that decides whether an existing document
   still matches what the installed tool would write.
2. **The inbox interface** — the `[inbox]` table's meaning, the
   never-delete disposition guarantee (a file is left in place by default,
   and moved out of the inbox only when the user opts in — never deleted),
   and the channels a drain reports.
3. **The load-calculator plugin API** — the calculator contract a third-party
   calculator implements, the entry-point discovery group, and the
   documented public import surface a calculator author may depend on.
4. **The user-facing settings schema** — `<data-root>/fitdocs.toml`, with its
   six tables today: `[tiles]`, `[inbox]`, `[plugins]`, `[load]` (and its
   sub-tables), `[plans]`, and `[history]` (see
   [Breaking, additive and internal](#breaking-additive-and-internal) below).

**Documented means public.** A name, key, or behavior described on this page,
in [`docs/plugins.md`](plugins.md), or in the ownership-contract and inbox
documentation is the contract. Everything else — including anything
undocumented or underscore-prefixed — is internal and may change in any
release, including a patch.

## Breaking, additive and internal

**The document and ownership contract.** Breaking: a change to a managed
frontmatter key's name or meaning, a change to the region-ownership policy
that changes which prose an existing document owns, or a document-format
version bump that is not restorable by regeneration. Additive: a new managed
key with a behavior-preserving default, or a new document-format version that
regeneration alone resolves. Internal: how a document is rendered internally,
its file layout on disk beyond the paths the ownership contract names, and
any helper module that reads or writes a document without being named here.

**The inbox interface.** Breaking: a change to a `[inbox]` key's meaning, a
narrower disposition guarantee (for example, treating a file the drain
previously moved as one it may now delete), or the removal or rename of a
reported channel. Additive: a new optional `[inbox]` key with a
behavior-preserving default, or a new reported channel that a caller who
ignores unknown channels can safely skip. Internal: the drain's internal
scheduling, its filesystem staging strategy, and any module that implements
the drain without being part of the documented `[inbox]` interface.

**The plugin API.** Breaking: a change to the calculator contract's required
members, a change to the entry-point discovery group's name, or the removal
or rename of a documented public name from `fitdocs` or `fitdocs.load`.
Additive: a new optional calculator-contract member with a
behavior-preserving default, or a new documented public name. Internal:
everything not enumerated in [the plugin API's public import
surface](plugins.md#the-public-import-surface) — including the
`fitdocs.plugins` module itself, which performs discovery but is not public
surface.

**The settings schema, including `[tiles]`.** One file, six tables today —
`[tiles]`, `[inbox]`, `[plugins]`, `[load]` (and its sub-tables), `[plans]`,
and `[history]` — all user-written and all documented; a table added by a
later feature joins this list the same way. The tile table is governed
exactly like the others, never left as an ungoverned user-facing schema.
Breaking: removing a key, narrowing an accepted value, or changing a default
in a way that changes behavior for an unchanged file. Additive: a new
optional key with a behavior-preserving default, or an entirely new table.
Internal: how the file is parsed — the shared loader and its single
file-level error type — regardless of which table a change touches.

## Version numbering

**Before the first stable release (`0.x`)**, the minor version position
carries breaking changes while the major position holds at zero — the
widespread pre-`1.0` convention: `0.4.0 -> 0.5.0` may break any governed
contract, while `0.4.0 -> 0.4.1` may not.

**From the first stable release (`1.0`) onward**, fitdocs follows full
semantic versioning: a breaking change to any governed contract requires a
major version bump, an additive change requires a minor bump, and a fix that
changes no governed contract is a patch.

## Internal versions and what they cost you

Two internal version identifiers exist independently of the released version
number, plus one schema with no identifier of its own, and each maps onto a
release differently:

- A **document-format version** (`DOC_VERSION`, scoped to `workouts/*.md`
  documents specifically — the training-history page, block pages, and
  planned-workout pages carry their own separate `history_version` /
  `block_version` / `planned_version` keys and need no regeneration step at
  all) bump is a compatible change. It costs the user one `fitdocs regen` to
  bring existing workout documents current; nothing else is required. See
  the ownership contract's own "Document-Format Versions and Migration"
  material for the regeneration story in detail.
- An **ownership-contract version** (`CONTRACT_VERSION`) bump is a compatible
  change. It costs the user nothing.
- A **settings-schema change that invalidates an existing `fitdocs.toml`**
  has no internal version identifier of its own, but is still a breaking
  change under the definitions above, and is treated as one in the released
  version number regardless of how small the edit looks.
- **Removing the built-in calculator from a release, or adding one, is a
  contract change by definition** — it is recorded in the changelog together
  with the action the user must take (for example, naming a replacement
  calculator to configure).

## Deprecation

A deprecated part of a governed contract is announced in the changelog and,
where the tool can surface it, in its own output at the point of use. It is
kept functioning for **at least two minor releases** after the release that
announces the deprecation, and is never removed in a patch release —
removal happens only at a minor release (pre-`1.0`) or major release
(post-`1.0`) boundary, after the notice period has elapsed.

## The compatible-upgrade guarantee

While a user's settings file, athlete profile, and local plugins are
unchanged, upgrading within the range this policy calls compatible requires
no edit to any of them: the settings file needs no key added or removed, the
athlete profile needs no re-entry, and a local plugin file needs no code
change to keep working.

## Public versus internal

fitdocs has exactly one public-versus-internal statement, and this is it.
The authority for the public *import* surface is
[`docs/plugins.md`'s enumeration](plugins.md#the-public-import-surface) —
every name from `fitdocs` and every name from `fitdocs.load` a calculator
author may depend on, name by name. This page does not restate that list;
`tests/test_public_api.py` pins it inside the repository so a change is
always deliberate and visible in the diff.

Everything else is internal and may change in any release, regardless of
where it is imported from. By name, the following modules are internal:

- `fitdocs.contract`
- `fitdocs.inbox`
- `fitdocs.plugins`
- `fitdocs.version`
- `fitdocs.agentskill`
- `fitdocs.layout`
- `fitdocs.settings`

The bundled calculator class, `ThresholdCalculator`
(`fitdocs.load.threshold.calculator`), is not public either — a calculator
author looks it up through `available()` or `get("threshold")`, never by
importing the class.

## Which commands need a data root

The project-wide rule: **a command that describes a tree requires a data
root; a command that describes the installed tool does not.** Three commands
are the current instances of this rule:

- `fitdocs skill [NAME]` describes the installed tool. It resolves no data
  root and exits `0` without a data root (an unknown `NAME` is still a
  configuration error and exits `2`, independent of any data root).
- `fitdocs plugins` describes the installed tool. It degrades gracefully
  without a data root — listing built-in and packaged calculators only — and
  exits `0`.
- `fitdocs check` describes a tree. An unresolvable data root is a
  configuration error for it, and it exits `2`.

`fitdocs.cli`'s module docstring carries this same rule in code, so a new
command's author meets it where the command is written rather than
discovering it here after the fact.
