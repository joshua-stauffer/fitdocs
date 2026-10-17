---
title: Ownership contract
description: What fitdocs owns in your data root, what you own, and what each command may write. A short summary of the published, versioned contract.
section: Reference
order: 3
---

# Ownership contract

fitdocs writes into a folder that may also hold your own notes. The rules for who owns what are a **published, versioned contract** (currently version 4), not an informal habit. This page summarizes it. The [full contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) is the authoritative version.

## What fitdocs owns

fitdocs may create, rewrite, or delete these, and writes **nowhere else**:

| Path | Contents |
|---|---|
| `workouts/` and `workouts/assets/` | One page per activity, plus charts and maps |
| `history/` and `history/assets/` | The training-history page and its chart |
| `blocks/` | Block pages and planned-workout pages |
| `fit-archive/` | Your source `.fit` files, named by content hash and never modified |
| `.cache/` | Map tiles |
| `.fitdocs/` | fitdocs' own state, such as the quarantine record |

It also writes to the locations **your settings name**: the inbox folder and, if you opt in, `processed_dir`.

## What you own

- **`fitdocs.toml`**: fitdocs only reads it.
- **Your plan folder** (`plans/` by default): fitdocs only reads it.
- **`athlete.toml`**: shared. fitdocs adds values you confirm or that it derives, but never overwrites one you entered, and keeps every key it doesn't manage exactly as it was.
- **Everything else in the data root**: fitdocs never reads or writes it.

## Inside a generated page

| Region | Owner | On regeneration |
|---|---|---|
| `notes` | you | kept word for word |
| `workout` (strength pages) | you | kept word for word |
| `load` | fitdocs | kept; only replaced when you run `fitdocs load --recompute` |
| `effort`, `effort_distance_m`, `effort_time_s`, `effort_event` frontmatter keys | you | kept word for word |
| everything else | fitdocs | rebuilt |

Regions are marked with `<!-- fitdocs:begin:NAME -->` / `<!-- fitdocs:end:NAME -->`. Don't add markers of your own. A page with a marker fitdocs doesn't recognize is refused regeneration until the marker is removed. That way fitdocs never guesses about content it doesn't understand.

**No operation throws away your region or race-tag content.** It’s yours to do with as you’d like, and when you upgrade fitdocs versions and regenerate your wiki, it persists.

## How the rules are shown

- **`AGENTS.md`** in `workouts/`, `history/`, `blocks/`, and `fit-archive/`: the contract restated for people and LLM agents browsing the folder. Refreshed on every run.
- **A one-line notice** at the top of every generated page.
- **`fitdocs check`**: confirms the whole tree still matches.

All three are generated from the same source code, and a test keeps the published contract in sync with it.

## Versions

- The **contract version** changes whenever a guarantee changes: a new owned path, a new page type, or a new class of user-owned key. The changelog calls it out, along with what (if anything) you need to do.
- Each page's **`doc_version`** tracks its file format. When it changes, `fitdocs check` tells you and `fitdocs regen` updates your pages. If a page was written by a *newer* fitdocs than the one you have installed, fitdocs leaves it alone rather than downgrading it.

See the [compatibility policy](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/compatibility.md) for exactly what each version number promises.
