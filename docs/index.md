# Documentation

This is the single entry point into fitdocs' documentation: every page below
covers one part of installing, configuring, and running fitdocs, or of
extending it as a plugin author or contributor. Start with [Install](install.md)
if you have not run fitdocs yet; otherwise jump straight to the page you need.

| Page | What you'll find there |
| --- | --- |
| [Install](install.md) | The full first-run path: installing the tool, choosing a data root, getting `.fit` files where fitdocs finds them, and running it. |
| [Configuration](configuration.md) | Everything fitdocs reads to decide where it writes, what it fetches, and how it computes — the data root, its resolution order, the settings file, and network/offline behavior. |
| [The inbox interface](inbox.md) | The standing inbox: its default location and keys, drain semantics, the safeguards, and the never-delete disposition policy. |
| [Upgrading and uninstalling](upgrading.md) | The exact commands to upgrade and uninstall, and what each does and does not touch. |
| [Wiki integration and agent skills](wiki-integration.md) | Installing and verifying the packaged agent skills, and the end-to-end recipe for adopting fitdocs into an agent-managed wiki. |
| [The ownership contract](ownership-contract.md) | What fitdocs owns in your data root and what you own, directory by directory. |
| [The plugin platform](plugins.md) | How fitdocs discovers third-party training-load calculators and how to package or drop one in. Its authoring companion, [Contributing a load calculator](contributing-calculators.md), walks through writing one from scratch. |
| [Compatibility policy](compatibility.md) | What fitdocs' version number promises, contract by contract, and what upgrading within a compatible range does and does not require of you. |
| [Releasing](releasing.md) | The ordered release procedure a maintainer follows by hand, and the automation that runs the identical commands from a version tag. |
| [Contributing](../CONTRIBUTING.md) | The contributor path: environment setup, what must pass before a change is accepted, and the rule for third-party material. |

## Where things live

The [README](../README.md) is the project overview — what fitdocs is, how to
install it, and a minimal first run — with links back into this set. This
page is where the detail lives once you're past that overview.
`docs/reference/` is research and provenance material this project keeps for
its own decisions — methodology evaluations, benchmark sources, and the
purge's own history-rewrite record among them; it is not user documentation
and no page above links into it.
