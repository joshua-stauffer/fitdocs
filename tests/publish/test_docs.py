"""The publishing reference, docs/publishing.md (publish-core Req 1.7, 9.6, 10.6,
16.1, 16.3).

The page's tables and examples are held equal to the code that produces them:
the code table to the vocabulary, the placeholder table to the placeholder
names and the examples the values produce (and the decimal places and
whole-number claims of its Format column to those examples), the option table
to the command, and the examples to the report, listing, ledger and region
renderers. The report examples come from a real ``run_publish`` over pages on
disk. The constants the prose restates (link and label bounds, the refused link
characters, the publication id shape, the listing sentence) are held equal to
the code. The page names no service.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest
from typer.main import get_command

from fitdocs.cli import _EXIT_CONFIG_ERROR, _EXIT_FILE_FAILURES, _EXIT_INTERRUPTED, app
from fitdocs.layout import publish_ledger_path
from fitdocs.publish.compose import post_digest
from fitdocs.publish.engine import PublishReport, ResultRow
from fitdocs.publish.ledger import (
    _ID_RE,
    PUBLISH_LEDGER_VERSION,
    PublicationRecord,
    load_ledgers,
    save_ledger,
    workout_page_key,
)
from fitdocs.publish.links import published_content
from fitdocs.publish.outcomes import OUTCOMES, PublishCode
from fitdocs.publish.report import (
    render_json,
    render_targets_json,
    render_targets_text,
    render_text,
)
from fitdocs.publish.request import (
    _LINK_REFUSED,
    MAX_LABEL_LENGTH,
    MAX_LINK_LENGTH,
    Post,
    PublishResult,
    valid_label,
    valid_link,
)
from fitdocs.publish.settings import (
    DEFAULT_DESCRIPTION,
    DEFAULT_TEMPLATES,
    load_publish_settings,
)
from fitdocs.publish.targets import TargetRow
from fitdocs.publish.template import TargetTemplates
from fitdocs.publish.values import PLACEHOLDERS, page_values
from tests.publish.conftest import ride_page, run_page
from tests.publish.test_engine import CLOCK, Env, _fm, _ref

_ROOT = Path(__file__).resolve().parents[2]
_PAGE = _ROOT / "docs" / "publishing.md"
_PAGE_URL = (
    tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "urls"
    ]["Source"]
    + "/blob/main/docs/publishing.md"
)

#: Every service, platform or brand name the page must not carry (matched
#: case-insensitively): the two Phase 14 services and the relay's host.
_SERVICE_NAMES = ("intervals", "strava", "fitdocs.ai")


def _text() -> str:
    return _PAGE.read_text(encoding="utf-8")


def _service_hits(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name in _SERVICE_NAMES if name in lowered]


def _section(heading: str) -> str:
    """The body of the one section whose heading is exactly ``heading``."""
    lines = _text().split("\n")
    starts = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"#{2,4} " + re.escape(heading), line)
    ]
    assert len(starts) == 1, f"expected one {heading!r} heading, found {len(starts)}"
    level = len(lines[starts[0]]) - len(lines[starts[0]].lstrip("#"))
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        match = re.match(r"(#{1,6}) ", line)
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _table(body: str) -> list[list[str]]:
    """The data rows of the one table in ``body``, as stripped cells."""
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in body.split("\n")
        if line.startswith("|")
    ]
    assert len(rows) > 2, "no table found in the section"
    return rows[2:]


def _fenced(body: str, language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)\n```", body, flags=re.DOTALL)


def _code(cell: str) -> str:
    assert cell.startswith("`") and cell.endswith("`"), cell
    return cell[1:-1]


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


# ------------------------------------------------------------ the code table


def test_the_code_table_equals_the_vocabulary_in_order() -> None:
    rows = _table(_section("Outcome codes"))
    expected = [
        [
            f"`{info.code.value}`",
            info.explanation,
            _yes_no(info.landed),
            _yes_no(info.failure),
            _yes_no(info.from_target),
            _yes_no(info.stops_target),
            _yes_no(info.target_state),
        ]
        for info in OUTCOMES.values()
    ]
    assert len(expected) == 35, "the vocabulary this page was written against moved"
    assert rows == expected


# ------------------------------------------------------- the placeholder table


def _example_values() -> dict[str, str | None]:
    values = dict(page_values(run_page()))
    values["speed_kmh"] = page_values(ride_page())["speed_kmh"]
    return values


def test_the_placeholder_table_lists_every_name_in_order_with_its_example() -> None:
    rows = _table(_section("Placeholders"))
    assert [_code(row[0]) for row in rows] == list(PLACEHOLDERS)
    examples = _example_values()
    assert all(value is not None for value in examples.values())
    assert [row[2] for row in rows] == [f"`{examples[name]}`" for name in PLACEHOLDERS]


def test_the_format_column_agrees_with_its_examples() -> None:
    """The decimal places and whole numbers the Format column promises."""
    places = {"one": 1, "two": 2}
    checked = 0
    for row in _table(_section("Placeholders")):
        example = row[2].strip("`")
        decimals = re.search(r"\b(one|two) decimals?\b", row[1])
        if decimals is not None:
            pattern = rf"\d+\.\d{{{places[decimals.group(1)]}}}"
        elif re.search(r"\bwhole\b", row[1]):
            pattern = r"\d+"
        else:
            continue
        assert re.fullmatch(pattern, example), (row[0], row[1], example)
        checked += 1
    assert checked == 8


# ---------------------------------------------------------- the option table


def test_the_option_table_lists_exactly_the_commands_options() -> None:
    command = get_command(app)
    publish = command.commands["publish"]  # type: ignore[attr-defined]
    real = {
        flag
        for param in publish.params
        for flag in getattr(param, "opts", ())
        if flag.startswith("--")
    }
    assert real >= {"--to", "--yes", "--targets", "--format", "--out"}
    documented = {
        match
        for row in _table(_section("Options"))
        for match in re.findall(r"`(--[a-z]+)", row[0])
    }
    assert documented == real - {"--help"}


def test_the_exit_codes_table_matches_the_command() -> None:
    rows = _table(_section("Exit codes"))
    assert [row[0] for row in rows] == [
        f"`{code}`"
        for code in (0, _EXIT_FILE_FAILURES, _EXIT_CONFIG_ERROR, _EXIT_INTERRUPTED)
    ]
    assert [_EXIT_FILE_FAILURES, _EXIT_CONFIG_ERROR, _EXIT_INTERRUPTED] == [1, 2, 130]


# ----------------------------------------------------------------- examples


def _keys_after(body: str, phrase: str) -> list[str]:
    """The backticked names in the sentence ``<phrase>, in order: ...``."""
    found = re.search(
        re.escape(phrase) + r", in order: (.*?)\.\n", body, re.DOTALL | re.IGNORECASE
    )
    assert found is not None, phrase
    return re.findall(r"`([a-z_]+)`", found.group(1))


_TARGET = "club-feed"
_SHA_RUN = "a" * 63 + "1"
_SHA_RIDE = "b" * 63 + "2"
_SHA_THIRD = "c" * 63 + "3"
_SHA_FOURTH = "d" * 63 + "4"
_LANDED_LINK = "https://example.invalid/a/1"
_REFUSED_LINK = "http://example.invalid/b/2"


def _sample_report(root: Path, *, posting: bool) -> PublishReport:
    """The report the page's examples show, from a real ``run_publish`` over
    pages written to ``root`` and one scripted publishing target, ``_TARGET``.

    The pages' file names ascend in the order the rows are expected in, so the
    rows' order is the engine's, not the test's.
    """
    env = Env(root)
    # Two pages that opt in to nothing: the "opted in to no selected target" count.
    env.write("2026-10-01-walk.md", _fm(sources=[_ref("e" * 64)], publish=None))
    env.write("2026-10-02-walk.md", _fm(sources=[_ref("f" * 64)], publish=None))
    if posting:
        names = (
            ("2026-10-22-run.md", _SHA_RUN),
            ("2026-10-23-ride.md", _SHA_RIDE),
            ("2026-10-26-run.md", _SHA_THIRD),
            ("2026-10-27-ride.md", _SHA_FOURTH),
        )
        for name, sha in names:
            env.write(
                name,
                _fm(sources=[_ref(sha)], publish=_TARGET),
                post="Morning Run\n\nTime: 58:20",
            )
        env.spy.publisher.publish_script.extend(
            [
                PublishResult(PublishCode.POSTED, _LANDED_LINK),
                PublishResult(PublishCode.POSTED, _REFUSED_LINK),
                PublishResult(PublishCode.RATE_LIMITED),
            ]
        )
        return env.run(env.plan(configured=(_TARGET,), posting=True))
    env.write(
        "2026-10-28-run.md",
        _fm(sources=[_ref(_SHA_RUN)], load_value=None, publish=_TARGET),
        post="Morning Run\n\nLoad: {load_value}",
    )
    env.write(
        "2026-10-29-ride.md",
        _fm(sources=[_ref(_SHA_RIDE)], publish=_TARGET),
        post="Evening Ride\n\nTime: {moving_time}",
    )
    env.write(
        "2026-10-30-run-1.md",
        _fm(sources=[_ref(_SHA_THIRD)], publish=_TARGET),
        post="{title}\n\nDistance: {distance_km} km\nTime: {moving_time}",
    )
    posted = Post("Evening Ride", "Time: 58:20")
    record = PublicationRecord(
        page=workout_page_key(_SHA_RIDE),
        publication_id="0" * 31 + "1",
        digest=post_digest(posted),
        code="posted",
        at=CLOCK,
        link=None,
        label=None,
    )
    return env.run(
        env.plan(configured=(_TARGET,), records={_TARGET: [record]}, posting=False)
    )


def _block_after(body: str, marker: str) -> str:
    """The first fenced ``text`` block after the line holding ``marker``."""
    head, found, tail = body.partition(marker)
    assert found, f"{marker!r} not found"
    return _fenced(tail, "text")[0]


def _listed_pages(block: str) -> list[str]:
    return re.findall(r"^(workouts/\S+) ->", block, flags=re.MULTILINE)


def test_the_dry_run_example_is_the_dry_run_report(tmp_path: Path) -> None:
    shown = _block_after(_section("Reading the report"), "dry run")
    report = _sample_report(tmp_path, posting=False)
    assert [(r.code, r.decision) for r in report.rows] == [
        (PublishCode.VALUE_MISSING, None),
        (PublishCode.UNCHANGED, PublishCode.UNCHANGED),
        (PublishCode.WOULD_POST, PublishCode.WOULD_POST),
    ]
    assert shown == render_text(report)
    pages = _listed_pages(shown)
    assert len(pages) == 3 and pages == sorted(pages)


def test_the_posting_example_is_the_posting_report(tmp_path: Path) -> None:
    shown = _block_after(_section("Reading the report"), "posting run")
    report = _sample_report(tmp_path, posting=True)
    assert [(r.code, r.decision, r.link_refused) for r in report.rows] == [
        (PublishCode.POSTED, PublishCode.WOULD_POST, False),
        (PublishCode.POSTED, PublishCode.WOULD_POST, True),
        (PublishCode.RATE_LIMITED, PublishCode.WOULD_POST, False),
        (PublishCode.NOT_ATTEMPTED, PublishCode.WOULD_POST, False),
    ]
    assert shown == render_text(report)
    pages = _listed_pages(shown)
    assert len(pages) == 4 and pages == sorted(pages)
    assert "  link: refused" in shown


def test_the_json_keys_are_those_of_the_json_report(tmp_path: Path) -> None:
    body = _section("Reading the report")
    document = json.loads(render_json(_sample_report(tmp_path, posting=False)))
    assert _keys_after(body, "top-level keys") == list(document)
    assert _keys_after(body, "each result's keys") == list(document["results"][0])
    assert document["format"] == 1
    assert "`format` is `1`" in body


def _target_rows() -> tuple[TargetRow, ...]:
    return (
        TargetRow(
            name="club-feed",
            connector="example",
            display_name="Example feed",
            capabilities=("push-activity", "annotate-remote-activity"),
            state=PublishCode.READY,
        ),
        TargetRow(
            name="team-log",
            connector="example-two",
            display_name="Example log",
            capabilities=("annotate-remote-activity",),
            state=PublishCode.NOT_CONNECTED,
        ),
    )


def test_the_listing_example_is_the_targets_listing() -> None:
    body = _section("Listing the targets")
    assert _fenced(body, "text")[0] == render_targets_text(_target_rows())
    sentence = render_targets_text(())
    assert sentence == "No publish target is configured."
    assert f"it prints `{sentence}` and exits 0" in " ".join(body.split())
    assert f"the sentence `{sentence}`" in " ".join(
        _section("Reading the report").split()
    )
    document = json.loads(render_targets_json(_target_rows()))
    assert _keys_after(body, "listing's keys") == list(document)
    assert _keys_after(body, "each target's keys") == list(document["targets"][0])


def test_the_default_post_example_is_what_the_defaults_compose() -> None:
    from fitdocs.publish.compose import compose_post

    shown = _block_after(_section("Templates and settings"), "built-in default")
    post = compose_post(DEFAULT_TEMPLATES, page_values(run_page()))
    assert isinstance(post, Post)
    assert shown == f"{post.title}\n\n{post.description}"
    assert DEFAULT_DESCRIPTION.count("{?") == 7


def test_the_settings_example_loads() -> None:
    body = _section("Templates and settings")
    document = tomllib.loads(_fenced(body, "toml")[0])
    assert "publish" in document
    loaded = load_publish_settings(
        document, settings_file=Path("fitdocs.toml"), targets=["club-feed", "team-log"]
    )
    default = DEFAULT_TEMPLATES.title.source
    wide = document["publish"]["title"]
    assert wide != default
    assert loaded.for_target("club-feed").title.source == wide
    assert loaded.for_target("team-log").title.source == "{sport} on {date}"
    assert loaded.for_target("club-feed").description.source != (
        loaded.for_target("team-log").description.source
    )
    assert (
        loaded.for_target("team-log").description.source
        == (document["publish"]["description"])
    )


def test_the_ledger_example_is_a_readable_ledger(tmp_path: Path) -> None:
    body = _section("The publish ledger")
    example = _fenced(body, "toml")[0]
    path = publish_ledger_path(tmp_path, "club-feed")
    path.parent.mkdir(parents=True)
    path.write_text(example, encoding="utf-8")
    ledgers = load_ledgers(tmp_path, {"club-feed": "example"})
    (record,) = ledgers["club-feed"].records
    assert record.digest is not None and record.link is not None
    assert f"`{publish_ledger_path(Path(), '<target>')}`" in body
    # The example is exactly what the writer produces from what it reads.
    other = tmp_path / "rewritten"
    assert save_ledger(other, ledgers["club-feed"]) is True
    written = publish_ledger_path(other, "club-feed").read_text(encoding="utf-8")
    assert written == example + "\n"


def test_the_ledger_prose_states_the_id_and_version_the_code_enforces() -> None:
    body = " ".join(_section("The publish ledger").split())
    assert PUBLISH_LEDGER_VERSION == 1
    assert "`ledger_version` is `1`" in body
    assert _ID_RE.fullmatch("0123456789abcdef" * 2) is not None
    for wrong in ("a" * 31, "a" * 33, "a" * 40, "A" * 32, "g" * 32):
        assert _ID_RE.fullmatch(wrong) is None, wrong
    assert "32 random lowercase hexadecimal characters" in body
    example = _fenced(_section("The publish ledger"), "toml")[0]
    (ident,) = re.findall(r'^id = "(.*)"$', example, flags=re.MULTILINE)
    assert _ID_RE.fullmatch(ident) is not None


def test_the_published_line_example_is_the_published_content() -> None:
    body = _section("The published region")
    line = _fenced(body, "markdown")[0]
    links = [
        ("club-feed", "Club feed", "https://example.invalid/a/1"),
        ("team-log", "Team log", "https://example.invalid/b/2"),
    ]
    assert line == published_content(links)


def test_the_link_and_label_rules_are_the_codes() -> None:
    body = " ".join(_section("The published region").split())
    assert f"at most {MAX_LINK_LENGTH} characters long" in body
    assert f"1 to {MAX_LABEL_LENGTH} characters" in body
    (span,) = re.findall(r"``(<.+?)``", body)
    assert set(span) == _LINK_REFUSED
    # The bounds and characters are the rule's, not just constants.
    good = "https://example.invalid/"
    assert valid_link(good + "a" * (MAX_LINK_LENGTH - len(good)))
    assert not valid_link(good + "a" * (MAX_LINK_LENGTH - len(good) + 1))
    assert not any(valid_link(good + char) for char in span)
    assert valid_label("a" * MAX_LABEL_LENGTH)
    assert not valid_label("a" * (MAX_LABEL_LENGTH + 1))
    assert not valid_label("")
    # The page's prose names the report line exactly as the renderer prints it.
    for heading in ("Reading the report", "The published region"):
        assert "`  link: refused`" in _section(heading), heading
    assert "  link: refused" in render_text(
        PublishReport(
            posting=True,
            rows=(
                ResultRow(
                    "workouts/a.md",
                    "t",
                    PublishCode.POSTED,
                    PublishCode.WOULD_POST,
                    None,
                    None,
                    True,
                    None,
                ),
            ),
            not_opted_in=0,
            configured=1,
        )
    )


# ------------------------------------------------------------- the statements


def test_the_page_carries_every_section_the_task_names() -> None:
    headings = re.findall(r"^#{2,4} (.+)$", _text(), flags=re.MULTILINE)
    for required in (
        "The command",
        "Options",
        "Preflight",
        "Exit codes",
        "Reading the report",
        "Listing the targets",
        "Opting a page in",
        "The `post` region",
        "Templates and settings",
        "Template syntax",
        "Placeholders",
        "Outcome codes",
        "The publish ledger",
        "The published region",
        "What a target does",
        "Nothing from a service",
    ):
        assert required in headings, required


def test_the_page_states_the_rulings_a_reader_relies_on() -> None:
    text = " ".join(_text().split())
    for sentence in (
        # Req 1.6 / 16.1: the closing statement.
        "Nothing a service returns is printed, logged or written, except a "
        "permitted link.",
        # Controller ruling 5.1.
        "A publication id that appears in the ledgers of two targets is refused",
        # Controller ruling 6.3 (Req 8.6).
        "every pair of that target in the run that would be sent gets that code",
        "a pair decided `unchanged` or refused offline keeps its own code",
        # Req 10.5.
        "does not count as landed",
        # Req 10.6 / 9.6.
        "look for an existing activity before creating one",
        "more than one matching activity",
        # Req 2.7.
        "keeps the recorded link on the page",
        # Req 7.5.
        "A run without `--yes` sends no request and writes nothing",
    ):
        assert sentence in text, sentence


def test_the_page_names_no_service() -> None:
    assert _service_hits(_text()) == []


@pytest.mark.parametrize("name", _SERVICE_NAMES)
def test_the_service_scan_sees_each_listed_name(name: str) -> None:
    for spelling in (name, name.upper(), name.title()):
        assert _service_hits(f"Posts to {spelling} work.") == [name]


# --------------------------------------------------------------- the links


def test_the_documentation_index_links_the_page() -> None:
    index = (_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "](publishing.md)" in index


def test_the_entry_point_link_list_requires_the_page() -> None:
    from tests.test_docs_guarantees import _REQUIRED_ENTRY_POINT_LINKS

    assert "publishing.md" in _REQUIRED_ENTRY_POINT_LINKS


def test_the_package_declares_the_page_as_a_project_url() -> None:
    urls = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["urls"]
    assert urls["Publishing"] == _PAGE_URL


def test_the_configuration_page_names_the_table_and_the_command() -> None:
    text = (_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    assert "### `[publish]`" in text
    assert "`fitdocs publish`" in text
    assert "](publishing.md)" in text
    assert (
        "falls back to the same field of `[publish]` first, and then to the built-in "
        "default" in " ".join(text.split())
    )


def test_a_target_field_falls_back_to_publish_then_the_default() -> None:
    """The order configuration.md and publishing.md state, as the loader does it."""
    file = Path("fitdocs.toml")
    both = load_publish_settings(
        {"publish": {"title": "{sport}", "targets": {"a": {"title": "{date}"}}}},
        settings_file=file,
        targets=["a", "b"],
    )
    assert both.for_target("a").title.source == "{date}"
    assert both.for_target("b").title.source == "{sport}"
    neither = load_publish_settings({}, settings_file=file, targets=["b"])
    assert neither.for_target("b").title.source == DEFAULT_TEMPLATES.title.source
    assert DEFAULT_TEMPLATES.title.source not in ("{sport}", "{date}")


def test_the_post_region_example_composes_what_the_page_says() -> None:
    from fitdocs.publish.compose import (
        PostOverride,
        compose_post,
        override_templates,
        read_post_region,
    )

    region = _fenced(_section("The `post` region"), "markdown")[0]
    inner = region.split("\n", 1)[1].rsplit("\n", 1)[0]
    override = read_post_region(inner)
    assert isinstance(override, PostOverride)
    templates = override_templates(override)
    assert isinstance(templates, TargetTemplates)
    post = compose_post(templates, page_values(run_page()))
    assert post == Post(
        "Morning Run: a day I wanted to run",
        "Felt strong from the first kilometre.\nAverage heart rate: 149 bpm",
    )
