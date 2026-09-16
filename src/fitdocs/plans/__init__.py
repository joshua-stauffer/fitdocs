"""The `fitdocs.plans` package: a training block's plan-source model, its
parser, the resolution seam, the two page renderers and the pass that writes
them (training-blocks spec; see `.kiro/specs/training-blocks/design.md`).

This module holds the package's published surface only -- the names a
consumer outside this package (including the `plan-resolution` and
`build-training-block` specs) may import -- and re-exports nothing of its
own computation. `__all__` starts here (task 2.1) with `plans.model`'s
task-2.1 names and is **append only** from here on: every later module task
in this plan (2.2, 2.3, 2.4, 3.1; 4.2 appends the two renderer modules' names
when it wires them) appends only its own module's names to the list below,
grouped one comment block per module, and rewrites nothing already there;
task 4.4 pins the final list once against `tests/test_public_api.py`'s
`_PLANS_SURFACE`. A wholesale rewrite of this list by a later task would
silently drop an earlier task's published names.
"""

from __future__ import annotations

from fitdocs.plans.model import (
    IDENTIFIER,
    RESERVED_BLOCK_IDS,
    Mesocycle,
    MesocycleTarget,
    PlannedWorkout,
    PlanProblem,
    PlanState,
    check_rows,
    check_targets,
    is_reserved_block_id,
    mesocycle_number,
    mesocycle_windows,
)

__all__: list[str] = [
    # -- plans.model (task 2.1) --
    "IDENTIFIER",
    "RESERVED_BLOCK_IDS",
    "is_reserved_block_id",
    "PlannedWorkout",
    "MesocycleTarget",
    "PlanState",
    "Mesocycle",
    "PlanProblem",
    "mesocycle_windows",
    "mesocycle_number",
    "check_rows",
    "check_targets",
    # -- plans.model (task 2.2) appends its own names here --
    # -- plans.source (task 2.3) appends its own names here --
    # -- plans.resolution (task 2.4) appends its own names here --
    # -- plans.page (task 3.1) appends its own names here --
    # -- plans.block_page, plans.planned_page (task 4.2) append here --
]
