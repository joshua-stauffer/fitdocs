"""The conformance harness: backend fixture, environment isolation, the require rule."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from fitdocs_relay.config import PostgresTarget, SqliteTarget

HARNESS = Path(__file__).parents[1] / "conftest.py"
URL_VARIABLE = "FITDOCS_RELAY_TEST_POSTGRES_URL"
REQUIRE_VARIABLE = "FITDOCS_RELAY_REQUIRE_POSTGRES"
UNREACHABLE_URL = "postgresql://127.0.0.1:1/none?connect_timeout=2"

CHILD_TEST = """
import os
from pathlib import Path

# Read at collection, before any fixture runs: what the process started with.
AT_COLLECTION = sorted(n for n in os.environ if n.startswith("FITDOCS_RELAY_"))


def test_sentinel(database_target):
    out = os.environ.get("CHILD_OUT")
    if out and hasattr(database_target, "conninfo"):
        Path(out).write_text(database_target.conninfo, encoding="utf-8")
    assert database_target is not None


def test_environment_is_clean():
    assert AT_COLLECTION == [
        "FITDOCS_RELAY_PLANTED",
        "FITDOCS_RELAY_REQUIRE_POSTGRES",
        "FITDOCS_RELAY_TEST_POSTGRES_URL",
    ]
    leaked = sorted(n for n in os.environ if n.startswith("FITDOCS_RELAY_"))
    assert leaked == []
"""


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("FITDOCS_RELAY_")}


def _run_child(
    tmp_path: Path,
    extra_env: dict[str, str],
    *args: str,
    source: str | None = None,
    shim: dict[str, str] | None = None,
) -> str:
    """Run pytest on a copy of the harness plus CHILD_TEST; return its output."""
    project = tmp_path / f"child-{uuid.uuid4().hex[:8]}"
    project.mkdir()
    (project / "conftest.py").write_bytes(HARNESS.read_bytes())
    (project / "test_child.py").write_text(
        CHILD_TEST if source is None else source, encoding="utf-8"
    )
    env = _clean_env() | extra_env
    if shim:
        shim_dir = project / "shim"
        for relative, text in shim.items():
            (shim_dir / relative).parent.mkdir(parents=True, exist_ok=True)
            (shim_dir / relative).write_text(text, encoding="utf-8")
        env["PYTHONPATH"] = str(shim_dir)
    done = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "-v",
            "-rs",
            "--rootdir",
            str(project),
            *args,
            str(project),
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return done.stdout + done.stderr


def _outcome(output: str, test_id: str) -> str:
    """PASSED, FAILED, SKIPPED or ERROR for the one `-v` line naming `test_id`."""
    prefix = f"test_child.py::{test_id} "
    lines = [line for line in output.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, f"{test_id}: {lines}\n{output}"
    return lines[0][len(prefix) :].split(" ", 1)[0]


def _skip_reasons(output: str) -> list[str]:
    return [
        line.split(": ", 1)[1]
        for line in output.splitlines()
        if line.startswith("SKIPPED [")
    ]


# --- the sentinel: runs on every backend ----------------------------------


def _schema_of(conninfo: str) -> str:
    from psycopg.conninfo import conninfo_to_dict

    options = str(conninfo_to_dict(conninfo)["options"])
    assert options.startswith("-csearch_path=")
    return options.removeprefix("-csearch_path=")


def _key(target: SqliteTarget | PostgresTarget) -> str:
    if isinstance(target, SqliteTarget):
        return str(target.path)
    return target.conninfo


@pytest.fixture(scope="module")
def seen_targets() -> list[str]:
    return []


def test_sentinel_the_backend_fixture_yields_a_fresh_target(
    database_target: SqliteTarget | PostgresTarget,
    tmp_path: Path,
    seen_targets: list[str],
) -> None:
    assert _key(database_target) not in seen_targets
    seen_targets.append(_key(database_target))
    if isinstance(database_target, SqliteTarget):
        assert database_target.path.parent == tmp_path
        assert not database_target.path.exists()
        return
    import psycopg

    schema = _schema_of(database_target.conninfo)
    assert schema.startswith("relay_test_")
    with psycopg.connect(database_target.conninfo, autocommit=True) as conn:
        assert conn.execute("SELECT current_schema()").fetchone() == (schema,)
        tables = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = %s",
            (schema,),
        ).fetchone()
    assert tables == (0,)


def test_targets_are_distinct_per_test(
    database_target: SqliteTarget | PostgresTarget,
    seen_targets: list[str],
) -> None:
    assert _key(database_target) not in seen_targets
    seen_targets.append(_key(database_target))


# --- the require rule, through a child pytest -------------------------------


def test_environment_is_isolated_for_every_test(tmp_path: Path) -> None:
    planted = {
        "FITDOCS_RELAY_PLANTED": "1",
        REQUIRE_VARIABLE: "0",
        URL_VARIABLE: UNREACHABLE_URL,
    }
    output = _run_child(tmp_path, planted, "-k", "environment_is_clean")
    assert _outcome(output, "test_environment_is_clean") == "PASSED", output


def test_without_the_url_postgres_skips_with_a_reason_and_sqlite_runs(
    tmp_path: Path,
) -> None:
    output = _run_child(tmp_path, {})
    assert _outcome(output, "test_sentinel[sqlite]") == "PASSED"
    assert _outcome(output, "test_sentinel[postgres]") == "SKIPPED"
    assert _skip_reasons(output) == [f"{URL_VARIABLE} is not set"]


def test_a_flag_other_than_1_does_not_fail_the_postgres_case(tmp_path: Path) -> None:
    output = _run_child(tmp_path, {REQUIRE_VARIABLE: "0"})
    assert _outcome(output, "test_sentinel[postgres]") == "SKIPPED"


def test_with_the_flag_and_no_url_the_postgres_case_fails(tmp_path: Path) -> None:
    output = _run_child(tmp_path, {REQUIRE_VARIABLE: "1"})
    assert _outcome(output, "test_sentinel[sqlite]") == "PASSED"
    # A fixture failure is reported by pytest as an ERROR at setup.
    assert _outcome(output, "test_sentinel[postgres]") == "ERROR"
    assert _skip_reasons(output) == []
    assert f"{REQUIRE_VARIABLE}=1 but {URL_VARIABLE} is not set" in output


def test_an_unreachable_server_fails_even_without_the_flag(tmp_path: Path) -> None:
    pytest.importorskip("psycopg", reason="needs the relay postgres extra")
    output = _run_child(tmp_path, {URL_VARIABLE: UNREACHABLE_URL})
    assert _outcome(output, "test_sentinel[postgres]") == "ERROR", output
    assert f"{URL_VARIABLE} is set but the server is unreachable" in output


def test_the_schema_is_dropped_on_teardown(
    tmp_path: Path, postgres_test_url: str
) -> None:
    psycopg = pytest.importorskip("psycopg", reason="needs the relay postgres extra")

    out = tmp_path / "conninfo.txt"
    output = _run_child(
        tmp_path,
        {URL_VARIABLE: postgres_test_url, "CHILD_OUT": str(out)},
        "-k",
        "test_sentinel and postgres",
    )
    assert _outcome(output, "test_sentinel[postgres]") == "PASSED", output
    schema = _schema_of(out.read_text(encoding="utf-8"))
    with psycopg.connect(postgres_test_url, autocommit=True) as conn:
        row = conn.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname = %s", (schema,)
        ).fetchone()
    assert row == (0,)


# --- the marker hook, through a child pytest --------------------------------

CHILD_MARKED = """
import pytest


@pytest.mark.covers("TokenStore.find_token")
@pytest.mark.covers("StorageBase.ping", "RecordStore.get_record")
def test_marked():
    pass


def test_unmarked():
    pass


def test_collected(collected_covers, marker_problems):
    assert collected_covers == [
        (
            "test_child.py::test_marked",
            ("StorageBase.ping", "RecordStore.get_record", "TokenStore.find_token"),
        )
    ]
    assert marker_problems(collected_covers) == []
"""

CHILD_BOGUS = CHILD_MARKED.replace(
    '"RecordStore.get_record"', '"RecordStore.get_records"'
)

CHILD_SCOPED = """
import pytest

pytestmark = pytest.mark.covers("StorageBase.bogus_module")


@pytest.mark.covers("StorageBase.bogus_class")
class TestScoped:
    def test_in_class(self):
        pass


@pytest.mark.covers("StorageBase.close")
class TestValid:
    def test_in_class(self):
        pass


def test_collected(collected_covers):
    seen = {nodeid.split("::", 1)[1]: names for nodeid, names in collected_covers}
    assert seen == {
        "test_collected": ("StorageBase.bogus_module",),
        "test_check": ("StorageBase.bogus_module",),
        "TestScoped::test_in_class": (
            "StorageBase.bogus_class",
            "StorageBase.bogus_module",
        ),
        "TestValid::test_in_class": ("StorageBase.close", "StorageBase.bogus_module"),
    }


def test_check(collected_covers, marker_problems):
    problems = marker_problems(collected_covers)
    assert [p.split(": ", 1)[1] for p in sorted(problems)] == [
        "'StorageBase.bogus_class' is not a Storage member",
    ] + ["'StorageBase.bogus_module' is not a Storage member"] * 4
"""


def test_the_hook_collects_class_and_module_level_markers(tmp_path: Path) -> None:
    output = _run_child(tmp_path, {}, source=CHILD_SCOPED)
    assert _outcome(output, "test_collected") == "PASSED", output
    assert _outcome(output, "test_check") == "PASSED", output


def test_the_hook_collects_every_marker_argument_of_a_test(tmp_path: Path) -> None:
    output = _run_child(tmp_path, {}, source=CHILD_MARKED)
    assert _outcome(output, "test_collected") == "PASSED", output


def test_a_marker_naming_a_non_member_reds_the_suite_check(tmp_path: Path) -> None:
    output = _run_child(tmp_path, {}, source=CHILD_BOGUS)
    assert _outcome(output, "test_collected") == "FAILED", output
    assert "'RecordStore.get_records' is not a Storage member" in output


# --- a missing driver is a failure, never a skip ----------------------------


def test_a_missing_driver_with_the_url_set_fails_the_postgres_case(
    tmp_path: Path,
) -> None:
    output = _run_child(
        tmp_path,
        {URL_VARIABLE: UNREACHABLE_URL, REQUIRE_VARIABLE: "1"},
        shim={"psycopg/__init__.py": "raise ImportError('shimmed out')\n"},
    )
    assert _outcome(output, "test_sentinel[postgres]") == "ERROR", output
    assert f"{URL_VARIABLE} is set but psycopg is not installed" in output
    assert _skip_reasons(output) == []
