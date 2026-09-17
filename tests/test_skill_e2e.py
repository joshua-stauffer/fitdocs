"""The automated half of the skill's own procedure, walked end to end
(build-training-block spec, task 3.4; Req 3.10, 3.11, 6.1, 6.2, 6.3). See
"SkillE2E (`tests/test_skill_e2e.py` and the recorded exercise)" in
`.kiro/specs/build-training-block/design.md` and "The skill's procedure, as
the e2e test walks it" (the sequence diagram, same design document).

This module is the mechanical half of Req 6.1's exercise (Req 6.2): it reads
the shipped companion, `example-block.toml`, through
`fitdocs.agentskill.skill_root` -- never a repository-relative path -- and
cuts it at its own three markers into the three plan-source texts the skill
teaches an agent to write incrementally (the section as first written, plus
the amendment, plus the two settling overrides the companion already
carries). Every run happens under `CliRunner` against a synthetic root
under `tmp_path` that carries no `fitdocs.toml`, so the plan-source
directory the run reads is the tool's own default, `plans/` (design's
"Automated half"). Every run is wrapped in the fake-date contextmanager
`tests.test_history_e2e._fake_system_date`, pinned to 2029-12-01 (the same
idiom `tests/test_reconcile_e2e.py` uses), so the walk never depends on the
wall clock and every row in the shipped example -- dated in 2030 -- resolves
`upcoming` before anything is logged.

No synthetic workout page here is read by any other test module; each is
built by this module's own `_page` helper, in the shape
`tests/plans/test_corpus.py::_page` and `tests/history/test_engine.py:43-64`
establish, extended with the frontmatter keys `fitdocs.plans.corpus` reads
(`sport`, `modality`, `indoor`, `start_time`) -- `modality` and `indoor` are
optional and emitted only when given; the two synthetic `Run` pages this
module writes (Stage C) pass only `sport` and `start_time`, because neither
competing row states a modality or an indoor flag.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from datetime import UTC, date, datetime, time
from pathlib import Path

from typer.testing import CliRunner, Result

from fitdocs import agentskill
from fitdocs.agentskill import BLOCK_SKILL_NAME
from fitdocs.cli import app
from fitdocs.contract import DATE_KEY
from fitdocs.plans.source import parse_block

# Imported dynamically, not `from tests.test_history_e2e import
# _fake_system_date` -- a static import would pull that module into this
# module's own mypy pass (this module is in `pyproject.toml`'s typed
# `files` list; `test_history_e2e.py` is not, and task ownership forbids
# fixing another module's type errors to make that pass green). The
# runtime behavior is identical: the same private context manager, from
# the same module, called the same way -- only how mypy sees the import
# differs.
_fake_system_date = importlib.import_module("tests.test_history_e2e")._fake_system_date

runner = CliRunner()

# --- the companion's own markers (cut points), verified non-vacuous below ---

_MARKER_1 = "# --- the plan as first written ---"
_MARKER_2 = "# --- amendments: appended, never edited ---"
_MARKER_3 = "# --- overrides: appended when settling ---"

_BLOCK_ID = "example-block"

# The pinned "today" for every run: before every row in the shipped
# example (which starts 2030-01-07), so every unmatched row is `upcoming`,
# never `not logged`.
_TODAY = date(2029, 12, 1)


def _epoch_utc_noon(day: date) -> float:
    return datetime.combine(day, time(12, 0), tzinfo=UTC).timestamp()


_EPOCH = _epoch_utc_noon(_TODAY)


# ==============================================================================
# Fixture helpers
# ==============================================================================


def _companion_text() -> str:
    root = agentskill.skill_root(BLOCK_SKILL_NAME)
    assert root is not None, "the packaged skill is not installed"
    return (root / "example-block.toml").read_text(encoding="utf-8")


def _cut_stages(text: str) -> tuple[str, str]:
    """Stage A (before the amendments marker) and Stage B (before the
    overrides marker) -- each marker asserted to appear exactly once first.
    Without that guard, a companion that dropped a marker would fail with a
    bare `ValueError` out of `str.index`, far from the real cause; a
    companion carrying a marker *twice* would fail with no error at all --
    `str.index` cuts at the first occurrence either way, silently, with no
    signal that the cut point was ambiguous. The exactly-once assertion
    replaces both with one clear failure naming the offending marker."""
    for marker in (_MARKER_1, _MARKER_2, _MARKER_3):
        assert text.count(marker) == 1, marker
    stage_a = text[: text.index(_MARKER_2)]
    stage_b = text[: text.index(_MARKER_3)]
    return stage_a, stage_b


def _plans_dir(root: Path) -> Path:
    directory = root / "plans"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_source(plans_dir: Path, text: str) -> Path:
    path = plans_dir / f"{_BLOCK_ID}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_plan(root: Path) -> Result:
    with _fake_system_date(_EPOCH, tz="UTC"):
        assert date.today() == _TODAY
        return runner.invoke(app, ["plan", "--out", str(root)])


_RENDERED_RE = re.compile(r"^rendered\s+(\S+) -> (\S+) ", re.MULTILINE)


def _rendered_source_and_page(stdout: str) -> tuple[str, str]:
    match = _RENDERED_RE.search(stdout)
    assert match, f"no 'rendered' line found in:\n{stdout}"
    return match.group(1), match.group(2)


def _row_line(block_text: str, block_id: str, row_id: str) -> str:
    """The one day-table line whose Planned cell links to `row_id`'s own
    planned page (`layout.planned_rel_link`'s `<block_id>/<row_id>.md`
    form) -- found by that id-based href, never by table position, so a
    row moved to a new day (or a new mesocycle section) is still found by
    the same lookup after it moves."""
    anchor = f"]({block_id}/{row_id}.md)"
    matches = [line for line in block_text.splitlines() if anchor in line]
    assert len(matches) == 1, (row_id, matches)
    return matches[0]


def _row_cell(block_text: str, block_id: str, row_id: str) -> str:
    """The Resolution cell (the table's last real column) of `row_id`'s own
    row."""
    cells = _row_line(block_text, block_id, row_id).split("|")
    assert len(cells) >= 2, cells
    return cells[-2].strip()


def _row_day(block_text: str, block_id: str, row_id: str) -> str:
    """The Day cell (the table's first real column) of `row_id`'s own row."""
    cells = _row_line(block_text, block_id, row_id).split("|")
    assert len(cells) >= 2, cells
    return cells[1].strip()


def _planned_line(block_text: str) -> str:
    lines = [
        line for line in block_text.splitlines() if line.startswith("Planned workouts:")
    ]
    assert len(lines) == 1, lines
    return lines[0]


_BACKTICK_RE = re.compile(r"`([^`\n]+)`")


def _report_line_tokens() -> set[str]:
    """Every backticked token on the skill's one `Report lines:` line --
    read from that anchored line only, the way the conformance test reads
    `Sports:` (never by scanning section 5's other spans, which legitimately
    name outcomes a clean walk never prints)."""
    skill_path = agentskill.skill_file(BLOCK_SKILL_NAME)
    assert skill_path is not None
    text = skill_path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith("Report lines:")]
    assert len(lines) == 1, lines
    tokens = set(_BACKTICK_RE.findall(lines[0]))
    assert tokens, "the anchored line carries no backticked token"
    return tokens


def _page(
    *,
    day: str,
    start_time: str,
    sport: str = "Run",
    modality: str | None = None,
    indoor: bool | None = None,
    load_value: float = 45.0,
    load_methodology: str = "banister_1991",
) -> str:
    """A minimal, syntactically valid fitdocs workout document -- the shape
    `tests/plans/test_corpus.py::_page` and `tests/history/test_engine.py`
    establish, extended with the four fields the plan corpus reads that
    those two helpers don't both carry (`sport`, `modality`, `indoor`,
    `start_time`); `modality`/`indoor` are emitted only when given, the same
    optional-field convention `tests/plans/test_corpus.py::_page` uses."""
    lines = [
        "---",
        "title: Test Workout",
        "type: workout",
        f'{DATE_KEY}: "{day}"',
        f"sport: {sport}",
    ]
    if modality is not None:
        lines.append(f"modality: {modality}")
    if indoor is not None:
        lines.append(f"indoor: {'true' if indoor else 'false'}")
    lines.append(f'start_time: "{start_time}"')
    lines.append(f"load_value: {load_value}")
    lines.append(f"load_methodology: {load_methodology}")
    lines += ["---", "", "# Test Workout", ""]
    return "\n".join(lines) + "\n"


def _write_workout(root: Path, stem: str, **kwargs: object) -> Path:
    path = root / "workouts" / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_page(**kwargs), encoding="utf-8")  # type: ignore[arg-type]
    return path


# ==============================================================================
# The walk, five stages
# ==============================================================================


def test_skill_walkthrough_five_stages(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    plans_dir = _plans_dir(root)

    companion = _companion_text()
    stage_a_text, stage_b_text = _cut_stages(companion)
    n_original_rows = len(parse_block(stage_a_text, block_id=_BLOCK_ID).current.rows)

    stdouts: list[str] = []

    # -- Stage A: header, mesocycles, workouts -------------------------------
    source_path = _write_source(plans_dir, stage_a_text)
    before = _hash(source_path)
    result_a = _run_plan(root)
    stdouts.append(result_a.stdout)
    assert result_a.exit_code == 0, result_a.stdout
    assert _hash(source_path) == before, "fitdocs must not touch the plan source"

    rendered_source, rendered_page = _rendered_source_and_page(result_a.stdout)
    assert rendered_source == "plans/example-block.toml"
    assert rendered_page == "blocks/example-block.md"
    block_page_path = root / rendered_page
    assert block_page_path.exists()
    text_a = block_page_path.read_text(encoding="utf-8")

    rows = parse_block(stage_a_text, block_id=_BLOCK_ID).current.rows
    assert len(rows) == n_original_rows, "the walk's own precondition is non-vacuous"
    for row in rows:
        assert _row_cell(text_a, _BLOCK_ID, row.id) == "upcoming", row.id
    assert _planned_line(text_a) == (
        f"Planned workouts: {n_original_rows} -- {n_original_rows} upcoming."
    )
    assert "matched" not in text_a

    # -- Stage B: + amendment -------------------------------------------------
    before = _hash(_write_source(plans_dir, stage_b_text))
    result_b = _run_plan(root)
    stdouts.append(result_b.stdout)
    assert result_b.exit_code == 0, result_b.stdout
    assert _hash(source_path) == before

    rendered_source_b, rendered_page_b = _rendered_source_and_page(result_b.stdout)
    assert rendered_source_b == "plans/example-block.toml"
    text_b = (root / rendered_page_b).read_text(encoding="utf-8")

    assert "### Amendment 1 -- 2030-01-15" in text_b
    assert "Reason: Travel week" in text_b

    # the moved row (`w1-sat`, `amendment.update` moves it 2030-01-12 ->
    # 2030-01-14) keeps its planned page (found by the same id-based href
    # both before and after), and its own Day cell actually changed --
    # falsity-before: the row's date before the amendment is not yet the
    # date after it.
    day_before = _row_day(text_a, _BLOCK_ID, "w1-sat")
    day_after = _row_day(text_b, _BLOCK_ID, "w1-sat")
    assert day_before != day_after
    assert "2030-01-14" in day_after

    # -- Stage C: + two synthetic logged pages on the ambiguous day ----------
    _write_workout(
        root,
        "2030-01-22-run-0700",
        day="2030-01-22",
        start_time="2030-01-22T07:00:00+00:00",
    )
    _write_workout(
        root,
        "2030-01-22-run-1800",
        day="2030-01-22",
        start_time="2030-01-22T18:00:00+00:00",
    )
    before = _hash(source_path)
    result_c = _run_plan(root)
    stdouts.append(result_c.stdout)
    assert result_c.exit_code == 0, result_c.stdout
    assert _hash(source_path) == before

    rendered_source_c, rendered_page_c = _rendered_source_and_page(result_c.stdout)
    assert rendered_source_c == "plans/example-block.toml"
    text_c = (root / rendered_page_c).read_text(encoding="utf-8")

    cell_tue = _row_cell(text_c, _BLOCK_ID, "w2-tue")
    cell_tue_b = _row_cell(text_c, _BLOCK_ID, "w2-tue-b")
    assert cell_tue.startswith("matched (ambiguous):")
    assert cell_tue_b.startswith("matched (ambiguous):")
    assert "2030-01-22-run-0700" in cell_tue
    assert "2030-01-22-run-1800" in cell_tue_b
    assert re.search(r"^  ambiguous: .*w2-tue.*w2-tue-b", result_c.stdout, re.MULTILINE)
    # Both synthetic pages carry a load under the same methodology (design's
    # "each with a load under one methodology") -- this makes that fixture
    # detail consequential: the run actually infers and reports it, rather
    # than merely carrying an unread field.
    assert "methodology: banister_1991 (inferred)" in result_c.stdout

    # -- Stage D: + the two settling overrides the companion already carries -
    before = _hash(_write_source(plans_dir, companion))
    result_d = _run_plan(root)
    stdouts.append(result_d.stdout)
    assert result_d.exit_code == 0, result_d.stdout
    assert _hash(source_path) == before

    rendered_source_d, rendered_page_d = _rendered_source_and_page(result_d.stdout)
    assert rendered_source_d == "plans/example-block.toml"
    text_d = (root / rendered_page_d).read_text(encoding="utf-8")

    cell_tue_d = _row_cell(text_d, _BLOCK_ID, "w2-tue")
    cell_tue_b_d = _row_cell(text_d, _BLOCK_ID, "w2-tue-b")
    assert cell_tue_d.startswith("overridden:")
    assert "2030-01-22-run-0700" in cell_tue_d
    assert cell_tue_b_d == "skipped"
    assert "1 overridden, 1 skipped" in _planned_line(text_d)
    assert "ambiguous:" not in result_d.stdout

    # -- Negative stage: a third, superseding override naming a missing stem -
    negative_text = companion + (
        "\n[[override]]\n"
        "date = 2030-01-24\n"
        'id = "w2-tue"\n'
        'stems = ["2030-01-22-run-0930"]\n'
    )
    before = _hash(_write_source(plans_dir, negative_text))
    before_page_bytes = block_page_path.read_bytes()
    result_neg = _run_plan(root)
    stdouts.append(result_neg.stdout)
    assert result_neg.exit_code == 1, result_neg.stdout
    assert _hash(source_path) == before
    assert "not found" in result_neg.stdout

    assert block_page_path.exists()
    after_page_bytes = block_page_path.read_bytes()
    assert after_page_bytes != before_page_bytes, (
        "the block page must still be rendered"
    )

    text_neg = block_page_path.read_text(encoding="utf-8")
    assert "Problems:" in text_neg
    assert "override[2]" in text_neg
    assert text_neg.index("Problems:") < text_neg.index("override[2]"), (
        "override[2] must sit under the Problems: header, not merely appear"
        " somewhere on the page"
    )
    cell_tue_neg = _row_cell(text_neg, _BLOCK_ID, "w2-tue")
    assert "2030-01-22-run-0700" not in cell_tue_neg
    assert cell_tue_neg.startswith("overridden:")
    assert "`2030-01-22-run-0930` (not found)" in cell_tue_neg

    # -- Report tokens, across every run --------------------------------------
    union_stdout = "\n".join(stdouts)
    for token in _report_line_tokens():
        assert token in union_stdout, token
    assert "rendered" in union_stdout
