"""Published wellness vocabulary, delivery contract and usable CLI examples."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path

import pytest
from typer.core import TyperGroup, TyperOption
from typer.main import get_command

from fitdocs.cli import app
from fitdocs.wellness import METRICS, Metric
from fitdocs.wellness.formats.intervals import DELIVERY_FORMAT, DELIVERY_VERSION
from tests.test_docs_guarantees import _REQUIRED_ENTRY_POINT_LINKS

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/wellness.md"
DAY_RULE = (
    "Every value belongs to one wellness day, a local calendar date. "
    "Sleep and every overnight value belong to the wake date. "
    "When a format supplies a sleep end timestamp instead of a date, an end "
    "at or after 18:00 on D−1 and before 18:00 on D belongs to D: take the "
    "date of end + 6 hours in its recorded UTC offset. "
    "A source-supplied calendar date is kept: Garmin calendarDate and "
    "intervals.icu id are wake dates for nights. "
    "The machine's timezone is never used. "
    "The night before a workout on local date D is the sleep of wellness day D. "
    "That morning's resting HR and HRV are the values of day D; a day-summary "
    "resting HR may be computed over the whole day D."
)
DAY_STATEMENT = (
    "The night before a workout on local date D is the sleep of wellness day D."
)
ATTRIBUTION = (
    "The table's `origin` column records the platform that measured each value, "
    "and any surface that charts or prints values whose `origin` is `garmin` "
    "(a dashboard over `wellness_daily`, for example) owes Garmin attribution, "
    "as the future recovery page and morning-of block will give it."
)
FENCES = re.compile(r"^```([^\n]*)\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    return _text().split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _rows() -> list[list[str]]:
    return [
        [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        for line in _section("Metrics").splitlines()
        if line.startswith("| `")
    ]


def test_metric_names() -> None:
    assert sorted(row[0] for row in _rows()) == sorted(
        metric.value for metric in METRICS
    )


@pytest.mark.parametrize("metric", tuple(METRICS), ids=lambda metric: metric.value)
@pytest.mark.parametrize("column", ("label", "unit", "minimum", "maximum"))
def test_metric_columns(metric: Metric, column: str) -> None:
    row = next(row for row in _rows() if row[0] == metric)
    info = METRICS[metric]
    index = {"label": 1, "unit": 2, "minimum": 3, "maximum": 4}[column]
    expected = getattr(info, column)
    if column in ("minimum", "maximum"):
        actual: object = float(row[index])
    else:
        actual = None if row[index] == "—" else row[index]
    assert actual == expected, (metric, column)


@pytest.mark.parametrize("key", ("format", "version"))
def test_delivery_constants(key: str) -> None:
    payload = json.loads(
        next(body for kind, body in FENCES.findall(_text()) if kind == "json")
    )
    assert payload[key] == {"format": DELIVERY_FORMAT, "version": DELIVERY_VERSION}[key]


def test_day_rule_is_complete() -> None:
    assert DAY_RULE in " ".join(_section("Wellness day").split())


def test_day_rule_has_one_published_statement() -> None:
    pages = sorted((ROOT / "docs").rglob("*.md"))
    occurrences = [
        str(page.relative_to(ROOT))
        for page in pages
        for _ in range(
            " ".join(page.read_text(encoding="utf-8").split()).count(DAY_STATEMENT)
        )
    ]
    assert occurrences == ["docs/wellness.md"]


def test_attribution_is_in_wellness_daily_section() -> None:
    assert ATTRIBUTION in " ".join(_section("wellness_daily").split())


@pytest.mark.parametrize(
    ("section", "statement"),
    [
        (
            "Get files into the inbox",
            "The intervals.icu pull delivers wellness files into the inbox: set "
            "`wellness = true` on your connector instance and run "
            "`fitdocs pull --sync`.",
        ),
        (
            "Get files into the inbox",
            "Apple Health import is planned and is not a supported format yet.",
        ),
        ("Supported files and source definitions", "`UDSFile_*.json`"),
        ("Supported files and source definitions", "`*_sleepData.json`"),
        ("Supported files and source definitions", "`MetricsMaxMetData_*.json`"),
        ("Supported files and source definitions", "`*_userBioMetrics.json`"),
        (
            "Supported files and source definitions",
            "Garmin's daily resting HR is its lowest 30-minute average "
            "over a 24-hour period",
        ),
        (
            "Supported files and source definitions",
            "Apple's resting HR is a sedentary estimate from background readings",
        ),
        (
            "Supported files and source definitions",
            "intervals.icu passes on its upstream platform's definition",
        ),
        (
            "Delivery envelope",
            'json.dumps(obj, sort_keys=True, separators=(",", ":"), '
            "ensure_ascii=False)",
        ),
        ("Delivery envelope", "sorted by `id`, with no duplicate `id`"),
        ("Delivery envelope", "`[a-z0-9]+(-[a-z0-9]+)*`"),
        (
            "Delivery envelope",
            "No other envelope key and no pull timestamp are emitted.",
        ),
        (
            "Absent values",
            "Missing, non-finite, out-of-range and placeholder measurements "
            "produce no row",
        ),
        ("Source precedence", 'precedence = ["intervals-icu", "garmin-export"]'),
        ("Source precedence", 'resting_hr_bpm = ["garmin-export"]'),
        ("Read the series", "day,metric,source,origin,value,canonical"),
        ("Read the series", "read_csv('wellness/*.csv', header = true)"),
        ("Read the series", "csv.DictReader(stream)"),
        ("Read the series", "read_series(Path("),
        (
            "Archive and withdrawal",
            "Remove its inbox copy too, or the next drain can import it again.",
        ),
        ("Check findings", "wellness_orphaned_entry"),
        ("Check findings", "wellness_series_stale"),
        ("Check findings", "wellness_series_occupied"),
        ("Check findings", "wellness_conflict"),
    ],
)
def test_guide_topics(section: str, statement: str) -> None:
    assert statement in " ".join(_section(section).split())


def _invocations(text: str) -> list[list[str]]:
    fragments = [
        body
        for kind, body in FENCES.findall(text)
        if kind in ("bash", "sh", "shell", "console")
    ]
    fragments.extend(re.findall(r"`(fitdocs(?:\s+[^`\n]+)?)`", FENCES.sub("", text)))
    result = []
    for fragment in fragments:
        for line in fragment.replace("\\\n", " ").splitlines():
            lexer = shlex.shlex(line, posix=True, punctuation_chars="|&;()<>")
            lexer.whitespace_split = True
            words = list(lexer)
            for index, word in enumerate(words):
                if word == "fitdocs":
                    end = next(
                        (
                            i
                            for i in range(index + 1, len(words))
                            if words[i] in ("|", "||", "&", "&&", ";", ">", ">>")
                        ),
                        len(words),
                    )
                    result.append(words[index + 1 : end])
    return result


def _validate_invocation(words: list[str]) -> None:
    command = get_command(app)
    index = 0
    while index < len(words):
        word = words[index]
        if word.startswith("-"):
            options = {
                flag: option
                for option in command.params
                if isinstance(option, TyperOption)
                for flag in (*option.opts, *option.secondary_opts)
            }
            option = options[word.split("=", 1)[0]]
            index += 1 if "=" in word or option.is_flag else 1 + option.nargs
        elif isinstance(command, TyperGroup):
            resolved = command.commands.get(word)
            if resolved is None:
                raise ValueError(f"unregistered fitdocs command {word!r}")
            command = resolved
            index += 1
        else:
            index += 1


def test_every_documented_command_and_option_is_registered() -> None:
    invocations = _invocations(_text())
    assert invocations
    for invocation in invocations:
        _validate_invocation(invocation)


def test_index_link_precedes_contributing() -> None:
    text = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", text)
    assert targets.index("wellness.md") < targets.index("../CONTRIBUTING.md")


def test_package_metadata_links_guide() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert (
        project["urls"]["Wellness"]
        == "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wellness.md"
    )


def test_required_entry_point_links_include_guide() -> None:
    assert "wellness.md" in _REQUIRED_ENTRY_POINT_LINKS


def test_configuration_wellness_keys_match_settings_reader() -> None:
    import ast
    import inspect

    from fitdocs.wellness.settings import load_wellness_settings

    document = (ROOT / "docs/configuration.md").read_text(encoding="utf-8")
    section = document.split("### `[wellness]`:", 1)[1].split("\n### ", 1)[0]
    documented = {
        line.split("|", 2)[1].strip().strip("`")
        for line in section.splitlines()
        if line.startswith("| `")
    }
    reader = ast.parse(inspect.getsource(load_wellness_settings))
    reader_keys = {
        node.args[0].value
        for node in ast.walk(reader)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "table"
        and node.func.attr == "get"
        and isinstance(node.args[0], ast.Constant)
    }
    assert documented == reader_keys
