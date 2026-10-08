"""Live-schema documentation regeneration controls."""

from __future__ import annotations

import ast
import os
import re
import runpy
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from typer.core import TyperOption
from typer.main import get_command

from fitdocs.cli import app
from fitdocs.index import store
from fitdocs.index.store import IndexConnection
from fitdocs.query.command import DEFAULT_MAX_ROWS, DEFAULT_TIMEOUT_S
from fitdocs.query.format import default_format
from fitdocs.query.sandbox import RESOURCE_SETTINGS
from fitdocs.query.schemaview import CatalogTable, read_catalog, render_reference
from tests.query._helpers import schema_only_index
from tests.query.conftest import HomeDirectory
from tests.test_docs_guarantees import _REQUIRED_ENTRY_POINT_LINKS

_START = "<!-- schema-reference:start -->"
_END = "<!-- schema-reference:end -->"
__all__ = ["read_catalog", "regenerate_schema_reference", "schema_only_index"]


def regenerate_schema_reference(page_path: Path) -> None:
    """Regenerate the page's reference block from a private live schema."""
    page = page_path.read_bytes().decode("utf-8")
    if page.count(_START) != 1 or page.count(_END) != 1:
        raise ValueError("schema reference must have one start and end marker")
    start = page.index(_START) + len(_START)
    end = page.index(_END)
    if start > end:
        raise ValueError("schema reference markers are reversed")

    caller_home = os.environ.get("HOME")
    try:
        with (
            TemporaryDirectory(prefix="fitdocs-schema-index-") as index_dir,
            TemporaryDirectory(prefix="fitdocs-schema-home-") as home_dir,
        ):
            os.environ["HOME"] = home_dir
            database = schema_only_index(Path(index_dir) / "index.duckdb")
            with store.open_index(database, read_only=True) as connection:
                catalog = read_catalog(connection)
            if not catalog:
                raise ValueError("schema reference catalog is empty")
            reference = render_reference(catalog)
    finally:
        if caller_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = caller_home

    updated = page[:start] + "\n" + reference + "\n" + page[end:]
    page_path.write_bytes(updated.encode("utf-8"))


def _marked_block(page: str) -> str:
    return page.split(_START, 1)[1].split(_END, 1)[0].strip("\n")


def _page_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "analytics.md"


def _section(page: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", page)
    assert match is not None
    return match.group(1)


def _bash_fitdocs_invocations(page: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for block in re.findall(r"(?ms)^```bash\s*\n(.*?)^```", page):
        for line in block.splitlines():
            if line.lstrip().startswith("#"):
                continue
            tokens = shlex.split(line, comments=True)
            if "fitdocs" not in tokens:
                continue
            command_index = tokens.index("fitdocs")
            commands.append(tokens[command_index + 1 :])
    return commands


def test_published_schema_reference_matches_live_catalog(
    tmp_path: Path, home_dir: HomeDirectory
) -> None:
    home_dir.assert_untouched()
    page_path = _page_path()
    page = page_path.read_text(encoding="utf-8")
    database = schema_only_index(tmp_path / "schema-oracle.duckdb")
    with store.open_index(database, read_only=True) as connection:
        tables = read_catalog(connection)
    assert tables
    assert _marked_block(page)
    assert _marked_block(page) == render_reference(tables)
    home_dir.assert_untouched()


def test_documented_query_contract_matches_the_implementation() -> None:
    page = _page_path().read_text(encoding="utf-8")
    outside_reference = page.split(_START, 1)[0] + page.split(_END, 1)[1]
    headings = re.findall(r"(?m)^## (.+)$", page)
    assert headings == [
        "Before you start",
        "Where the index lives",
        "Running a query",
        "The schema view",
        "The sandbox",
        "Opening the index from another DuckDB client",
        "Schema reference",
    ]

    start = _section(page, "Before you start")
    assert "`fitdocs index`" in start and "build" in start
    assert "`fitdocs index --rebuild`" in start

    location = _section(page, "Where the index lives")
    assert "`fitdocs query --schema`" in location
    normalized_location = " ".join(location.split())
    assert (
        "`FITDOCS_INDEX_DIR`, then `$XDG_CACHE_HOME/fitdocs/index`, "
        "then `~/.cache/fitdocs/index`."
    ) in normalized_location
    assert "`fitdocs index`" in location
    assert "print the index file path" in normalized_location

    running = _section(page, "Running a query")
    assert "one SQL statement as an argument" in running
    assert "`--file PATH`" in running
    assert "`-` to read the statement from standard input" in running
    assert all(f"`--format {name}`" in running for name in ("table", "csv", "json"))
    normalized_running = " ".join(running.split())
    assert (
        f"Without `--format`, fitdocs prints `{default_format(True).value}` "
        "when standard output is a terminal"
    ) in normalized_running
    assert (
        f"and `{default_format(False).value}` when output is piped or redirected"
    ) in normalized_running
    assert "SQL `NULL` appears as `NULL`" in normalized_running
    assert "empty unquoted field" in running and 'is `""`' in running
    assert "SQL `NULL` is `null`" in running
    assert f"**{DEFAULT_MAX_ROWS:,} rows**" in running
    assert "`--max-rows`" in running and "truncation" in running
    assert "closing notice" in running and "`truncated` to `true`" in running
    assert "A truncated result still exits 0." in running
    assert f"**{int(DEFAULT_TIMEOUT_S)} seconds**" in running
    assert "`--timeout`" in running
    assert "exit 0" in running and "exit 1" in running and "exit 2" in running
    normalized_exits = " ".join(running.split())
    assert "prints `Query interrupted.` on standard error, and exits 130" in (
        normalized_exits
    )
    assert "freshness notice" in running and "bring it up to date" in running

    schema = _section(page, "The schema view")
    assert "`fitdocs query --schema`" in schema
    assert "column types and descriptions" in schema
    assert "`--format json`" in schema and "does not support CSV" in schema

    sandbox = _section(page, "The sandbox")
    normalized_sandbox = " ".join(sandbox.split())
    assert "one query or `EXPLAIN`" in sandbox
    assert all(
        f"`{statement}`" in sandbox
        for statement in ("ATTACH", "COPY", "INSTALL", "LOAD")
    )
    assert "file and address access outside the index" in sandbox
    assert "Read-only access alone is not the sandbox" in sandbox
    assert "accidental or injected SQL" in sandbox
    assert "not a boundary against a local user" in sandbox
    assert "not a substitute for proper sandboxing" in normalized_sandbox
    memory = str(RESOURCE_SETTINGS["memory_limit"])
    spill_limit = str(RESOURCE_SETTINGS["max_temp_directory_size"])
    assert re.search(rf"\b{re.escape(memory[:-2])}\s?GB\b", normalized_sandbox)
    assert f"{RESOURCE_SETTINGS['threads']} DuckDB threads" in normalized_sandbox
    assert re.search(rf"\b{re.escape(spill_limit[:-2])}\s?GB\b", normalized_sandbox)
    assert "`query-spill-<pid>/`" in sandbox

    outside = _section(page, "Opening the index from another DuckDB client")
    normalized_outside = " ".join(outside.split())
    assert "bypasses fitdocs's query sandbox" in outside
    assert "not covered by fitdocs's no-network guarantee" in normalized_outside
    assert "each client its own" in outside and "temporary spill directory" in outside
    assert re.search(
        r"every fitdocs refresh reports the index busy until that client closes",
        normalized_outside,
    )
    bash = re.findall(r"(?ms)^```bash\s*\n(.*?)^```", outside)
    duckdb_lines = [
        line.strip()
        for block in bash
        for line in block.splitlines()
        if line.strip().startswith("duckdb ")
    ]
    assert len(duckdb_lines) == 1
    duckdb_args = shlex.split(duckdb_lines[0])
    assert "-readonly" in duckdb_args
    command_arg = duckdb_args[duckdb_args.index("-cmd") + 1]
    for setting in (
        "autoinstall_known_extensions = false",
        "autoload_known_extensions = false",
        "temp_directory = '/path/to/your-client-temp'",
    ):
        assert setting in command_arg

    python_blocks = re.findall(r"(?ms)^```python\s*\n(.*?)^```", outside)
    assert len(python_blocks) == 1
    python_tree = ast.parse(python_blocks[0])
    connections = [
        node
        for node in ast.walk(python_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "duckdb"
        and node.func.attr == "connect"
    ]
    assert len(connections) == 1
    keywords = {keyword.arg: keyword.value for keyword in connections[0].keywords}
    read_only = keywords.get("read_only")
    assert isinstance(read_only, ast.Constant)
    assert read_only.value is True
    config = keywords.get("config")
    assert isinstance(config, ast.Dict)
    settings: dict[str, str] = {}
    for key, value in zip(config.keys, config.values, strict=True):
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            settings[key.value] = value.value
    assert settings["autoinstall_known_extensions"] == "false"
    assert settings["autoload_known_extensions"] == "false"
    assert settings["temp_directory"] == "/path/to/your-client-temp"

    assert all(
        required in outside_reference
        for required in (
            "FITDOCS_INDEX_DIR",
            "XDG_CACHE_HOME",
            "read_only",
            "-readonly",
            "autoinstall_known_extensions",
            "autoload_known_extensions",
            "temp_directory",
        )
    )


def test_bash_fitdocs_commands_use_registered_commands_and_options() -> None:
    page = _page_path().read_text(encoding="utf-8")
    root_command = get_command(app)
    root_commands = getattr(root_command, "commands", None)
    assert isinstance(root_commands, dict)
    invocations = _bash_fitdocs_invocations(page)
    assert invocations

    for invocation in invocations:
        command_name, *arguments = invocation
        assert command_name in root_commands
        command = root_commands[command_name]
        assert command is not None
        options: dict[str, TyperOption] = {}
        for parameter in command.params:
            if isinstance(parameter, TyperOption):
                for spelling in (*parameter.opts, *parameter.secondary_opts):
                    options[spelling] = parameter

        index = 0
        while index < len(arguments):
            token = arguments[index]
            if token == "--":
                break
            if token.startswith("--") or (
                len(token) > 1 and token[0] == "-" and token[1].isalpha()
            ):
                spelling, separator, _value = token.partition("=")
                message = (
                    f"{command_name}: unregistered option {spelling!r} "
                    f"in {invocation!r}"
                )
                assert spelling in options, message
                option = options[spelling]
                if not option.is_flag and not separator:
                    index += 2
                    continue
            index += 1


def test_analytics_page_is_wired_into_docs_and_package_metadata() -> None:
    docs_index = (Path(__file__).resolve().parents[2] / "docs" / "index.md").read_text(
        encoding="utf-8"
    )
    analytics_row = docs_index.index("| [Analytics](analytics.md) |")
    contributing_row = docs_index.index("| [Contributing](../CONTRIBUTING.md) |")
    assert analytics_row < contributing_row
    assert "analytics.md" in _REQUIRED_ENTRY_POINT_LINKS

    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    project_urls = pyproject["project"]["urls"]
    assert (
        project_urls["Analytics"]
        == "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md"
    )


def test_regeneration_replaces_only_the_marked_live_schema_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.query import test_docs_analytics as regeneration

    page_path = tmp_path / "analytics.md"
    prefix = "prefix sentinel\n"
    suffix = "\nsuffix sentinel\n"
    page_path.write_text(
        prefix + _START + "\nstale schema\n" + _END + suffix, encoding="utf-8"
    )
    original = page_path.read_bytes()
    prior_home = os.environ.get("HOME")
    monkeypatch.setattr(
        "fitdocs.index.location.resolve_index_location",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("resolver used")),
    )
    expected_database = schema_only_index(tmp_path / "oracle.duckdb")
    with store.open_index(expected_database, read_only=True) as connection:
        expected_tables = read_catalog(connection)
    assert expected_tables
    expected = render_reference(expected_tables)

    private_tmp = Path(os.environ["TMPDIR"])
    index_paths: list[Path] = []
    helper_home_records: list[tuple[Path, bool]] = []
    original_schema_only_index = regeneration.schema_only_index

    def record_schema_only_index(path: Path) -> Path:
        index_paths.append(path)
        return original_schema_only_index(path)

    original_read_catalog = regeneration.read_catalog

    def record_read_catalog(
        connection: IndexConnection,
    ) -> tuple[CatalogTable, ...]:
        helper_home = Path(os.environ["HOME"])
        helper_tables = original_read_catalog(connection)
        helper_home_records.append((helper_home, helper_home.is_dir()))
        assert helper_tables
        return helper_tables

    monkeypatch.setattr(regeneration, "schema_only_index", record_schema_only_index)
    monkeypatch.setattr(regeneration, "read_catalog", record_read_catalog)

    regeneration.regenerate_schema_reference(page_path)

    assert os.environ.get("HOME") == prior_home
    assert len(index_paths) == 1
    assert len(helper_home_records) == 1
    helper_home, helper_home_was_directory = helper_home_records[0]
    assert index_paths[0].is_relative_to(private_tmp)
    assert helper_home.is_relative_to(private_tmp)
    assert helper_home_was_directory
    assert index_paths[0].parent != helper_home
    resulting = page_path.read_text(encoding="utf-8")
    assert original != page_path.read_bytes()
    assert resulting.startswith(prefix)
    assert resulting.endswith(suffix)
    assert _marked_block(resulting)
    assert _marked_block(resulting) == expected


@pytest.mark.parametrize(
    "malformed",
    [
        "prefix\nstale\n" + _END + "\nsuffix\n",
        "prefix\n" + _START + "\none\n" + _START + "\ntwo\n" + _END,
        "prefix\n" + _END + "\nstale\n" + _START + "\nsuffix\n",
    ],
)
def test_malformed_markers_fail_before_writing(tmp_path: Path, malformed: str) -> None:
    from tests.query import test_docs_analytics as regeneration

    page_path = tmp_path / "malformed.md"
    page_path.write_text(malformed, encoding="utf-8")
    original = page_path.read_bytes()
    prior_home = os.environ.get("HOME")

    with pytest.raises(ValueError):
        regeneration.regenerate_schema_reference(page_path)

    assert os.environ.get("HOME") == prior_home
    assert page_path.read_bytes() == original


def test_home_is_restored_when_catalog_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.query import test_docs_analytics as regeneration

    page_path = tmp_path / "failure.md"
    page_path.write_text(_START + "\nstale\n" + _END + "\n", encoding="utf-8")
    caller_home = tmp_path / "caller-home"
    caller_home.mkdir()
    monkeypatch.setenv("HOME", str(caller_home))
    seen_home: list[Path] = []

    def fail_catalog_read(
        connection: IndexConnection,
    ) -> tuple[CatalogTable, ...]:
        helper_home = Path(os.environ["HOME"])
        seen_home.append(helper_home)
        assert helper_home != caller_home
        assert helper_home.is_dir()
        raise RuntimeError("catalog read sentinel")

    monkeypatch.setattr(regeneration, "read_catalog", fail_catalog_read)
    with pytest.raises(RuntimeError, match="catalog read sentinel"):
        regeneration.regenerate_schema_reference(page_path)

    assert len(seen_home) == 1
    assert os.environ["HOME"] == str(caller_home)
    assert tuple(caller_home.iterdir()) == ()


def test_subprocess_page_argument_replaces_block_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page_path = tmp_path / "subprocess-page.md"
    prefix = "UNIQUE-PREFIX-α\n"
    suffix = "\nUNIQUE-SUFFIX-ω\n"
    page_path.write_text(
        prefix + _START + "\nold generated text\n" + _END + suffix,
        encoding="utf-8",
    )
    original = page_path.read_bytes()
    monkeypatch.setenv("HOME", str(tmp_path / "private-home"))
    Path(os.environ["HOME"]).mkdir()
    command = [sys.executable, "-m", "tests.query.test_docs_analytics", str(page_path)]

    first = subprocess.run(command, check=False, capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    after_first = page_path.read_bytes()
    assert after_first != original
    first_text = after_first.decode("utf-8")
    assert first_text.startswith(prefix)
    assert first_text.endswith(suffix)
    assert _marked_block(first_text)
    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert page_path.read_bytes() == after_first


def test_module_default_entrypoint_regenerates_its_private_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_root = tmp_path / "relocated"
    module_path = private_root / "tests" / "query" / "test_docs_analytics.py"
    module_path.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__), module_path)
    page_path = private_root / "docs" / "analytics.md"
    page_path.parent.mkdir(parents=True)
    original = (
        "private-prefix\n"
        + _START
        + "\nstale schema that differs\n"
        + _END
        + "\nprivate-suffix\n"
    ).encode("utf-8")
    page_path.write_bytes(original)
    assert _marked_block(original.decode("utf-8")) == "stale schema that differs"

    home = tmp_path / "private-home"
    home.mkdir()
    temp = tmp_path / "private-temp"
    temp.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setattr(sys, "argv", [str(module_path)])
    original_write_bytes = Path.write_bytes
    writes: list[Path] = []

    def guarded_write_bytes(path: Path, data: bytes) -> int:
        assert path.is_relative_to(private_root)
        writes.append(path)
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    runpy.run_path(str(module_path), run_name="__main__")

    updated = page_path.read_bytes()
    updated_text = updated.decode("utf-8")
    assert updated != original
    assert updated_text.startswith("private-prefix\n" + _START)
    assert updated_text.endswith(_END + "\nprivate-suffix\n")
    assert _marked_block(updated_text) != "stale schema that differs"
    assert writes == [page_path]
    monkeypatch.setattr(sys, "argv", [str(module_path), str(page_path), "extra"])
    with pytest.raises(SystemExit, match=r"usage: .* \[PAGE\]"):
        runpy.run_path(str(module_path), run_name="__main__")
    assert page_path.read_bytes() == updated
    assert tuple(home.iterdir()) == ()
    assert tuple(temp.iterdir()) == ()


def test_import_is_pure_in_an_isolated_home(tmp_path: Path) -> None:
    home = tmp_path / "empty-home"
    home.mkdir()
    temp = tmp_path / "empty-temp"
    temp.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["TMPDIR"] = str(temp)

    result = subprocess.run(
        [sys.executable, "-c", "import tests.query.test_docs_analytics"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert tuple(home.iterdir()) == ()
    assert tuple(temp.iterdir()) == ()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        regenerate_schema_reference(_page_path())
    elif len(sys.argv) == 2:
        regenerate_schema_reference(Path(sys.argv[1]))
    else:
        raise SystemExit("usage: python -m tests.query.test_docs_analytics [PAGE]")
