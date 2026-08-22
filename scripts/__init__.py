"""Internal tooling for fitdocs -- under the *current* build configuration,
never shipped in the sdist or the wheel.

`scripts/purge` holds the one-shot content purge tooling for the
`encumbered-content-purge` spec (`.kiro/specs/encumbered-content-purge/`).
The wheel never carries it: `[tool.hatch.build.targets.wheel]` scopes to
`src/fitdocs` only, and nothing in this spec touches that. The sdist is a
separate claim -- hatchling's default sdist scope is the whole working tree
minus `.gitignore`, so `scripts/` (and `tests/purge/`) would ship there
unless excluded, and today they are: `[tool.hatch.build.targets.sdist].exclude`
names both, verified by probe (`uv build`, then listing the built tarball).
See that block's comment for why, and for this spec's own task 3.1, which
deletes the whole sdist build-target section later -- at which point both
directories ship in the sdist again, and the "never shipped in the sdist"
half of this sentence stops being true. That is a deliberate,
already-scheduled interaction (see the `pyproject.toml` comment), not a
regression to flag when it happens.
"""

from __future__ import annotations
