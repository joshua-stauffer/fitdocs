---
id: 2026-10-19-site-llm-isms-outside-the-0-2-diff
title: fitdocs.ai pages carry stock phrasing ("LLM-isms") on lines the 0.2 site-copy PR does not touch
status: open
importance: low
importance_why: Distracting to an engaged reader, and the maintainer asked for it; nothing is wrong factually, so it waits for the full-site pass.
effort: M
kind: docs
area: docs-site, website/content/
created: 2026-10-19
surfaced_by: maintainer review of PR #1 (docs(website) update fitdocs.ai for 0.2), LLM-ism sweep scoped to the PR diff first
pinned_at: 309625c
resume_command: "do: re-run the LLM-ism review over website/content/ on a chore branch, starting from the findings listed in .kiro/queue/2026-10-19-site-llm-isms-outside-the-0-2-diff.md; propose a rewrite with a GitHub permalink for each to the maintainer before editing, then validate with uv run --group docs python -m scripts.build_site build"
context:
  - website/content/
  - website/content/llm/index.md
  - website/content/index.md
  - .kiro/queue/2026-10-19-site-maintainer-prose-nits.md
blocked_by: []
---

## What
The maintainer defined an "LLM-ism" as a turn of phrase highly likely in
LLM-generated text, and more broadly any trope that distracts an engaged
reader; their example was "and nowhere else" in
`guides/privacy-and-network.md`. A four-reviewer sweep of every page under
`website/content/` found 140 such phrases at `309625c` (PR #1's head,
branch `chore/site-copy-0-2`). The 60 on lines that PR adds or edits are
proposed in the PR review. The 80 below sit on lines the PR does not touch,
and the maintainer chose to do them in a later pass.

Patterns, most frequent first: a guarantee stated twice back to back ("only
reads. It never writes"); decorative absolutes ("exactly", "at all", "only
ever", "nowhere else", "and no other way"); bold slogan sentences;
reassurance or payoff tags ("That's it", "is all it takes", "it persists");
filler ("just", "simply", "for you"); stock idioms and hook openers ("only as
accurate as", "sounding board", "go off the rails", "half the story");
marketing intensifiers on the home page ("AI-native", "powerful",
"lightning-fast").

## Why it matters
Each one is small, but together they give the site a generated voice and
make readers skim past the guarantees that matter (ownership, never
deleting, the network). `llm/index.md` and `index.md` hold about a third of
the findings, and both are the maintainer's own prose.

## Evidence
Line numbers are at `309625c`. Each quote was matched verbatim on its line
then; re-find each quote by text, because the PR's merge will shift lines.

- `website/content/extend/load-calculators.md`: L10 “A running system, a cycling model, a strength-training load:”; L10 “and there's room for more than one answer”; L12 “## The contract, in one screen”; L51 “Nothing could be computed, and here's why.”; L55 “## The rules that matter”; L61 “if the check actually ran”; L80 “Installing the package is all it takes.”; L107 “A broken plugin is always a warning, never a failed run.”; L119 “Built a calculator? Open an issue”
- `website/content/faq.md`: L32 “No plugin needed.”
- `website/content/getting-started/install.md`: L31 “No config file, no profile, no data folder.”; L33 “Hand it to your LLM.”; L49 “exactly as they are”
- `website/content/guides/benchmarks.md`: L10 “The best way to know what kind of shape you’re in is to race!”; L38 “Here's what fitdocs derives, from which efforts:”
- `website/content/guides/history.md`: L35 “A fitness curve is only as accurate as the underlying data points.”
- `website/content/guides/inbox.md`: L61 “stays exactly where it is”
- `website/content/guides/privacy-and-network.md`: L10 “it can be run entirely offline, which makes it simple to use in sandboxed environments.”; L35 “No run fails because a map couldn't be drawn.”; L58 “**No account, no telemetry, no update checks.** fitdocs doesn't phone home.”; L61 “which could be a model running on your own machine.”; L62 “Nothing is published anywhere.”
- `website/content/guides/training-blocks.md`: L13 “LLMs make it easy to learn fast, but they don’t replace your judgement.”; L13 “The agent **asks you** for the goal”; L21 “fitdocs only reads this folder. It never writes, renames, or deletes anything there.”; L22 “so each planned session has its own page before you've done it”; L35 “If a better match is logged later, it simply takes over.”; L35 “Nothing is ever written back into your workout pages or your plan file.”; L89 “The plan file becomes a history of how the plan changed.”
- `website/content/guides/training-load.md`: L10 “and shows its work on every page”; L14 “adds up to one meaningful total”; L16 “## Three channels, one pick”; L82 “leads to confidently wrong decisions”
- `website/content/guides/wiki-integration.md`: L10 “You can link to them, search them, and query them together”; L10 “and everything else you think about”; L12 “## How it stays out of your way”; L42 “if you want no network access at all”; L56 “so they always match the version you have installed”; L94 “a short pointer is enough. You don't need to copy the rules:”
- `website/content/guides/workout-pages.md`: L14 “Here's what's in a run or ride page, top to bottom.”; L51 “the notes section is always stable”; L63 “It's the quickest way to see whether”; L81 “so a computed load isn't lost when pages are rebuilt”; L95 “## Editing rules, in one place”
- `website/content/index.md`: L8 “AI-native”; L11 “in the format that LLMs read best”; L19 “includes a powerful analytics database for immediate insight”; L19 “lightning-fast”; L19 “powerful resources”; L22 “They aren't a reliable calculator.”
- `website/content/llm/index.md`: L3 “You plan, fitdocs runs the numbers, and the model makes the connections.”; L9 “makes it easy for LLMs”; L9 “opens up new possibilities”; L13 “LLMs are great at explaining concepts in a way that works for you.”; L13 “LLMs make it easy to learn fast.”; L13 “the pattern you’d never have spotted in a spreadsheet”; L15 “Fitdocs closes the feedback loop;”; L15 “is only yours”; L18 “Here are some ideas”; L21 “before they snowball”; L23 “Dig in as much -- or as little -- as you want.”; L25 “so that your learnings today become durable”; L28 “surfaces insights”; L31 “a sounding board and reality check”; L31 “actually enjoy”; L33 “Fitness is built over decades, not weeks or months.”; L39 “Get curious”; L39 “When things go off the rails”; L39 “you can always end it early”
- `website/content/llm/prompts.md`: L10 “Each one works as written. Adapt freely.”
- `website/content/reference/configuration.md`: L14 “and no other way”; L20 “**exit code 2**”; L26 “**You own this file. fitdocs only reads it**”; L26 “just means "use the default"”; L26 “never silently ignored”
- `website/content/reference/ownership.md`: L14 “and writes **nowhere else**”; L40 “exactly as it was”; L54 “That way fitdocs never guesses about content it doesn't understand.”; L56 “**No operation throws away your region or race-tag content.**”; L77 “for exactly what each version number promises”

Two non-trope notes from the same sweep: `llm/index.md` puts a
"**Once a week**" routine under a "### Mesocycle" heading (a week is a
microcycle), and `index.md`'s unfinished last sentence is already
`2026-10-19-site-maintainer-prose-nits`.

## How to pick it up
1. Wait for PR #1 to merge, or work on its branch if it hasn't, so the
   60 in-diff fixes aren't redone.
2. For each quote above, find it by text, and propose the smallest rewrite
   that keeps every fact, matching the page's apostrophe style (some pages use
   curly ’, some straight ') and capitalizing "Fitdocs" at a sentence start.
3. Show the maintainer each proposal with a permalink
   (`https://github.com/joshua-stauffer/fitdocs/blob/<sha>/website/content/<page>?plain=1#L<n>`)
   before editing; `index.md` and `llm/index.md` are their voice.

## Open questions
- Whether to adopt a site-wide rule against stating a guarantee twice in a
  row. That would decide many of these at once.
