"""M0/M1 tree manifests (Req 10.3) and the `training-load` spec-status
baseline (Req 4.4).

`ValidationGate` (design.md `#### ValidationGate`) needs an artifact that
outlives the rewrite: `git ls-tree -r <commit>` (path, mode, blob SHA) taken
against a **named commit**, never the working tree, so the baseline can be
regenerated even after edits have started on top of it. `M0`, captured here
against the commit before Major 1's first edit, is the fixed point `8.3`
diffs the post-rewrite tree against once the base commit itself has ceased
to exist.

The spec-status baseline is a second, unrelated artifact this task captures
to the same scratch location: `/kiro-spec-status training-load` is computed
output, not a tracked file, so unlike the tree manifest it cannot be
recovered from a commit once the rewrite has run. `6.2` compares the
post-reversal report against what is captured here field for field --
requirement count, acceptance-criterion count, task totals, and all six
`spec.json` approval booleans (Req 4.4).

Per the plan's execution rule that no task rests on a count, every number
below is *measured* from the source files at call time; nothing here is a
literal that could drift out from under the files it describes.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Tree manifests (Req 10.3) and the spec-status baseline (Req 4.4).",
)


@dataclass(frozen=True)
class ManifestRow:
    """One tracked path at a named commit: its path, its git file mode, and
    its blob object id."""

    path: str
    mode: str
    blob: str


def build_tree_manifest(commit: str, repo_root: Path) -> list[ManifestRow]:
    """`git ls-tree -r <commit>` at `repo_root`, one row per tracked path.

    Reads the named commit's recorded tree, never the working tree or the
    index -- a modification staged or made after `commit` was recorded does
    not change any row here.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "--full-tree", commit],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        meta, path = line.split("\t", 1)
        mode, obj_type, blob = meta.split(" ")
        if obj_type != "blob":
            # A commit-type entry is a submodule gitlink; fitdocs has none,
            # and it carries no content blob to compare.
            continue
        rows.append(ManifestRow(path=path, mode=mode, blob=blob))
    return sorted(rows, key=lambda row: row.path)


def write_tree_manifest(rows: list[ManifestRow], out_path: Path) -> None:
    """Write `rows` as `path\\tmode\\tblob` lines, one per tracked path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{row.path}\t{row.mode}\t{row.blob}" for row in rows]
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""))


def resolve_commit(commit: str, repo_root: Path) -> str:
    """Resolve `commit` (a ref, an abbreviation, `HEAD`, ...) to its full
    40-character object id, so a manifest's recorded provenance still
    resolves after the ref or the abbreviation it was given by has stopped
    meaning anything -- which is exactly the state task 8.3 finds M0 in,
    since the base commit itself has by then ceased to exist.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", commit],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def write_manifest_meta(commit: str, out_path: Path) -> None:
    """Write `<out_path>.meta.json`, recording the full commit id `out_path`
    was snapshotted against and the wall-clock time it was taken.

    `M0.tsv` on its own carries no record of which commit it snapshots (only
    the CLI's stdout echo does, and that is not durable) -- and that commit
    will not exist by the time task 8.3 consumes M0. This sibling file is
    the record that survives instead.
    """
    meta_path = out_path.with_name(out_path.name + ".meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "commit": commit,
        "taken_at": datetime.now(UTC).isoformat(),
    }
    meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


_REQUIREMENT_HEADING = re.compile(r"^### Requirement \d+", re.MULTILINE)
_ACCEPTANCE_CRITERIA_HEADING = re.compile(r"^#### Acceptance Criteria\b")
_HEADING = re.compile(r"^#")
_CRITERION_ITEM = re.compile(r"^\d+\.\s")
_TASK_LINE = re.compile(r"^\s*- \[([ xX])\]")


def count_requirements(requirements_md: Path) -> int:
    """Count `### Requirement N` headings, withdrawn ones included -- a
    withdrawn requirement keeps its heading and its number (the rule stated in
    `.kiro/specs/training-load/requirements.md`'s Amendment 2 and Requirement 4:
    withdrawn requirements keep their numbers and are marked withdrawn in
    place, and a retired number is never reused or renumbered)."""
    text = requirements_md.read_text()
    return len(_REQUIREMENT_HEADING.findall(text))


def count_acceptance_criteria(requirements_md: Path) -> int:
    """Count numbered acceptance-criterion lines, scoped to each `####
    Acceptance Criteria` section and reset at the next heading, so a numbered
    list anywhere else (an objective, a withdrawal note) is never counted."""
    count = 0
    in_section = False
    for line in requirements_md.read_text().splitlines():
        if _ACCEPTANCE_CRITERIA_HEADING.match(line):
            in_section = True
            continue
        if in_section and _HEADING.match(line):
            in_section = False
            continue
        if in_section and _CRITERION_ITEM.match(line):
            count += 1
    return count


def count_tasks(tasks_md: Path) -> tuple[int, int]:
    """Return `(total, completed)` counted from `- [ ]` / `- [x]` lines at
    any indentation depth -- major tasks and sub-tasks both count."""
    total = 0
    completed = 0
    for line in tasks_md.read_text().splitlines():
        match = _TASK_LINE.match(line)
        if match is None:
            continue
        total += 1
        if match.group(1).lower() == "x":
            completed += 1
    return total, completed


@dataclass(frozen=True)
class SpecApprovals:
    """The six approval booleans `spec.json` carries: `generated` and
    `approved` for each of the three phases."""

    requirements_generated: bool
    requirements_approved: bool
    design_generated: bool
    design_approved: bool
    tasks_generated: bool
    tasks_approved: bool


def load_spec_approvals(
    spec_json: Path,
) -> tuple[SpecApprovals, str | None, bool | None]:
    """Read the six approval booleans plus `phase` and
    `ready_for_implementation` from `spec.json`. Absent fields read as
    `None`, never a fabricated default."""
    data = json.loads(spec_json.read_text())
    approvals_raw = data["approvals"]
    approvals = SpecApprovals(
        requirements_generated=approvals_raw["requirements"]["generated"],
        requirements_approved=approvals_raw["requirements"]["approved"],
        design_generated=approvals_raw["design"]["generated"],
        design_approved=approvals_raw["design"]["approved"],
        tasks_generated=approvals_raw["tasks"]["generated"],
        tasks_approved=approvals_raw["tasks"]["approved"],
    )
    phase = data.get("phase")
    ready_for_implementation = data.get("ready_for_implementation")
    return approvals, phase, ready_for_implementation


@dataclass(frozen=True)
class SpecStatusBaseline:
    """Everything `6.2` must match field for field against a freshly
    computed report: the requirement, criterion and task counts, the six
    approval booleans, and the phase/readiness fields (Req 4.4)."""

    feature: str
    requirement_count: int
    criterion_count: int
    total_task_count: int
    completed_task_count: int
    approvals: SpecApprovals
    phase: str | None
    ready_for_implementation: bool | None


def build_spec_status_baseline(feature: str, spec_dir: Path) -> SpecStatusBaseline:
    """Compute the spec-status baseline for `feature` from
    `spec_dir/{requirements,tasks}.md` and `spec_dir/spec.json`."""
    requirement_count = count_requirements(spec_dir / "requirements.md")
    criterion_count = count_acceptance_criteria(spec_dir / "requirements.md")
    total_task_count, completed_task_count = count_tasks(spec_dir / "tasks.md")
    approvals, phase, ready_for_implementation = load_spec_approvals(
        spec_dir / "spec.json"
    )
    return SpecStatusBaseline(
        feature=feature,
        requirement_count=requirement_count,
        criterion_count=criterion_count,
        total_task_count=total_task_count,
        completed_task_count=completed_task_count,
        approvals=approvals,
        phase=phase,
        ready_for_implementation=ready_for_implementation,
    )


def write_spec_status_baseline(baseline: SpecStatusBaseline, out_path: Path) -> None:
    """Write `baseline` as sorted-key JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asdict(baseline), indent=2, sort_keys=True) + "\n")


# typer parameter declarations, defined at module scope so the ``typer.Option``
# / ``typer.Argument`` calls do not sit inside an argument default
# (flake8-bugbear B008), following ``src/fitdocs/cli.py``'s convention.
_COMMIT_ARGUMENT = typer.Argument(
    ..., help="Commit-ish to snapshot (e.g. M0's base commit)."
)
_OUT_OPTION = typer.Option(
    ..., "--out", help="Scratch path (outside the repo) to write to."
)
_REPO_ROOT_OPTION = typer.Option(Path("."), "--repo-root", help="Repository root.")
_FEATURE_ARGUMENT = typer.Argument(..., help="Spec feature name, e.g. training-load.")
_SPECS_ROOT_OPTION = typer.Option(
    Path(".kiro/specs"), "--specs-root", help="Root holding <feature>/spec.json etc."
)


@app.command("tree")
def tree_command(
    commit: str = _COMMIT_ARGUMENT,
    out: Path = _OUT_OPTION,
    repo_root: Path = _REPO_ROOT_OPTION,
) -> None:
    """Write a tree manifest for `commit`: one `path\\tmode\\tblob` row per
    tracked path, plus a sibling `<out>.meta.json` recording the resolved
    full commit id this manifest snapshots."""
    resolved_commit = resolve_commit(commit, repo_root)
    rows = build_tree_manifest(resolved_commit, repo_root)
    write_tree_manifest(rows, out)
    write_manifest_meta(resolved_commit, out)
    typer.echo(f"wrote {len(rows)} rows for {resolved_commit} to {out}")


@app.command("spec-status")
def spec_status_command(
    feature: str = _FEATURE_ARGUMENT,
    out: Path = _OUT_OPTION,
    specs_root: Path = _SPECS_ROOT_OPTION,
) -> None:
    """Capture the spec-status baseline for `feature` (Req 4.4)."""
    baseline = build_spec_status_baseline(feature, specs_root / feature)
    write_spec_status_baseline(baseline, out)
    typer.echo(f"wrote spec-status baseline for {feature} to {out}")
