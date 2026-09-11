<!-- fitdocs:generated: this file is maintained by fitdocs and rewritten whenever its content differs from what fitdocs would write -->
# AGENTS.md -- Generated Workout Documents

The contents of `workouts/` are written and tool-owned by fitdocs.

This directory holds generated workout documents; the user-owned regions are `notes` and `workout`. The region markers actually present in a document are authoritative for which of them it reserves -- check the document itself rather than assuming.

The frontmatter keys `effort`, `effort_distance_m`, `effort_time_s`, and `effort_event` are user-owned: fitdocs never writes them and carries them unchanged through regeneration. The rest of the frontmatter block is tool-owned and rebuilt on regeneration.

The *generated* content of the documents in this directory is re-derivable: fitdocs rebuilds it by regeneration from the archived sources under `fit-archive/`, the athlete profile, the configured timezone, and the tile source. Content inside a document's region markers is not re-derived by regeneration -- it is carried over from the document itself, so regenerating a deleted document brings back only the generated content, not what its regions held.

Never add a region marker to a document that does not already have one: doing so makes the next regeneration refuse to write that document until the added marker is removed by hand.

## Ownership

Owner: `fitdocs`.
Ownership contract version: `3`.
Published ownership contract: https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md
