"""`docs/relay.md` bound to the deploy contract (Requirements 2.8, 9.2, 9.10, 16.4).

The operator page carries the environment table, the three version numbers,
the image constants, the commands and the probes. Each is parsed out of the
page and compared with the live `fitdocs_relay.contract` values, so a change
to the code that the page does not follow reds this file. The page's
relay-code table is bound on the fitdocs side
(`tests/connectors/test_relay_docs.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs_relay import contract
from fitdocs_relay.contract import EnvVar
from fitdocs_relay.seam import SEAM_VERSION
from fitdocs_relay.shared.relay_envelope import (
    ENVELOPE_VERSION,
    ROUTE_LIVEZ,
    ROUTE_READYZ,
)

RELAY_ROOT = Path(__file__).resolve().parents[1]
PAGE = RELAY_ROOT.parent / "docs" / "relay.md"
SMOKE_SCRIPT = RELAY_ROOT / "scripts" / "image_smoke.sh"
DERIVED_HEADING = "### Install a wrapper in a derived image"

ENV_HEADER = "| Variable | Required | Default | Secret | Meaning |"
COMMAND_HEADER = "| Command | Behaviour |"
PROBE_HEADER = "| Probe | Path | Answers |"


def page_text() -> str:
    assert PAGE.is_file(), f"the operator page is missing: {PAGE}"
    return PAGE.read_text(encoding="utf-8")


def table_rows(text: str, header: str) -> list[list[str]]:
    """The body rows of the one table whose header line is `header`, as cells."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == header]
    if len(starts) != 1:
        return []
    rows: list[list[str]] = []
    for line in lines[starts[0] + 2 :]:  # skip the header and its rule
        if not line.startswith("|"):
            break
        cells = re.split(r"(?<!\\)\|", line.strip())[1:-1]
        rows.append([cell.strip().replace("\\|", "|") for cell in cells])
    return rows


def default_cell(variable: EnvVar) -> str:
    if variable.default is None:
        return "—"
    if variable.default == "":
        return "empty"
    if variable.default.startswith("the "):
        return variable.default  # prose, not a literal value
    return f"`{variable.default}`"


def required_cell(variable: EnvVar) -> str:
    if variable.required:
        return "yes"
    if variable.required_with:
        names = " or ".join(f"`{name}`" for name in variable.required_with)
        return f"with {names}"
    return "no"


def environment_row(variable: EnvVar) -> list[str]:
    return [
        f"`{variable.name}`",
        required_cell(variable),
        default_cell(variable),
        "yes" if variable.secret else "no",
        variable.meaning,
    ]


def environment_problems(text: str) -> list[str]:
    """Every way the page's environment table differs from the code's."""
    found = table_rows(text, ENV_HEADER)
    wanted = [environment_row(variable) for variable in contract.ENVIRONMENT]
    problems = [f"missing row: {row[0]}" for row in wanted if row not in found]
    problems += [f"unexpected row: {row[0]}" for row in found if row not in wanted]
    if not problems and found != wanted:
        problems.append("the rows are not in the code's order")
    return problems


VERSION_LINES = {
    "Deploy contract version": contract.DEPLOY_CONTRACT_VERSION,
    "Envelope version": ENVELOPE_VERSION,
    "Seam version": SEAM_VERSION,
}


def version_problems(text: str) -> list[str]:
    problems = []
    for label, number in VERSION_LINES.items():
        found = re.findall(rf"^- {re.escape(label)}: (\S+)$", text, re.MULTILINE)
        if found != [str(number)]:
            problems.append(f"{label}: page says {found}, code says {number}")
    return problems


IMAGE_LINES = {
    "Image user id": str(contract.IMAGE_USER_ID),
    "Image port": str(contract.IMAGE_PORT),
    "Image entrypoint": " ".join(contract.IMAGE_ENTRYPOINT),
    "Image default command": " ".join(contract.IMAGE_DEFAULT_COMMAND),
    "Image Python environment": contract.IMAGE_ENVIRONMENT,
}


def image_problems(text: str) -> list[str]:
    problems = []
    for label, value in IMAGE_LINES.items():
        found = re.findall(rf"^- {re.escape(label)}: `([^`]*)`$", text, re.MULTILINE)
        if found != [value]:
            problems.append(f"{label}: page says {found}, code says {value}")
    return problems


def command_problems(text: str) -> list[str]:
    names = [row[0].strip("`").split()[0] for row in table_rows(text, COMMAND_HEADER)]
    if names != list(contract.COMMANDS):
        return [f"commands: page lists {names}, code has {list(contract.COMMANDS)}"]
    return []


def probe_problems(text: str) -> list[str]:
    paths = [row[1] for row in table_rows(text, PROBE_HEADER)]
    wanted = [f"`{ROUTE_LIVEZ}`", f"`{ROUTE_READYZ}`"]
    if paths != wanted:
        return [f"probes: page lists {paths}, code has {wanted}"]
    return []


def derived_steps_from_script() -> list[str]:
    """The smoke script's derived-image Dockerfile, with the page's placeholders."""
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    start = text.index("<<DOCKERFILE")
    end = text.index("\nDOCKERFILE\n")
    steps = text[start:end].splitlines()[1:]
    substitutions = {
        "$ENVIRONMENT_PATH": contract.IMAGE_ENVIRONMENT,
        "$USER_ID": str(contract.IMAGE_USER_ID),
        "$IMAGE": "<relay image>",
        "$UV_IMAGE": "<uv image>",
    }
    rendered = []
    for step in steps:
        for variable, value in substitutions.items():
            step = step.replace(variable, value)
        rendered.append(step)
    return rendered


def derived_steps_on_page(text: str) -> list[str]:
    """The fenced block under the derived-image heading, one line per step."""
    if text.count(DERIVED_HEADING) != 1:
        return []
    section = text.split(DERIVED_HEADING, 1)[1]
    blocks = re.findall(r"```dockerfile\n(.*?)```", section, re.DOTALL)
    return blocks[0].splitlines() if blocks else []


def derived_problems(text: str) -> list[str]:
    wanted = derived_steps_from_script()
    found = derived_steps_on_page(text)
    if found != wanted:
        return [f"derived-image steps: page has {found}, the smoke run has {wanted}"]
    return []


# --- the real page ---------------------------------------------------------


def test_the_environment_table_is_the_codes_table() -> None:
    assert environment_problems(page_text()) == []


def test_the_page_states_the_three_versions() -> None:
    assert version_problems(page_text()) == []


def test_the_page_states_the_image_constants() -> None:
    assert image_problems(page_text()) == []


def test_the_page_lists_the_commands_in_order() -> None:
    assert command_problems(page_text()) == []


def test_the_page_lists_the_probes() -> None:
    assert probe_problems(page_text()) == []


def test_the_derived_image_steps_are_the_smoke_runs_steps() -> None:
    assert len(derived_steps_from_script()) == 6, "the script was read wrongly"
    assert derived_problems(page_text()) == []


# --- the binding can fail ---------------------------------------------------


@pytest.mark.parametrize("index", range(len(contract.ENVIRONMENT)))
def test_deleting_any_environment_row_reds_the_binding(index: int) -> None:
    lines = page_text().splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith("| `FITDOCS_RELAY_")]
    assert len(rows) == len(contract.ENVIRONMENT), "the row scan found the wrong lines"
    del lines[rows[index]]
    problems = environment_problems("\n".join(lines))
    assert len(problems) == 1
    assert contract.ENVIRONMENT[index].name in problems[0]


def test_a_two_name_tuple_renders_joined_with_or() -> None:
    both = EnvVar("FITDOCS_RELAY_X", False, None, False, "m", ("A_ONE", "B_TWO"))
    one = EnvVar("FITDOCS_RELAY_Y", False, None, False, "m", ("A_ONE",))
    assert environment_row(both)[1] == "with `A_ONE` or `B_TWO`"
    assert environment_row(one)[1] == "with `A_ONE`"
    page = page_text()
    assert "| with `FITDOCS_RELAY_STRAVA_CLIENT_ID` |" in page


def test_dropping_the_required_with_rendering_reds_the_binding() -> None:
    changed = page_text().replace(
        "| with `FITDOCS_RELAY_STRAVA_CLIENT_ID` |", "| no |", 1
    )
    assert changed != page_text(), "the fixture changed nothing"
    assert len(environment_problems(changed)) == 2


def test_changing_a_cell_reds_the_binding() -> None:
    changed = page_text().replace("| `20` |", "| `21` |", 1)
    assert changed != page_text(), "the fixture changed nothing"
    assert environment_problems(changed) != []


def test_an_extra_environment_row_reds_the_binding() -> None:
    text = page_text()
    extra = "| `FITDOCS_RELAY_INVENTED` | no | empty | no | Not a variable |"
    lines = text.splitlines()
    last = max(
        i for i, line in enumerate(lines) if line.startswith("| `FITDOCS_RELAY_")
    )
    lines.insert(last + 1, extra)
    assert environment_problems("\n".join(lines)) == [
        "unexpected row: `FITDOCS_RELAY_INVENTED`"
    ]


def test_swapping_two_rows_reds_the_binding() -> None:
    lines = page_text().splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith("| `FITDOCS_RELAY_")]
    lines[rows[0]], lines[rows[1]] = lines[rows[1]], lines[rows[0]]
    assert environment_problems("\n".join(lines)) == [
        "the rows are not in the code's order"
    ]


def test_a_wrong_version_reds_the_binding() -> None:
    original = page_text()
    text = original.replace(
        f"- Seam version: {SEAM_VERSION}", f"- Seam version: {SEAM_VERSION + 1}"
    )
    assert text != original, "the fixture changed nothing"
    assert version_problems(text) == [
        f"Seam version: page says ['{SEAM_VERSION + 1}'], code says {SEAM_VERSION}"
    ]


def test_a_dropped_version_line_reds_the_binding() -> None:
    original = page_text()
    text = original.replace("- Envelope version:", "Envelope version:")
    assert text != original, "the fixture changed nothing"
    assert version_problems(text) == [
        f"Envelope version: page says [], code says {ENVELOPE_VERSION}"
    ]


def test_a_wrong_image_constant_reds_the_binding() -> None:
    original = page_text()
    text = original.replace(
        f"- Image port: `{contract.IMAGE_PORT}`", "- Image port: `9090`"
    )
    assert text != original, "the fixture changed nothing"
    assert image_problems(text) == [
        f"Image port: page says ['9090'], code says {contract.IMAGE_PORT}"
    ]


def test_a_dropped_image_line_reds_the_binding() -> None:
    original = page_text()
    text = original.replace("- Image user id:", "Image user id:")
    assert text != original, "the fixture changed nothing"
    assert image_problems(text) == [
        f"Image user id: page says [], code says {contract.IMAGE_USER_ID}"
    ]


# --- statements the page must make -----------------------------------------


def section(text: str, heading: str) -> str:
    assert text.count(heading + "\n") == 1, f"{heading!r} is not exactly once"
    rest = text.split(heading + "\n", 1)[1]
    return re.split(r"^## ", rest, maxsplit=1, flags=re.MULTILINE)[0]


STATEMENTS = {
    "pepper": ("## Pepper rotation", "invalidates every existing relay token"),
    "compatibility": (
        "# The relay: operator guide and contract",
        "is not governed by fitdocs's [compatibility policy]",
    ),
    "replica": ("### One replica, stop-then-start", "Run exactly one serving instance"),
    "network filesystem": (
        "### One replica, stop-then-start",
        "a database file on a network filesystem shared between hosts",
    ),
}


def statement_problems(text: str) -> list[str]:
    problems = []
    for name, (heading, sentence) in STATEMENTS.items():
        body = " ".join(section(text, heading).split())
        if sentence not in body:
            problems.append(name)
    return problems


def test_the_page_makes_its_required_statements() -> None:
    assert statement_problems(page_text()) == []


def test_reversing_the_pepper_statement_reds_the_pin() -> None:
    original = page_text()
    text = original.replace("invalidates every existing relay token", "is allowed")
    assert text != original, "the fixture changed nothing"
    assert statement_problems(text) == ["pepper"]


def test_reversing_the_compatibility_statement_reds_the_pin() -> None:
    original = page_text()
    text = original.replace("is not governed by", "is governed by")
    assert text != original, "the fixture changed nothing"
    assert statement_problems(text) == ["compatibility"]


def test_dropping_the_shared_filesystem_limit_reds_the_pin() -> None:
    original = page_text()
    text = original.replace("network filesystem shared between hosts", "disk")
    assert text != original, "the fixture changed nothing"
    assert statement_problems(text) == ["network filesystem"]


def test_a_dropped_command_reds_the_binding() -> None:
    lines = [
        line
        for line in page_text().splitlines()
        if not line.startswith("| `new-pepper`")
    ]
    assert command_problems("\n".join(lines)) != []


def test_a_dropped_probe_reds_the_binding() -> None:
    lines = [
        line
        for line in page_text().splitlines()
        if not line.startswith("| Readiness |")
    ]
    assert probe_problems("\n".join(lines)) != []


def test_a_changed_derived_step_reds_the_binding() -> None:
    text = page_text()
    changed = text.replace("USER root\n", "USER nobody\n", 1)
    assert changed != text, "the fixture changed nothing"
    assert len(derived_problems(changed)) == 1
    dropped = text.replace("COPY . /tmp/wrapper\n", "", 1)
    assert dropped != text, "the fixture changed nothing"
    assert len(derived_problems(dropped)) == 1
