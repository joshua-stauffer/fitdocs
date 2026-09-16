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

from fitdocs.plans.block_page import render_block_page
from fitdocs.plans.engine import (
    BlockOutcome,
    BlockStatus,
    PlanReport,
    Resolver,
    run_plan,
)
from fitdocs.plans.model import (
    IDENTIFIER,
    MUTABLE_FIELDS,
    RESERVED_BLOCK_IDS,
    AddOp,
    Amendment,
    AmendmentOp,
    AmendmentSpec,
    Block,
    Change,
    Mesocycle,
    MesocycleTarget,
    Override,
    PlannedWorkout,
    PlanProblem,
    PlanState,
    RemoveOp,
    RowAdded,
    RowChanged,
    RowRemoved,
    TargetChanged,
    TargetOp,
    UpdateOp,
    apply_amendments,
    build_block,
    check_overrides,
    check_rows,
    check_targets,
    is_reserved_block_id,
    mesocycle_number,
    mesocycle_windows,
)
from fitdocs.plans.page import (
    BLOCK_FRONTMATTER_KEYS,
    BLOCK_TYPE,
    BLOCK_VERSION,
    BLOCK_VERSION_KEY,
    GENERATOR,
    INDOOR_WORD,
    PLANNED_FRONTMATTER_KEYS,
    PLANNED_TYPE,
    PLANNED_VERSION,
    PLANNED_VERSION_KEY,
    WEEKDAYS,
    banner,
    cell,
    check_resolution,
    format_day,
    format_load,
    frontmatter,
    is_fence_line,
    link_text,
    notes_region,
    sport_phrase,
    yaml_string,
)
from fitdocs.plans.planned_page import render_planned_page
from fitdocs.plans.resolution import (
    UNRESOLVED_ROW,
    MesocycleResolution,
    Resolution,
    RowResolution,
    unresolved,
)
from fitdocs.plans.settings import (
    DEFAULT_PLAN_SETTINGS,
    PLANS_TABLE,
    PlanSettings,
    PlanSettingsError,
    load_plan_settings,
    resolve_plans_dir,
)
from fitdocs.plans.source import PlanValidationError, load_block, parse_block

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
    "MUTABLE_FIELDS",
    "UpdateOp",
    "AddOp",
    "RemoveOp",
    "TargetOp",
    "AmendmentOp",
    "AmendmentSpec",
    "RowChanged",
    "RowAdded",
    "RowRemoved",
    "TargetChanged",
    "Change",
    "Amendment",
    "Override",
    "Block",
    "apply_amendments",
    "check_overrides",
    "build_block",
    # -- plans.source (task 2.3) --
    "PlanValidationError",
    "parse_block",
    "load_block",
    # -- plans.resolution (task 3.1) --
    "RowResolution",
    "MesocycleResolution",
    "Resolution",
    "UNRESOLVED_ROW",
    "unresolved",
    # -- plans.page (task 3.1) --
    "BLOCK_TYPE",
    "BLOCK_VERSION",
    "BLOCK_VERSION_KEY",
    "BLOCK_FRONTMATTER_KEYS",
    "PLANNED_TYPE",
    "PLANNED_VERSION",
    "PLANNED_VERSION_KEY",
    "PLANNED_FRONTMATTER_KEYS",
    "WEEKDAYS",
    "INDOOR_WORD",
    "GENERATOR",
    "yaml_string",
    "frontmatter",
    "banner",
    "notes_region",
    "check_resolution",
    "is_fence_line",
    "sport_phrase",
    "cell",
    "link_text",
    "format_day",
    "format_load",
    # -- plans.settings (task 4.1) --
    "PLANS_TABLE",
    "PlanSettings",
    "DEFAULT_PLAN_SETTINGS",
    "PlanSettingsError",
    "load_plan_settings",
    "resolve_plans_dir",
    # -- plans.block_page, plans.planned_page, plans.engine (task 4.2) --
    "render_block_page",
    "render_planned_page",
    "BlockStatus",
    "BlockOutcome",
    "PlanReport",
    "Resolver",
    "run_plan",
]
