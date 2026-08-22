"""Tests for data-root resolution with loud failure (Req 2.1, 2.2, 2.3).

These exercise :func:`fitdocs.config.resolve_data_root`, the pure implementation
of the output-location contract (design: DataRootResolver, ``src/fitdocs/config.py``).
The function takes an explicit ``--out`` path plus an injected ``env`` mapping and
``start_dir`` -- it never reads ``os.environ`` or ``Path.cwd()`` itself, so every
precedence level and failure mode is unit-testable with ``tmp_path`` alone.

Coverage:

* precedence: explicit flag beats env and pointer; env beats pointer (Req 2.1);
* pointer discovery in ``start_dir`` and in an *ancestor* of it, nearest wins,
  first line is the target, relative targets resolve against the pointer file's
  directory, absolute targets are honored (Req 2.1);
* an empty/whitespace env var and an empty pointer never resolve to the current
  working directory -- there is no implicit fallback of any kind (Req 2.3);
* every failure mode (nothing configured, explicit missing, explicit is a file,
  env missing, env is a file, pointer target missing, pointer empty) raises
  :class:`fitdocs.config.DataRootError` whose message names the failing source
  and lists all three configuration options (Req 2.2);
* nothing is written to disk on any failure (Req 2.2).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from fitdocs.config import (
    DATA_ROOT_ENV,
    POINTER_RELPATH,
    DataRootError,
    resolve_data_root,
)

# --- helpers ----------------------------------------------------------------


def _write_pointer(base: Path, content: str) -> Path:
    """Create ``base/.fitdocs/data-root`` with *content* and return its path."""
    pointer = base / POINTER_RELPATH
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(content)
    return pointer


def _snapshot(root: Path) -> set[Path]:
    """Every path under *root*, for asserting the tree is untouched."""
    return set(root.rglob("*"))


def _assert_lists_all_three_options(msg: str) -> None:
    """The error must mention each of the three configuration sources (Req 2.2)."""
    assert "--out" in msg
    assert DATA_ROOT_ENV in msg  # "FITDOCS_DATA"
    assert POINTER_RELPATH in msg  # ".fitdocs/data-root"


# --- Precedence: explicit > env > pointer (Req 2.1) -------------------------


def test_explicit_flag_takes_precedence_over_env_and_pointer(tmp_path: Path) -> None:
    """The explicit ``--out`` path wins over both env var and pointer (Req 2.1)."""
    explicit_dir = tmp_path / "explicit"
    env_dir = tmp_path / "env"
    pointer_dir = tmp_path / "pointer"
    for d in (explicit_dir, env_dir, pointer_dir):
        d.mkdir()
    _write_pointer(tmp_path, str(pointer_dir))

    result = resolve_data_root(
        explicit_dir,
        env={DATA_ROOT_ENV: str(env_dir)},
        start_dir=tmp_path,
    )

    assert result == explicit_dir


def test_env_var_takes_precedence_over_pointer(tmp_path: Path) -> None:
    """With no explicit flag, the env var wins over the pointer file (Req 2.1)."""
    env_dir = tmp_path / "env"
    pointer_dir = tmp_path / "pointer"
    env_dir.mkdir()
    pointer_dir.mkdir()
    _write_pointer(tmp_path, str(pointer_dir))

    result = resolve_data_root(
        None,
        env={DATA_ROOT_ENV: str(env_dir)},
        start_dir=tmp_path,
    )

    assert result == env_dir


# --- Pointer discovery (Req 2.1) --------------------------------------------


def test_pointer_found_in_start_dir(tmp_path: Path) -> None:
    """A pointer file directly in ``start_dir`` resolves its target (Req 2.1)."""
    base = tmp_path / "wiki"
    base.mkdir()
    target = tmp_path / "data"
    target.mkdir()
    _write_pointer(base, str(target))

    result = resolve_data_root(None, env={}, start_dir=base)

    assert result == target


def test_pointer_found_in_ancestor_of_start_dir(tmp_path: Path) -> None:
    """Discovery walks upward: a pointer in an ancestor is found (Req 2.1)."""
    root = tmp_path / "root"
    deep = root / "x" / "y" / "z"
    deep.mkdir(parents=True)
    target = tmp_path / "data"
    target.mkdir()
    _write_pointer(root, str(target))

    result = resolve_data_root(None, env={}, start_dir=deep)

    assert result == target


def test_nearest_pointer_wins_over_ancestor(tmp_path: Path) -> None:
    """The first pointer found walking upward wins over a higher one (Req 2.1)."""
    root = tmp_path / "root"
    child = root / "a" / "b"
    child.mkdir(parents=True)
    near = tmp_path / "near"
    far = tmp_path / "far"
    near.mkdir()
    far.mkdir()
    _write_pointer(root, str(far))  # ancestor pointer
    _write_pointer(child, str(near))  # nearest pointer

    result = resolve_data_root(None, env={}, start_dir=child)

    assert result == near


def test_pointer_first_line_is_the_target(tmp_path: Path) -> None:
    """Only the pointer's first line is read as the data-root path (Req 2.1)."""
    base = tmp_path / "wiki"
    base.mkdir()
    target = tmp_path / "data"
    target.mkdir()
    _write_pointer(base, f"{target}\nthis-line-is-ignored\nand-so-is-this\n")

    result = resolve_data_root(None, env={}, start_dir=base)

    assert result == target


def test_pointer_relative_target_resolves_against_pointer_dir(tmp_path: Path) -> None:
    """A relative pointer target resolves against the pointer file's dir (Req 2.1).

    The pointer file lives at ``project/.fitdocs/data-root``; a target of
    ``../actual-data`` therefore resolves to ``project/actual-data`` -- not
    against ``start_dir`` and not against the current working directory.
    """
    project = tmp_path / "project"
    data = project / "actual-data"
    data.mkdir(parents=True)
    _write_pointer(project, "../actual-data\n")

    result = resolve_data_root(None, env={}, start_dir=project)

    assert result == data


def test_pointer_absolute_target_is_honored(tmp_path: Path) -> None:
    """An absolute pointer target is used directly (Req 2.1)."""
    base = tmp_path / "wiki"
    base.mkdir()
    target = tmp_path / "elsewhere" / "data"
    target.mkdir(parents=True)
    _write_pointer(base, str(target))

    result = resolve_data_root(None, env={}, start_dir=base)

    assert result == target


# --- No implicit fallback of any kind (Req 2.3) -----------------------------


def test_empty_env_falls_through_to_pointer(tmp_path: Path) -> None:
    """A whitespace-only env var is treated as unset, not as ``Path('.')`` (Req 2.3)."""
    target = tmp_path / "data"
    target.mkdir()
    _write_pointer(tmp_path, str(target))

    result = resolve_data_root(None, env={DATA_ROOT_ENV: "   "}, start_dir=tmp_path)

    assert result == target


def test_empty_env_and_no_pointer_raises_never_uses_cwd(tmp_path: Path) -> None:
    """An empty env with no pointer fails; never falls back to cwd (Req 2.3)."""
    start = tmp_path / "iso"
    start.mkdir()

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(None, env={DATA_ROOT_ENV: ""}, start_dir=start)

    msg = str(excinfo.value)
    assert "No output location is configured" in msg
    _assert_lists_all_three_options(msg)


# --- Failure modes: name the source, list all options (Req 2.2) -------------


def test_nothing_configured_raises_and_lists_options(tmp_path: Path) -> None:
    """No source at all -> DataRootError listing all three options (Req 2.2)."""
    start = tmp_path / "iso"
    start.mkdir()

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(None, env={}, start_dir=start)

    msg = str(excinfo.value)
    assert "No output location is configured" in msg
    _assert_lists_all_three_options(msg)


def test_explicit_nonexistent_path_raises_naming_out(tmp_path: Path) -> None:
    """An explicit path that does not exist fails, naming ``--out`` (Req 2.2)."""
    missing = tmp_path / "nope"

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(missing, env={}, start_dir=tmp_path)

    msg = str(excinfo.value)
    assert "--out path does not exist" in msg
    assert str(missing) in msg
    _assert_lists_all_three_options(msg)


def test_explicit_file_not_directory_raises_naming_out(tmp_path: Path) -> None:
    """An explicit path that is a file (not a dir) fails, naming ``--out`` (Req 2.2)."""
    a_file = tmp_path / "afile"
    a_file.write_text("not a directory")

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(a_file, env={}, start_dir=tmp_path)

    msg = str(excinfo.value)
    assert "--out path is not a directory" in msg
    assert str(a_file) in msg
    _assert_lists_all_three_options(msg)


def test_env_nonexistent_path_raises_naming_env(tmp_path: Path) -> None:
    """A missing env target fails, naming ``FITDOCS_DATA`` (Req 2.2)."""
    missing = tmp_path / "nope"

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(None, env={DATA_ROOT_ENV: str(missing)}, start_dir=tmp_path)

    msg = str(excinfo.value)
    assert "FITDOCS_DATA environment variable points to" in msg
    assert str(missing) in msg
    _assert_lists_all_three_options(msg)


def test_env_file_not_directory_raises_naming_env(tmp_path: Path) -> None:
    """An env target that is a file (not a dir) fails, naming the env (Req 2.2)."""
    a_file = tmp_path / "afile"
    a_file.write_text("not a directory")

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(None, env={DATA_ROOT_ENV: str(a_file)}, start_dir=tmp_path)

    msg = str(excinfo.value)
    assert "FITDOCS_DATA environment variable points to" in msg
    assert str(a_file) in msg
    _assert_lists_all_three_options(msg)


def test_pointer_target_missing_raises_naming_pointer(tmp_path: Path) -> None:
    """A pointer whose target is missing fails, naming the pointer file (Req 2.2)."""
    base = tmp_path / "wiki"
    base.mkdir()
    missing = tmp_path / "gone"
    pointer = _write_pointer(base, str(missing))

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(None, env={}, start_dir=base)

    msg = str(excinfo.value)
    assert ".fitdocs/data-root pointer file" in msg
    assert "points to" in msg
    assert str(pointer) in msg
    _assert_lists_all_three_options(msg)


def test_empty_pointer_raises_naming_pointer(tmp_path: Path) -> None:
    """An empty pointer file fails rather than resolving to cwd (Req 2.2, 2.3)."""
    base = tmp_path / "wiki"
    base.mkdir()
    pointer = _write_pointer(base, "")

    with pytest.raises(DataRootError) as excinfo:
        resolve_data_root(None, env={}, start_dir=base)

    msg = str(excinfo.value)
    assert "pointer file is empty" in msg
    assert str(pointer) in msg
    _assert_lists_all_three_options(msg)


# --- Nothing is written to disk on any failure (Req 2.2) --------------------


def _setup_nothing(tmp_path: Path) -> tuple[Path | None, Mapping[str, str], Path]:
    start = tmp_path / "iso"
    start.mkdir()
    return (None, {}, start)


def _setup_explicit_missing(
    tmp_path: Path,
) -> tuple[Path | None, Mapping[str, str], Path]:
    return (tmp_path / "nope", {}, tmp_path)


def _setup_env_missing(tmp_path: Path) -> tuple[Path | None, Mapping[str, str], Path]:
    return (None, {DATA_ROOT_ENV: str(tmp_path / "nope")}, tmp_path)


def _setup_pointer_target_missing(
    tmp_path: Path,
) -> tuple[Path | None, Mapping[str, str], Path]:
    base = tmp_path / "wiki"
    base.mkdir()
    _write_pointer(base, str(tmp_path / "gone"))
    return (None, {}, base)


def _setup_pointer_empty(tmp_path: Path) -> tuple[Path | None, Mapping[str, str], Path]:
    base = tmp_path / "wiki"
    base.mkdir()
    _write_pointer(base, "")
    return (None, {}, base)


_FAILURE_SETUPS: list[Callable[[Path], tuple[Path | None, Mapping[str, str], Path]]] = [
    _setup_nothing,
    _setup_explicit_missing,
    _setup_env_missing,
    _setup_pointer_target_missing,
    _setup_pointer_empty,
]


@pytest.mark.parametrize(
    "setup",
    _FAILURE_SETUPS,
    ids=[fn.__name__ for fn in _FAILURE_SETUPS],
)
def test_nothing_is_written_on_failure(
    tmp_path: Path,
    setup: Callable[[Path], tuple[Path | None, Mapping[str, str], Path]],
) -> None:
    """The resolver never creates or writes anything when it fails (Req 2.2)."""
    explicit, env, start_dir = setup(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(DataRootError):
        resolve_data_root(explicit, env=env, start_dir=start_dir)

    assert _snapshot(tmp_path) == before


def test_resolver_never_creates_a_valid_explicit_root(tmp_path: Path) -> None:
    """A valid explicit dir is returned unchanged; nothing new is written (Req 2.2)."""
    out = tmp_path / "out"
    out.mkdir()
    before = _snapshot(tmp_path)

    result = resolve_data_root(out, env={}, start_dir=tmp_path)

    assert result == out
    assert _snapshot(tmp_path) == before
