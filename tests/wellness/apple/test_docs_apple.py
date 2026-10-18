"""Rendered Apple Health import documentation contracts."""

from __future__ import annotations

import re
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from fitdocs.wellness.formats.apple import ARCHIVED_SUFFIX, FORMAT, FORMAT_ID
from fitdocs.wellness.formats.apple.reduce import POLICIES, DailyRule, DayRule, Writer
from fitdocs.wellness.registry import candidate_suffixes, default_source_order
from tests._changelog_view import V0_1_0, unreleased_since
from tests.wellness.test_docs_wellness import (
    DAY_RULE,
    DAY_STATEMENT,
    _validate_invocation,
)

ROOT = Path(__file__).resolve().parents[3]
MARKDOWN = MarkdownIt("commonmark").enable("table")
WRITERS = {Writer.WATCH: "Apple Watch", Writer.PHONE: "iPhone", Writer.OTHER: "other"}
DAYS = {
    DayRule.WAKE_DATE: "wake date of each segment’s end (wellness day)",
    DayRule.NIGHT_OF_READING: "night of the reading (wellness day)",
    DayRule.START_DATE: "local start date (wellness day)",
}
DAILY = {
    DailyRule.SLEEP_NIGHT: "total asleep; stages only for a staged night",
    DailyRule.ASLEEP_MEAN: "mean of readings asleep, rounded to 0.1",
    DailyRule.FINAL: "latest end, then latest creation",
    DailyRule.LARGEST_TOTAL: "largest single-source day total",
    DailyRule.LATEST: "latest start, then latest creation; rounded to 0.01 kg",
}
DEFINITIONS = {
    "resting_hr_bpm": (
        "Apple’s sedentary estimate from background heart-rate readings, in bpm"
    ),
    "hrv_sdnn_ms": (
        "SDNN: standard deviation of normal-to-normal heartbeat intervals, "
        "in ms; not rMSSD"
    ),
    "respiration_brpm": "Breathing rate, in breaths per minute",
    "spo2_pct": (
        "Blood-oxygen saturation; the exported fraction is converted to percent"
    ),
    "vo2max_ml_per_kg_min": (
        "Estimated maximum oxygen consumption, in millilitres per kilogram per minute"
    ),
    "steps": "Number of steps",
    "weight_kg": "Body mass, converted to kilograms",
    "sleep_s": (
        "Total asleep time: core, deep, REM and unspecified asleep; excludes "
        "awake and in-bed time"
    ),
    "sleep_deep_s": "Time in Apple’s deep sleep stage",
    "sleep_light_s": "Time in Apple’s core sleep stage, mapped to light sleep",
    "sleep_rem_s": "Time in Apple’s REM sleep stage",
    "sleep_awake_s": "Time awake within the staged night",
}


def _tokens(path: str) -> list[Token]:
    text = (ROOT / path).read_text(encoding="utf-8")
    if path == "CHANGELOG.md":
        text = unreleased_since(text, V0_1_0)
    return MARKDOWN.parse(text)


def _visible(tokens: list[Token]) -> str:
    return " ".join(
        " ".join(
            "".join(
                " " if child.type in {"softbreak", "hardbreak"} else child.content
                for child in token.children or []
                if child.type in {"text", "code_inline", "softbreak", "hardbreak"}
            )
            for token in tokens
            if token.type == "inline"
        ).split()
    )


def _section(tokens: list[Token], heading: str) -> list[Token]:
    for index, token in enumerate(tokens):
        if (
            token.type == "heading_open"
            and _visible(tokens[index + 1 : index + 2]) == heading
        ):
            end = next(
                (
                    i
                    for i in range(index + 3, len(tokens))
                    if tokens[i].type == "heading_open" and tokens[i].tag <= token.tag
                ),
                len(tokens),
            )
            return tokens[index + 3 : end]
    return []


def _apple() -> list[Token]:
    return _section(_tokens("docs/wellness.md"), "Apple Health")


def _tables(tokens: list[Token]) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    for index, token in enumerate(tokens):
        if token.type == "table_open":
            tables.append([])
        elif token.type == "tr_open":
            tables[-1].append([])
        elif token.type in {"th_open", "td_open"}:
            tables[-1][-1].append(_visible(tokens[index + 1 : index + 2]))
    return tables


def _links(tokens: list[Token]) -> list[tuple[str, str]]:
    result = []
    for token in tokens:
        children = token.children or []
        for index, child in enumerate(children):
            if child.type == "link_open":
                end = next(
                    i
                    for i in range(index + 1, len(children))
                    if children[i].type == "link_close"
                )
                label = "".join(
                    " " if c.type in {"softbreak", "hardbreak"} else c.content
                    for c in children[index + 1 : end]
                    if c.type in {"text", "code_inline", "softbreak", "hardbreak"}
                ).strip()
                if label:
                    result.append((label, str(child.attrGet("href") or "")))
    return result


def _day_links() -> list[list[tuple[str, str]]]:
    tokens = _section(_apple(), "Types and definitions")
    for start, token in enumerate(tokens):
        if token.type != "table_open":
            continue
        end = next(
            i for i in range(start + 1, len(tokens)) if tokens[i].type == "table_close"
        )
        table = tokens[start : end + 1]
        if _tables(table)[0][0] != [
            "Apple type",
            "Metrics",
            "Writers",
            "Day rule",
            "Daily rule",
        ]:
            continue
        result = []
        column = 0
        for index, cell in enumerate(table):
            if cell.type == "tr_open":
                column = 0
            elif cell.type == "td_open":
                if column == 3:
                    result.append(_links(table[index + 1 : index + 2]))
                column += 1
        return result
    return []


def test_type_table_equals_policies() -> None:
    expected = [["Apple type", "Metrics", "Writers", "Day rule", "Daily rule"]]
    expected.extend(
        [
            kind.value,
            ", ".join(metric.value for metric in policy.metrics),
            ", ".join(WRITERS[writer] for writer in Writer if writer in policy.writers),
            DAYS[policy.day_rule],
            DAILY[policy.daily_rule],
        ]
        for kind, policy in POLICIES.items()
    )
    assert (
        next((table for table in _tables(_apple()) if table[0][0] == "Apple type"), [])
        == expected
    )


def test_metric_definitions() -> None:
    assert next(
        (
            table
            for table in _tables(_apple())
            if table[0] == ["Metric", "Apple definition"]
        ),
        [],
    ) == [
        ["Metric", "Apple definition"],
        *[[metric, meaning] for metric, meaning in DEFINITIONS.items()],
    ]


def test_how_to_export() -> None:
    text = _visible(_section(_apple(), "How to export"))
    assert (
        "On your iPhone, open Health, tap your profile picture, then Export "
        "All Health Data → Export. Put export.zip into the configured inbox "
        "and run fitdocs sync."
    ) in text


def test_apple_suffixes() -> None:
    export = _visible(_section(_apple(), "How to export"))
    assert frozenset(re.findall(r"(?<![\w.])\.\w+\b", export)) == FORMAT.suffixes


def test_extract_path() -> None:
    extract = _section(_apple(), "Extract and corrections")
    assert f"wellness-archive/{FORMAT_ID}/<sha256>{ARCHIVED_SUFFIX}" in _visible(
        extract
    )


def test_day_rule_and_references() -> None:
    pages = sorted((ROOT / "docs").rglob("*.md"))
    assert (
        pages
        and sum(
            _visible(MARKDOWN.parse(page.read_text(encoding="utf-8"))).count(
                DAY_STATEMENT
            )
            for page in pages
        )
        == 1
    )
    assert DAY_RULE in _visible(_section(_tokens("docs/wellness.md"), "Wellness day"))
    assert _day_links() == [[("wellness day", "#wellness-day")]] * len(POLICIES)
    assert "18:00" not in _visible(_apple())


def test_apple_commands_registered() -> None:
    commands = [
        child.content
        for token in _apple()
        for child in token.children or []
        if child.type == "code_inline" and child.content.startswith("fitdocs ")
    ]
    assert commands
    for command in commands:
        _validate_invocation(command.split()[1:])


def test_inbox_suffixes() -> None:
    section = _visible(_section(_tokens("docs/inbox.md"), "Safeguards"))
    sentence = section.split("currently ", 1)[-1].split("with case-insensitive", 1)[0]
    assert frozenset(re.findall(r"\.[a-z]+", sentence)) == candidate_suffixes()


def test_source_order() -> None:
    table = next(
        (
            table
            for table in _tables(
                _section(
                    _tokens("docs/configuration.md"),
                    "[wellness]: source precedence for wellness",
                )
            )
            if table[0] == ["Key", "Meaning", "Default"]
        ),
        [],
    )
    default = next((row[2] for row in table[1:] if row[0] == "precedence"), "")
    assert (
        tuple(
            default.partition("built-in order: ")[2].removesuffix(")").split(", then ")
        )
        == default_source_order()
    )
    assert (
        "Today that puts garmin-export before apple-health before intervals-icu."
        in _visible(_section(_tokens("docs/wellness.md"), "Source precedence"))
    )


def test_skill_unrecognized_meaning() -> None:
    table = next(
        (
            table
            for table in _tables(
                _section(
                    _tokens("src/fitdocs/skills/fitdocs-workouts/SKILL.md"),
                    "Reading the report",
                )
            )
            if table[0] == ["Channel", "Field", "Meaning", "Do"]
        ),
        [],
    )
    assert next((row[2] for row in table[1:] if row[1] == "unrecognized"), "") == (
        "No supported wellness format recognized the .json, .zip or .xml "
        "file; it stays in the inbox."
    )


PROSE = {
    "Writers and daily rules": (
        (
            "A writing source is classified from all its device evidence: "
            "manufacturer Apple Inc. and model Watch wins over model iPhone; "
            "otherwise it is other. Records without a device inherit their "
            "writing source’s class."
        ),
        (
            "A third-party watch app that names an Apple Watch as its device can "
            "therefore be misclassified as Apple Watch."
        ),
        (
            "Other apps’ values, except body weight, are excluded; import those "
            "platforms’ own sources instead. Writers are selected from export "
            "content, independently of record order, and different writers’ "
            "values are never added together."
        ),
        (
            "Resting HR and VO2max use the final estimate because Apple can "
            "revise its estimate during the day. Equal end times use latest "
            "creation; remaining ties use record content."
        ),
        (
            "HRV, respiration and SpO2 average only readings whose end lies in "
            "Apple Watch asleep time, start inclusive and end exclusive, rounded "
            "to one decimal place. This keeps each day’s measure tied to sleep "
            "rather than daytime activity. No watch sleep, or no qualifying "
            "reading, means no value; a night without the watch supplies no HRV."
        ),
        (
            "Steps take the largest single-writer daily sum to avoid counting "
            "the phone and watch together. Weight takes the latest measurement "
            "across every writer, including manual entries and scales, because "
            "the last measurement is the daily observation; creation time and "
            "then content break ties. Weight is converted to kilograms and "
            "rounded to two decimal places."
        ),
        (
            "Every imported value has source apple-health and origin apple, "
            "except weight, whose origin is unknown. SDNN is never converted to "
            "rMSSD."
        ),
    ),
    "Sleep and naps": (
        (
            "Sleep uses Apple Watch records if that night contains any watch "
            "asleep time, otherwise iPhone records; they are never combined "
            "within a night."
        ),
        (
            "Overlapping segments count once, with priority deep, REM, core, "
            "awake, then unspecified asleep. Core maps to light; deprecated "
            "asleep maps to unspecified asleep. In-bed time contributes nothing."
        ),
        (
            "Total sleep includes core, deep, REM and unspecified asleep, "
            "excluding awake. Only a night with core, deep or REM time supplies "
            "stage and awake values; an older unstaged night supplies total "
            "sleep only. A zero total supplies no sleep values."
        ),
        (
            "Naps count toward the same night under the linked wellness day "
            "rule; this is not restricted to one main sleep session."
        ),
    ),
    "Extract and corrections": (
        (
            "The archive keeps a deterministic gzip-compressed UTF-8 JSON Lines "
            "extract at wellness-archive/apple-health/<sha256>.jsonl.gz, named "
            "by the original export’s SHA-256."
        ),
        (
            "Its header records the original SHA-256, byte size and stated "
            "export date. Each supported raw record retains type, writing "
            "source, source version, device, unit, creation/start/end times, "
            "value and metadata; the device description’s memory address is "
            "removed. A trailer records record counts and correction counts."
        ),
        (
            "It contains no personal profile (date of birth, biological sex, "
            "blood type or skin type), workouts, routes, clinical records, ECGs, "
            "audiograms or unsupported record types. It contains no run date, "
            "original filename/path or machine-specific value."
        ),
        (
            "Read it without fitdocs using gzip -dc "
            "wellness-archive/apple-health/<sha256>.jsonl.gz; there is one JSON "
            "record per line."
        ),
        (
            "Corrections remove a malformed document-type declaration, remove "
            "illegal XML control characters, and keep the first occurrence of a "
            "duplicate WorkoutStatistics attribute. Removing a control character "
            "changes the text it was in. Each correction kind is counted in the "
            "extract; the original export is never modified. Other malformed XML "
            "fails the whole import with a line number and leaves the series "
            "unchanged."
        ),
    ),
    "Later exports and the original": (
        (
            "The latest export date replaces the earlier export entirely, "
            "including any day the later export no longer holds. Every Apple "
            "Health export in the archive is assumed to belong to the same "
            "athlete."
        ),
        (
            "Superseded extracts remain unchanged in the archive and are listed "
            "as superseded in the manifest. An older export is archived but does "
            "not replace a newer one. Zip and bare XML copies use a "
            "deterministic archive-reference tie-break."
        ),
        (
            "The series is rebuilt from the extract alone; the original is never "
            "needed again. The original follows inbox disposition: left in place "
            "by default, or moved to processed_dir, never deleted by fitdocs. "
            "Move it out of an iCloud inbox yourself to avoid re-hashing it on "
            "every drain."
        ),
    ),
    "Time, memory and exclusions": (
        (
            "Allow about 10–20 seconds per GB of main export.xml on a recent "
            "computer, plus about one second per GB for each of two framework "
            "hashes. Large imports can take minutes. A terminal reports the "
            "percentage of the main XML document read, at most once per whole "
            "percent."
        ),
        (
            "XML is streamed without unpacking to disk; import memory stays flat "
            "with XML size, under 100 MiB. Daily reduction additionally retains "
            "sleep segments and spot readings: tens of MB for a decade, "
            "depending on history."
        ),
        (
            "Import and rebuild are offline. No real export or extract belongs "
            "in the fitdocs repository."
        ),
        (
            "Workouts continue to arrive as .fit files through HealthFit. Heart "
            "rate, walking heart rate, wrist temperature, nutrition, clinical "
            "records, ECGs, audiograms, Sleep Score, Apple’s rMSSD type and "
            "third-party file exporters are not imported."
        ),
    ),
}


def test_required_prose() -> None:
    missing = {
        heading: [
            statement
            for statement in statements
            if statement not in _visible(_section(_apple(), heading))
        ]
        for heading, statements in PROSE.items()
    }
    assert missing == {heading: [] for heading in PROSE}


def test_unrecognized_and_progress() -> None:
    text = _visible(_section(_tokens("docs/inbox.md"), "Safeguards"))
    assert (
        "Other ZIP files (including Garmin export ZIPs) and unrelated XML "
        "are reported as unrecognized and left in place; silence them with "
        "[inbox] ignore."
    ) in text
    assert (
        "An Apple Health import can take minutes; on a terminal, progress "
        "shows the percentage of its main XML document read."
    ) in _visible(_section(_tokens("docs/inbox.md"), "Drain semantics"))


def test_release_notes() -> None:
    unreleased = _section(_tokens("CHANGELOG.md"), "[Unreleased]")
    added = _visible(_section(unreleased, "Added"))
    changed = _visible(_section(unreleased, "Changed"))
    assert (
        "Apple Health import reads supported wellness types from export.zip "
        "or bare export.xml, archives a compact extract, and uses the latest "
        "export date to supersede earlier exports entirely."
    ) in added
    assert (
        "Inbox interface: .zip and .xml files are wellness candidates. "
        "Unrelated ZIP or XML stays in place and is reported as "
        "unrecognized; add it to [inbox] ignore to silence it."
    ) in changed
    assert (
        "The default wellness source order gains apple-health between "
        "garmin-export and intervals-icu. The first fitdocs sync or fitdocs "
        "regen after upgrading rebuilds the series once."
    ) in changed
    assert (
        "Apple Health guide",
        (
            "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wellness.md#apple-health"
        ),
    ) in _links(_section(unreleased, "Added"))
