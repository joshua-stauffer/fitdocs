"""Pins the statements that publish derived analytics and their amendment."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_changelog_publishes_derived_tables_under_unreleased() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text()
    unreleased = " ".join(
        changelog.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0].split()
    ).lower()
    assert "### added" in unreleased
    assert all(
        phrase in unreleased
        for phrase in (
            "best efforts",
            "daily and weekly load series",
            "benchmark timeline",
            "training blocks",
            "run `fitdocs index` once after upgrading",
        )
    ), unreleased


def test_structure_names_the_derived_index_package() -> None:
    structure = (ROOT / ".kiro/steering/structure.md").read_text()
    index_paragraph = " ".join(
        structure.split("- `index`", 1)[1].split("\n- ", 1)[0].split()
    )
    assert "index.derived" in index_paragraph


def test_fit_ingest_requirement_numbers_are_unique_and_consecutive() -> None:
    requirements = (ROOT / ".kiro/specs/fit-ingest/requirements.md").read_text()
    numbers = [
        int(number)
        for number in re.findall(r"^### Requirement (\d+):", requirements, re.M)
    ]
    assert numbers == list(range(1, max(numbers) + 1))


def test_fit_ingest_amendment_headings_are_unique_and_consecutive() -> None:
    requirements = (ROOT / ".kiro/specs/fit-ingest/requirements.md").read_text()
    numbers = [
        int(number)
        for number in re.findall(r"^## Amendment (\d+)\b", requirements, re.M)
    ]
    assert numbers == list(range(1, 7))


def test_fit_ingest_final_amendment_heading_attributes_derived() -> None:
    requirements = (ROOT / ".kiro/specs/fit-ingest/requirements.md").read_text()
    headings = re.findall(r"^## Amendment \d+.*$", requirements, re.M)
    assert headings[-1].startswith("## Amendment 6 ")
    assert "landed by analytics-derived" in headings[-1]


def test_fit_ingest_amendment_records_the_library_rule_and_test_paths() -> None:
    spec = json.loads((ROOT / ".kiro/specs/fit-ingest/spec.json").read_text())
    amendments = spec["amendments"]
    amendment = amendments[-1]
    assert "Amendment 6" in amendment["requirement"]
    assert "landed by analytics-derived" in amendment["requirement"]
    assert "tests/metrics/test_mean_max.py" in json.dumps(amendment["tests"])
    assert "tests/metrics/test_mean_max_sources.py" in json.dumps(amendment["tests"])
    requirements = (ROOT / ".kiro/specs/fit-ingest/requirements.md").read_text()
    assert "### Requirement 19: Best Efforts" in requirements
    requirement_19 = " ".join(
        requirements.split("### Requirement 19: Best Efforts", 1)[1].split()
    )
    assert "at library level" in requirement_19
    assert "outside the enumeration in criterion 15.6" in requirement_19
    assert "under criterion 15.8" in requirement_19
