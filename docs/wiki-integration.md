# Wiki Integration

fitdocs packages agent skills — self-contained markdown workflows an LLM
agent can follow — and this page covers the part of using them that has
nothing to do with any one skill's own instructions: where a skill lands,
how you put it where your agent reads it, how you know it took, how you
keep it current, and an end-to-end recipe for adopting fitdocs into a wiki
your agent already manages.

## The packaged skills

Run `fitdocs skill` with no argument to list every packaged skill and its
installed directory, one line per skill:

```bash
$ fitdocs skill
build-training-block  /path/to/site-packages/fitdocs/skills/build-training-block
fitdocs-workouts  /path/to/site-packages/fitdocs/skills/fitdocs-workouts
```

- **`build-training-block`** walks an agent through building a training
  block from the athlete's answers as a plan source, rendering it with
  `fitdocs plan`, amending it, and settling ambiguous matches.
- **`fitdocs-workouts`** drains the fitdocs inbox into workout documents
  and reads the resulting drain report — the turnkey workflow for a wiki's
  agent to run whenever new `.fit` files have arrived.

## Installing a skill

Run `fitdocs skill <name>` to print that skill's installed directory and a
one-line copy recipe:

```bash
$ fitdocs skill fitdocs-workouts
/path/to/site-packages/fitdocs/skills/fitdocs-workouts
Copy it into your agent's skills directory: cp -R /path/to/.../fitdocs-workouts <skills-dir>/fitdocs-workouts
```

The open SKILL.md standard fixes no install location, so `<skills-dir>`
above is whatever your own agent's documentation names — copy the printed
directory there under the skill's own name, either by copying it outright:

```sh
cp -R "$(fitdocs skill fitdocs-workouts | head -n1)" <skills-dir>/fitdocs-workouts
```

or by symlinking it instead, so an upgrade's refreshed directory is picked
up without a second copy step:

```sh
ln -s "$(fitdocs skill fitdocs-workouts | head -n1)" <skills-dir>/fitdocs-workouts
```

Either way, the directory name you install under must match the skill's
own name — an agent that lists skills by directory name, rather than by
reading `SKILL.md`'s frontmatter, would otherwise see it under the wrong
name.

## Confirming a skill is active

Ask your agent to list its skills. A correctly installed packaged skill
appears under the `name` its `SKILL.md` frontmatter declares — the same
name `fitdocs skill` printed it under. If it doesn't appear, re-check the
skills directory your agent actually reads (its own documentation names
this) against the directory `fitdocs skill <name>` reports.

## Updating a skill after upgrading fitdocs

A packaged skill is released together with fitdocs and carries the
released version. `fitdocs skill <name>` always prints the same installed
path, so if you installed by symlink (as in
[Installing a skill](#installing-a-skill) above), nothing further is
needed after an upgrade — the symlink already resolves to the upgraded
copy. If you installed by copy, replace it rather than layering onto it:
re-running `cp -R` into a directory that already exists copies *into* it
(leaving a stale top-level `SKILL.md` and an extra nested copy) rather than
over it, so remove the old copy first:

```bash
rm -rf <skills-dir>/fitdocs-workouts && cp -R "$(fitdocs skill fitdocs-workouts | head -n1)" <skills-dir>/fitdocs-workouts
```

The copied `SKILL.md`'s `metadata.version` field states which fitdocs
release it came from; read it directly to confirm which version is
currently installed for your agent:

```bash
grep -A1 '^metadata:' <skills-dir>/fitdocs-workouts/SKILL.md
```

## Adopting fitdocs into an existing wiki

An end-to-end recipe for pointing fitdocs at a markdown wiki your agent
already maintains — from nothing installed to a first drained inbox.
Run each step from the wiki's own working directory.

**1. Install fitdocs.** See [Install](install.md) for the two
isolated-application installer commands, and installing from a checkout
before the package is published.

**2. Point the data root at the wiki.** The data root *is* the wiki
directory itself — fitdocs never creates it, and here it already exists,
so there is nothing to `mkdir` for the data root. Drop the pointer file in
the wiki's own working tree, naming itself:

```bash
mkdir -p .fitdocs
echo "$(pwd)" > .fitdocs/data-root
```

**3. Configure the inbox.** The default inbox location, `inbox/` under the
data root, is created here by hand; `[inbox]` needs no keys to accept every
default (see [Inbox](inbox.md) for the full key reference). This step also
sets `[tiles] enabled = false`, so a wiki adopted somewhere offline never
attempts a tile fetch:

```bash
mkdir -p inbox
cat > fitdocs.toml <<'EOF'
[tiles]
enabled = false

[inbox]
EOF
```

**4. Install the skill.** Copy the `fitdocs-workouts` skill into your
agent's skills directory, as in
[Installing a skill](#installing-a-skill) above:

```bash
cp -R "$(fitdocs skill fitdocs-workouts | head -n1)" <skills-dir>/fitdocs-workouts
```

**5. Run the first drain.** With `.fit` files already waiting in `inbox/`:

```bash
fitdocs sync --no-prompt
```

**6. Confirm the result.**

```bash
fitdocs check
```

`fitdocs check` exits `0`. `workouts/` now holds one generated document per
drained `.fit` file, and `workouts/AGENTS.md` — the ownership declaration
fitdocs writes into every directory it owns — is present, naming the
published ownership contract as its authority. Nothing outside the
directories fitdocs owns is touched: the rest of your wiki is exactly as it
was.

## What the wiki's agent does next

From here, the wiki's agent follows the `fitdocs-workouts` skill's own
routine whenever new `.fit` files arrive or the wiki's workouts look
stale: drain the inbox, read the drain report, and act on anything
deferred, quarantined, or failed. See [Inbox](inbox.md) for the full
interface the skill's commands drive — the inbox's default location and
resolution, every settings key, drain semantics, the safeguards, and the
disposition policy's never-delete guarantee.
