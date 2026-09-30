"""The preview loop: snapshots, the live root, and the serve process (7.1-7.4).

Unit part. The build and the serve launcher are replaced by recording stubs, so
no test in the unit part runs Zensical; the integration part at the end of this
module runs the real generator behind ``requires_zensical``. The loop is
scripted: ``ScriptedStop`` is an ``Event`` whose ``wait`` runs the next scripted
step (usually an edit) and reports "not stopped", then sets itself once the
script is spent. ``drive`` runs the loop in a daemon thread with a bounded join,
so a loop that never stops fails its test instead of hanging. One test uses a
plain ``Event`` to check that a stop cuts a long poll wait short. Every
preview root, repository skeleton and content copy is
under ``tmp_path``; the real fixture tree and the real ``website/`` are only
read.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import socket
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from scripts.sitebuild import generator, pipeline, preview
from scripts.sitebuild.generator import GeneratorResult
from scripts.sitebuild.model import Problem
from scripts.sitebuild.pipeline import BuildOutcome, BuildRootRefused, build
from scripts.sitebuild.preview import snapshot

from tests.sitebuild.conftest import copy_fixture_tree

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "site"
ADDR = "127.0.0.1:8123"
SECOND = 1_000_000_000


def write(path: Path, text: str) -> None:
    """Write ``text`` at a new mtime, creating parent directories."""
    existed = path.exists()
    before = path.stat().st_mtime_ns if existed else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if existed:
        os.utime(path, ns=(before + SECOND, before + SECOND))


# ---------------------------------------------------------------- snapshot


def test_snapshot_records_mtime_and_size_per_file(tmp_path: Path) -> None:
    """Each file maps to ``(mtime_ns, size)``, nested and bare files included.

    The three files differ in size, so the tuples are distinct and a swapped or
    dropped field shows.

    Dies on: the value tuple reordered to `(size, mtime_ns)`; the walk not
    descending into subdirectories; a watched entry that is a file skipped.
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abc")
    write(tree / "sub" / "deep" / "b.md", "hello world")
    single = tmp_path / "template.yml"
    write(single, "x: 1\n")
    result = snapshot([tree, single])
    expected = {
        str(p): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in (tree / "a.md", tree / "sub" / "deep" / "b.md", single)
    }
    assert len({v for v in expected.values()}) == 3
    assert result == expected


def test_snapshot_detects_a_created_file(tmp_path: Path) -> None:
    """A new file, in a new subdirectory, changes the snapshot.

    Dies on: the snapshot built from a fixed list of the first-level entries
    (a nested create goes unseen); `snapshot` returning `{}`.
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abc")
    before = snapshot([tree])
    assert before
    write(tree / "new" / "b.md", "hello")
    after = snapshot([tree])
    assert after != before
    assert str(tree / "new" / "b.md") in after


def test_snapshot_detects_a_deleted_file(tmp_path: Path) -> None:
    """Deleting one of two files changes the snapshot, and the key is gone.

    The survivor is unchanged, so only the deletion can differ.

    Dies on: a snapshot ignoring deletes (the previous snapshot merged into the
    new one).
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abc")
    write(tree / "b.md", "hello")
    before = snapshot([tree])
    (tree / "a.md").unlink()
    after = snapshot([tree])
    assert str(tree / "a.md") in before
    assert after != before
    assert str(tree / "a.md") not in after
    assert after[str(tree / "b.md")] == before[str(tree / "b.md")]


def test_snapshot_detects_a_same_size_change(tmp_path: Path) -> None:
    """A rewrite with the same number of bytes changes the snapshot through mtime.

    Dies on: the snapshot recording size only.
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abcdef")
    before = snapshot([tree])
    write(tree / "a.md", "uvwxyz")
    assert (tree / "a.md").stat().st_size == 6
    after = snapshot([tree])
    assert after != before


def test_snapshot_detects_a_size_change_at_the_same_mtime(tmp_path: Path) -> None:
    """A longer file with the old mtime restored still changes the snapshot.

    Dies on: the snapshot recording mtime only.
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abc")
    stamp = (tree / "a.md").stat().st_mtime_ns
    before = snapshot([tree])
    (tree / "a.md").write_text("abcdef", encoding="utf-8")
    os.utime(tree / "a.md", ns=(stamp, stamp))
    assert (tree / "a.md").stat().st_mtime_ns == stamp
    assert snapshot([tree]) != before


def test_snapshot_detects_a_created_link_to_a_directory(tmp_path: Path) -> None:
    """A new symbolic link to a directory changes the snapshot (a build problem).

    The link is created in ``tmp_path`` and points at a directory beside the tree
    that holds a file. The link is recorded as an entry, and the file behind it
    is not.

    Dies on: the walk recording file names only, without the directory-link
    entries; `os.walk(..., followlinks=True)`.
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abc")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    write(elsewhere / "f.md", "linked file")
    before = snapshot([tree])
    (tree / "link").symlink_to(elsewhere, target_is_directory=True)
    after = snapshot([tree])
    assert after != before
    assert str(tree / "link") in after
    assert str(tree / "link" / "f.md") not in after


def test_snapshot_of_untouched_files_is_equal_and_skips_missing_paths(
    tmp_path: Path,
) -> None:
    """Two snapshots of untouched files are equal, and an absent path is skipped.

    Dies on: the stat of a missing path not guarded (a missing template
    raises).
    """
    tree = tmp_path / "tree"
    write(tree / "a.md", "abc")
    missing = tmp_path / "no-such-template.yml"
    first = snapshot([tree, missing])
    assert first
    assert snapshot([tree, missing]) == first


# ------------------------------------------------------------- loop doubles


class ScriptedStop(threading.Event):
    """An ``Event`` whose ``wait`` runs one scripted step per poll, then stops."""

    def __init__(self, *steps: Callable[[], None]) -> None:
        super().__init__()
        self.steps = list(steps)
        self.timeouts: list[float | None] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.timeouts.append(timeout)
        if self.is_set():
            return True
        if not self.steps:
            self.set()
            return True
        self.steps.pop(0)()
        return False


def drive(call: Callable[[], int], stop: threading.Event, *, limit: float = 4.0) -> int:
    """Run ``call`` in a daemon thread; fail if it outlives ``limit`` seconds.

    An exception raised in the thread, ``KeyboardInterrupt`` included, is raised
    again in the caller.
    """
    result: list[int] = []
    raised: list[BaseException] = []

    def target() -> None:
        try:
            result.append(call())
        except BaseException as error:
            raised.append(error)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(limit)
    if thread.is_alive():
        stop.set()
        thread.join(limit)
        pytest.fail(f"the loop was still running after {limit} s")
    if raised:
        raise raised[0]
    return result[0]


class FakeProc:
    """A ``Popen`` stand-in that records how it was stopped."""

    def __init__(
        self, *, ignores_terminate: bool = False, exits_after_polls: int | None = None
    ) -> None:
        self.ignores_terminate = ignores_terminate
        self.exits_after_polls = exits_after_polls
        self.polls = 0
        self.returncode: int | None = None
        self.events: list[str] = []

    def poll(self) -> int | None:
        self.polls += 1
        if self.exits_after_polls is not None and self.polls >= self.exits_after_polls:
            self.returncode = 1
        return self.returncode

    def terminate(self) -> None:
        self.events.append("terminate")

    def kill(self) -> None:
        self.events.append("kill")

    def wait(self, timeout: float | None = None) -> int:
        self.events.append("wait")
        if self.ignores_terminate and "kill" not in self.events:
            # A real Popen blocks for ever here without a timeout.
            assert timeout is not None, (
                "unbounded wait on a process that ignores terminate"
            )
            raise subprocess.TimeoutExpired("serve", timeout)
        return 0


class StubServe:
    """A stand-in for ``start_serve`` that records each launch."""

    def __init__(
        self, *, ignores_terminate: bool = False, exits_after_polls: int | None = None
    ) -> None:
        self.ignores_terminate = ignores_terminate
        self.exits_after_polls = exits_after_polls
        self.starts: list[tuple[Path, str]] = []
        self.procs: list[FakeProc] = []
        self.started = threading.Event()
        self.live_at_start: list[dict[str, bytes]] = []

    def __call__(self, root: Path, addr: str) -> FakeProc:
        self.starts.append((root, addr))
        self.live_at_start.append(read_live(root))
        proc = FakeProc(
            ignores_terminate=self.ignores_terminate,
            exits_after_polls=self.exits_after_polls,
        )
        self.procs.append(proc)
        self.started.set()
        return proc


class StubBuild:
    """A stand-in for ``build`` that returns scripted outcomes in order."""

    def __init__(self, *outcomes: BuildOutcome | BaseException) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[Path, Path, Path]] = []
        self.on_call: Callable[[], None] | None = None

    def __call__(
        self, content_dir: Path, root: Path, *, repo_root: Path
    ) -> BuildOutcome:
        self.calls.append((content_dir, root, repo_root))
        if self.on_call is not None:
            self.on_call()
        assert self.outcomes, "the loop built more often than the test scripted"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def tree_a() -> dict[str, bytes]:
    return {
        "mkdocs.yml": b"site_name: A\n",
        "staged/index.md": b"index of A\n",
        "staged/only-a.md": b"only in A\n",
        "staged/deep/x.md": b"deep in A\n",
        "overrides/home.html": b"<home>A</home>\n",
    }


def tree_b() -> dict[str, bytes]:
    return {
        "mkdocs.yml": b"site_name: B\n",
        "staged/index.md": b"index of B, longer\n",
        "staged/new.md": b"new in B\n",
        "overrides/home.html": b"<home>A</home>\n",
    }


def ok(tree: Mapping[str, bytes]) -> BuildOutcome:
    return BuildOutcome(True, (), "", dict(tree), 1)


PROBLEMS = (
    Problem("why.md", "section", "unknown section"),
    Problem("get-started/install.md", "3:1", "multi\nline message\n"),
    Problem("", "", "third problem"),
)


GENERATOR_OUTPUT = "GENERATOR-OUTPUT-LINE one\nGENERATOR-OUTPUT-LINE two\n"


def failed(*, tree: Mapping[str, bytes] | None = None) -> BuildOutcome:
    """A failed build; ``tree`` set means a generator failure after a clean plan."""
    return BuildOutcome(
        False, PROBLEMS, GENERATOR_OUTPUT, None if tree is None else dict(tree), 1
    )


def read_live(live: Path) -> dict[str, bytes]:
    """The managed files of a live root, by relative POSIX path."""
    found: dict[str, bytes] = {}
    for name in ("mkdocs.yml", "staged", "overrides"):
        path = live / name
        if path.is_file():
            found[name] = path.read_bytes()
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    found[child.relative_to(live).as_posix()] = child.read_bytes()
    return found


def live_hash(live: Path) -> str:
    """Path, mode, mtime and bytes of everything under ``live``."""
    digest = hashlib.sha256()
    rows = [f".|{live.lstat().st_mtime_ns}"]
    for path in sorted(live.rglob("*")):
        info = path.lstat()
        row = f"{path.relative_to(live).as_posix()}|{info.st_mode:o}|{info.st_mtime_ns}"
        if stat.S_ISREG(info.st_mode):
            row += "|" + hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(row)
    for row in rows:
        digest.update(row.encode() + b"\n")
    return digest.hexdigest()


@dataclass
class Env:
    """A repository skeleton, a content dir and a preview root, all in ``tmp_path``."""

    tmp_path: Path
    monkeypatch: pytest.MonkeyPatch
    build: StubBuild = field(default_factory=StubBuild)
    serve: StubServe = field(default_factory=StubServe)
    out: io.StringIO = field(default_factory=io.StringIO)

    def __post_init__(self) -> None:
        self.repo = self.tmp_path / "repo"
        self.content = self.tmp_path / "content"
        self.root = self.tmp_path / "preview"
        write(self.content / "index.md", "home\n")
        write(self.repo / "website" / "overrides" / "home.html", "<home/>\n")
        write(self.repo / "website" / "assets" / "brand.css", "a{}\n")
        write(self.repo / "website" / "mkdocs.template.yml", "site_name: t\n")
        self.template = self.repo / "website" / "mkdocs.template.yml"
        self.monkeypatch.setattr(preview, "build", self._build)
        self.monkeypatch.setattr(preview, "start_serve", self._start)

    def _build(self, content_dir: Path, root: Path, *, repo_root: Path) -> BuildOutcome:
        return self.build(content_dir, root, repo_root=repo_root)

    def _start(self, root: Path, addr: str) -> FakeProc:
        return self.serve(root, addr)

    @property
    def live(self) -> Path:
        return self.root.resolve() / "live"

    def run(
        self, *steps: Callable[[], None], poll: float = 0.25, expect: int = 0
    ) -> ScriptedStop:
        stop = ScriptedStop(*steps)
        code = drive(
            lambda: preview.serve(
                self.content,
                self.root,
                repo_root=self.repo,
                addr=ADDR,
                poll_interval=poll,
                stop=stop,
                out=self.out,
            ),
            stop,
        )
        assert code == expect
        if expect == 0:
            assert stop.steps == [], "the loop ended before the script was spent"
        return stop

    def lines(self) -> list[str]:
        return self.out.getvalue().splitlines()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


def nothing() -> None:
    return None


# ----------------------------------------------------------- the loop: builds


def test_the_first_build_goes_into_check_and_success_syncs_live_then_serves(
    env: Env,
) -> None:
    """A clean first build lands in ``live/``, and the serve process starts on it.

    The build is asked for ``<root>/check`` and the launcher for ``<root>/live``
    with the given address; ``live/`` did not exist before, and holds exactly
    the tree afterwards.

    The launcher also sees the complete tree already in ``live/`` when it is
    called.

    Dies on: the build pointed at `live/` (or at the root itself); the serve
    launcher pointed at `check/`; the address dropped; the sync skipped; the
    launcher called before the sync.
    """
    env.build = StubBuild(ok(tree_a()))
    assert not env.root.exists()
    env.run()
    assert len(env.build.calls) == 1
    content_dir, built_root, repo_root = env.build.calls[0]
    assert (content_dir, built_root, repo_root) == (
        env.content,
        env.root.resolve() / "check",
        env.repo,
    )
    assert read_live(env.live) == tree_a()
    assert env.serve.starts == [(env.live, ADDR)]
    assert env.serve.live_at_start == [tree_a()]
    assert env.lines() == []


def test_a_rebuild_happens_on_a_change_and_only_on_a_change(env: Env) -> None:
    """Quiet polls build nothing, and one edit builds exactly once.

    Two quiet polls, one edit, one quiet poll: two builds in all. The waits use
    the given poll interval each time.

    Dies on: a rebuild on every poll; the change check inverted; the poll wait
    using a constant instead of `poll_interval`.
    """
    env.build = StubBuild(ok(tree_a()), ok(tree_a()))
    stop = env.run(
        nothing,
        nothing,
        lambda: write(env.content / "index.md", "edited\n"),
        nothing,
        poll=0.125,
    )
    assert len(env.build.calls) == 2
    assert set(stop.timeouts) == {0.125}


@pytest.mark.parametrize("watched", ["content", "overrides", "assets", "template"])
def test_each_of_the_four_inputs_triggers_a_rebuild(env: Env, watched: str) -> None:
    """A change in any one of the four watched inputs rebuilds once.

    Dies on: the corresponding path dropped from the watched list (the
    parametrized case for that input goes red, the other three stay green).
    """
    targets = {
        "content": env.content / "index.md",
        "overrides": env.repo / "website" / "overrides" / "home.html",
        "assets": env.repo / "website" / "assets" / "brand.css",
        "template": env.template,
    }
    target = targets[watched]
    env.build = StubBuild(ok(tree_a()), ok(tree_a()))
    env.run(lambda: write(target, "changed text that is longer\n"))
    assert len(env.build.calls) == 2


def test_create_and_delete_in_the_content_dir_each_rebuild(env: Env) -> None:
    """Creating a page, then deleting another, rebuilds once for each.

    Dies on: the snapshot ignoring creates (first rebuild missing) or deletes
    (second rebuild missing).
    """
    write(env.content / "old.md", "old\n")
    env.build = StubBuild(ok(tree_a()), ok(tree_a()), ok(tree_a()))
    env.run(
        lambda: write(env.content / "sub" / "fresh.md", "fresh\n"),
        nothing,
        lambda: (env.content / "old.md").unlink(),
        nothing,
    )
    assert len(env.build.calls) == 3


def test_an_edit_made_during_a_build_is_picked_up(env: Env) -> None:
    """The snapshot is taken before the build, so an edit mid-build rebuilds.

    The first build itself edits the content and no step does.

    Dies on: the snapshot taken after the build returns.
    """
    env.build = StubBuild(ok(tree_a()), ok(tree_b()))
    env.build.on_call = lambda: (
        write(env.content / "index.md", "edited during the build\n")
        if len(env.build.calls) == 1
        else None
    )
    env.run(nothing)
    assert len(env.build.calls) == 2


# ------------------------------------------------------------ the loop: live


def test_a_later_success_syncs_live_in_place(env: Env) -> None:
    """A second success makes ``live/`` equal the new tree, keeping inodes.

    A hard link taken to a changed file and to an unchanged file still names the
    live file afterwards (an in-place write), the removed and added files are
    gone and present, and the serve process was not restarted.

    Dies on: `write_tree` in place of `sync_tree` for the live root (the links
    then name deleted files); the sync skipped on later successes.
    """
    env.build = StubBuild(ok(tree_a()), ok(tree_b()))
    links: dict[str, Path] = {}

    def link_files() -> None:
        for name in ("staged/index.md", "overrides/home.html"):
            links[name] = env.tmp_path / ("link-" + name.replace("/", "-"))
            os.link(env.live / name, links[name])
        write(env.content / "index.md", "edited\n")

    assert not (env.live / "staged" / "new.md").exists()
    env.run(link_files, nothing)
    assert read_live(env.live) == tree_b()
    for name, link in links.items():
        assert os.path.samefile(link, env.live / name), name
    assert links["staged/index.md"].read_bytes() == b"index of B, longer\n"
    assert len(env.serve.starts) == 1


def test_serving_starts_once_however_many_builds_succeed(env: Env) -> None:
    """Three successful builds start the serve process exactly once.

    Dies on: the launcher called on every success.
    """
    env.build = StubBuild(ok(tree_a()), ok(tree_b()), ok(tree_a()))
    env.run(
        lambda: write(env.content / "index.md", "one\n"),
        lambda: write(env.content / "index.md", "twoo\n"),
        nothing,
    )
    assert len(env.build.calls) == 3
    assert len(env.serve.starts) == 1
    assert read_live(env.live) == tree_a()


# ----------------------------------------------------------- the loop: failure


def test_a_failing_rebuild_prints_the_build_lines_and_leaves_live_untouched(
    env: Env,
) -> None:
    """Every problem prints as its ``render()`` line, and ``live/`` is byte-unchanged.

    The failure carries a tree (a generator failure after a clean plan) that
    differs from the live one, so a sync decided on the tree would show.
    ``live/`` is hashed with modes and mtimes before and after.

    Dies on: syncing on `outcome.tree is not None` instead of `outcome.ok`;
    printing only the first problem; printing `str(problem)` or the message
    alone instead of `render()`; problem lines sent to another stream; the
    generator output printed after the problem lines (the failed outcome
    carries a non-empty one).
    """
    env.build = StubBuild(ok(tree_a()), failed(tree=tree_b()))
    seen: dict[str, str] = {}

    def after_failure() -> None:
        seen["live"] = live_hash(env.live)
        seen["out"] = env.out.getvalue()

    env.run(lambda: write(env.content / "index.md", "broken\n"), after_failure)
    assert PROBLEMS[1].message.count("\n") == 2
    expected = [p.render() for p in PROBLEMS]
    assert len(expected) == 3
    assert env.lines() == expected
    assert seen["out"] == env.out.getvalue()
    assert live_hash(env.live) == seen["live"]
    assert read_live(env.live) == tree_a()
    assert len(env.serve.starts) == 1


def test_a_script_level_failure_leaves_live_untouched_and_the_loop_running(
    env: Env,
) -> None:
    """A failure with no tree also leaves ``live/`` alone, and a fix then syncs.

    The order is success, failure, success with a different tree: the failure
    prints the problem lines once and the third build is still made.

    Dies on: the loop returning after a failed rebuild; a failure clearing
    `live/`; the later success not synced.
    """
    env.build = StubBuild(ok(tree_a()), failed(), ok(tree_b()))
    lives: list[dict[str, bytes]] = []
    env.run(
        lambda: write(env.content / "index.md", "broken\n"),
        lambda: lives.append(read_live(env.live)),
        lambda: write(env.content / "index.md", "fixed!\n"),
    )
    assert lives == [tree_a()]
    assert env.lines() == [p.render() for p in PROBLEMS]
    assert read_live(env.live) == tree_b()


def test_an_initial_failure_starts_no_server_until_a_success(env: Env) -> None:
    """Two failed builds start nothing and create no ``live/``; a success starts it.

    Dies on: the launcher called before the first success (or after a failure);
    `live/` created before a success; the loop stopping after a failed first
    build.
    """
    env.build = StubBuild(failed(), failed(tree=tree_a()), ok(tree_a()))
    state: list[tuple[int, bool]] = []

    def record() -> None:
        state.append((len(env.serve.starts), env.live.exists()))

    env.run(
        record,
        lambda: write(env.content / "index.md", "still broken\n"),
        record,
        lambda: write(env.content / "index.md", "now good!!\n"),
    )
    assert state == [(0, False), (0, False)]
    assert env.lines() == [p.render() for p in PROBLEMS] * 2
    assert len(env.serve.starts) == 1
    assert read_live(env.live) == tree_a()


# ----------------------------------------------------------- the loop: exit


def test_the_serve_process_is_terminated_and_reaped_on_stop(env: Env) -> None:
    """A normal stop terminates the one process, then waits for it.

    Dies on: no terminate at exit; the wait skipped.
    """
    env.build = StubBuild(ok(tree_a()))
    env.run()
    assert env.serve.procs[0].events == ["terminate", "wait"]


def test_a_process_that_ignores_terminate_is_killed(env: Env) -> None:
    """When the process outlives the wait timeout, it is killed and reaped.

    The double behaves like ``Popen``: an unbounded wait on a process that
    ignores terminate fails the test, and only a bounded wait times out.

    Dies on: the kill dropped from the timeout path; `process.wait()` without a
    timeout after terminate.
    """
    env.serve = StubServe(ignores_terminate=True)
    env.build = StubBuild(ok(tree_a()))
    env.run()
    assert env.serve.procs[0].events == ["terminate", "wait", "kill", "wait"]


def test_a_serve_process_that_dies_ends_the_preview_with_two(env: Env) -> None:
    """A serve process that exits on its own is reported, and the loop returns 2.

    The process exits with status 1 at its second poll (a bound port, say). One
    line is printed, the loop stops at that poll with eight scripted polls
    unspent, and the dead process is still cleaned up.

    Dies on: the `process.poll()` check dropped from the loop (the loop runs to
    the end of the script and returns 0).
    """
    env.serve = StubServe(exits_after_polls=2)
    env.build = StubBuild(ok(tree_a()))
    stop = env.run(*([nothing] * 10), expect=2)
    assert env.lines() == ["site generator: serve exited with status 1"]
    assert len(stop.steps) == 8
    assert env.serve.procs[0].events[:1] == ["terminate"]


def test_an_exception_terminates_the_process_and_propagates(env: Env) -> None:
    """A build that raises after the server started still stops the server.

    Dies on: the terminate placed after the loop instead of in a `finally`.
    """
    env.build = StubBuild(ok(tree_a()), RuntimeError("generator exploded"))
    with pytest.raises(RuntimeError, match="generator exploded"):
        env.run(lambda: write(env.content / "index.md", "boom\n"))
    assert len(env.serve.procs) == 1
    assert env.serve.procs[0].events[:1] == ["terminate"]


def test_an_interrupt_returns_zero_and_terminates_the_process(env: Env) -> None:
    """Ctrl-C during the poll wait ends the preview with 0 and stops the server.

    Dies on: `KeyboardInterrupt` not caught (the call raises); no terminate on
    that path.
    """
    env.build = StubBuild(ok(tree_a()))

    def interrupt() -> None:
        raise KeyboardInterrupt

    try:
        env.run(interrupt)
    except KeyboardInterrupt:
        pytest.fail("the interrupt escaped the preview")
    assert env.serve.procs[0].events == ["terminate", "wait"]


def test_an_exception_before_the_first_success_starts_nothing(env: Env) -> None:
    """A first build that raises propagates, with no process ever launched.

    Dies on: a launcher call made before the first build result is known.
    """
    env.build = StubBuild(RuntimeError("first build exploded"))
    with pytest.raises(RuntimeError, match="first build exploded"):
        env.run()
    assert env.serve.starts == []


def test_a_refused_root_raises_before_anything_is_built_or_written(env: Env) -> None:
    """A preview root inside the repository but outside ``website/build`` is refused.

    The build is a stub with no guard of its own, so only the loop can refuse.

    Dies on: the `guard_root` call removed from `serve`.
    """
    env.root = env.repo / "elsewhere"
    env.build = StubBuild(ok(tree_a()))
    with pytest.raises(BuildRootRefused):
        env.run()
    assert env.build.calls == []
    assert not env.root.exists()
    assert env.serve.starts == []


def test_a_stop_cuts_the_poll_wait_short(env: Env) -> None:
    """With a 60 s poll, setting the stop event ends the loop within seconds.

    A real thread runs the loop; the join is bounded so a hang fails the test
    rather than blocking it.

    Dies on: the poll wait made a `time.sleep(poll_interval)`.
    """
    env.build = StubBuild(ok(tree_a()))
    stop = threading.Event()
    result: list[int] = []

    def target() -> None:
        result.append(
            preview.serve(
                env.content,
                env.root,
                repo_root=env.repo,
                addr=ADDR,
                poll_interval=60.0,
                stop=stop,
                out=env.out,
            )
        )

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    assert env.serve.started.wait(10)
    stop.set()
    thread.join(10)
    assert not thread.is_alive()
    assert result == [0]
    assert env.serve.procs[0].events == ["terminate", "wait"]


# ------------------------------------------------- composed with the real build


class HtmlStub:
    """A stand-in for ``run_build`` that leaves an ``html/`` like a success."""

    def __call__(self, root: Path) -> GeneratorResult:
        (root / "html").mkdir(exist_ok=True)
        (root / "html" / "index.html").write_text("<html></html>")
        return GeneratorResult(ok=True, problems=(), output="")


def dir_hash(root: Path) -> tuple[int, str]:
    """The file count and a digest of path, mode, mtime and bytes under ``root``."""
    digest = hashlib.sha256()
    count = 0
    rows = [f".|{root.lstat().st_mode:o}|{root.lstat().st_mtime_ns}"]
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted([*dirnames, *filenames]):
            path = Path(dirpath) / name
            info = path.lstat()
            row = f"{path.relative_to(root).as_posix()}|{info.st_mode:o}"
            row += f"|{info.st_mtime_ns}"
            if stat.S_ISREG(info.st_mode):
                row += "|" + hashlib.sha256(path.read_bytes()).hexdigest()
                count += 1
            rows.append(row)
    for row in sorted(rows):
        digest.update(row.encode() + b"\n")
    return count, digest.hexdigest()


def test_the_real_build_through_the_loop_writes_only_under_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edit, break, fix over a copy of the fixture, with the real ``build``.

    Only the generator is a stub. The failure prints exactly the lines a direct
    ``build`` of the same broken content reports, the live copy of the edited
    page is byte-identical during the failure, and the fix reaches ``live/``.
    The content copy and the repository skeleton are hashed (bytes, modes and
    mtimes) after each edit and again at the end, and the top-level entries of
    ``tmp_path`` are the ones that existed before plus the preview root, which
    holds ``check/`` and ``live/`` only. The content dir sits outside the
    repository skeleton (7.1).

    Dies on: the live root placed beside the preview root instead of under it;
    a file written, or a `utime` call, in the content copy; the failure lines
    differing from `build`'s.
    """
    monkeypatch.setattr(pipeline, "run_build", HtmlStub())
    repo = tmp_path / "repo"
    (repo / "website").mkdir(parents=True)
    for name in ("assets", "overrides"):
        shutil.copytree(REPO_ROOT / "website" / name, repo / "website" / name)
    shutil.copytree(REPO_ROOT / "docs", repo / "docs")
    shutil.copy2(
        REPO_ROOT / "website" / "mkdocs.template.yml",
        repo / "website" / "mkdocs.template.yml",
    )
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    broken = copy_fixture_tree(FIXTURE, tmp_path, "broken-reference")
    why = "why.md"
    for tree in (content, broken):
        assert (tree / why).read_text(encoding="utf-8").count("section: Why\n") == 1
    write(
        broken / why,
        (broken / why)
        .read_text(encoding="utf-8")
        .replace("section: Why\n", "section: Nowhere\n"),
    )
    reference = build(broken, tmp_path / "reference" / "site", repo_root=repo)
    assert not reference.ok
    reference_lines = [p.render() for p in reference.problems]
    assert reference_lines

    baseline = {p.name for p in tmp_path.iterdir()}
    pristine = (content / why).read_text(encoding="utf-8")
    edited = pristine.replace("A single valid tree", "EDITMARKER a single valid tree")
    assert edited != pristine
    monkeypatch.setattr(preview, "start_serve", StubServe())
    hashes: dict[str, tuple[int, str]] = {}
    seen: dict[str, bytes] = {}
    out = io.StringIO()
    root = tmp_path / "preview"

    def guard_inputs(label: str) -> None:
        for name, path in (("content", content), ("repo", repo)):
            current = dir_hash(path)
            assert current[0] > 0
            key = f"{name}:{label}"
            if key not in hashes:
                hashes[key] = current
            assert current == hashes[key], key

    def remember(label: str) -> None:
        for name, path in (("content", content), ("repo", repo)):
            hashes[f"{name}:{label}"] = dir_hash(path)

    def edit() -> None:
        guard_inputs("initial")
        write(content / why, edited)
        remember("after-edit")

    def break_it() -> None:
        guard_inputs("after-edit")
        seen["live-edited"] = (root.resolve() / "live" / "staged" / why).read_bytes()
        assert b"EDITMARKER" in seen["live-edited"]
        write(content / why, edited.replace("section: Why\n", "section: Nowhere\n"))
        remember("after-break")

    def check_failure() -> None:
        guard_inputs("after-break")
        assert (root.resolve() / "live" / "staged" / why).read_bytes() == seen[
            "live-edited"
        ]
        assert out.getvalue().splitlines() == reference_lines
        write(content / why, edited)
        remember("after-fix")

    stop = ScriptedStop(edit, nothing, break_it, nothing, check_failure, nothing)
    remember("initial")
    code = drive(
        lambda: preview.serve(
            content,
            root,
            repo_root=repo,
            addr=ADDR,
            poll_interval=0.25,
            stop=stop,
            out=out,
        ),
        stop,
    )
    assert code == 0
    assert stop.steps == []
    guard_inputs("after-fix")
    assert {p.name for p in tmp_path.iterdir()} == baseline | {"preview"}
    assert {p.name for p in root.iterdir()} == {"check", "live"}
    live_why = (root.resolve() / "live" / "staged" / why).read_bytes()
    assert b"EDITMARKER" in live_why
    assert b"Nowhere" not in live_why
    assert out.getvalue().splitlines() == reference_lines


# ------------------------------------------------ live preview, real generator

WAIT_LIMIT = 20.0


class LockedOut(io.StringIO):
    """A ``StringIO`` that the preview thread writes and the test thread reads."""

    def __init__(self) -> None:
        super().__init__()
        self.lock = threading.Lock()

    def write(self, text: str) -> int:
        with self.lock:
            return super().write(text)

    def text(self) -> str:
        with self.lock:
            return self.getvalue()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fetch(addr: str, path: str) -> tuple[int | None, str]:
    """``(status, body)`` of one GET; ``(None, reason)`` when nothing answers."""
    try:
        with urllib.request.urlopen(f"http://{addr}{path}", timeout=2) as reply:
            return reply.status, reply.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, ""
    except OSError as error:
        return None, repr(error)


def wait_for(what: str, ready: Callable[[], bool], thread: threading.Thread) -> None:
    """Poll ``ready`` for ``WAIT_LIMIT`` seconds; fail naming ``what`` if it fails."""
    end = time.monotonic() + WAIT_LIMIT
    while time.monotonic() < end:
        if ready():
            return
        if not thread.is_alive():
            pytest.fail(f"the preview loop ended while waiting for: {what}")
        time.sleep(0.1)
    pytest.fail(f"not within {WAIT_LIMIT} s: {what}")


def test_live_preview_serves_edits_adds_deletes_failures_and_fixes(
    requires_zensical: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real ``serve`` over a fixture copy, seen through HTTP, ``out`` and the disk.

    One preview runs the whole sequence: an edit is served, an added page is
    served, the deleted page answers 404, a page with a broken `section:` prints
    its problem lines (identical to a direct ``build`` of the same content) while
    the edited text is still served, and the fix is served. Each wait is a
    bounded poll. Before the steps that add a page and print problems the test
    asserts the page answers 404 and ``out`` is empty. The content copy, outside
    the repository, hashes the same (bytes, modes, mtimes) before and after the
    startup waits and each wait that follows one of the test's own edits. After
    stop the recorded ``zensical serve`` process has a return code, read before
    the test's own cleanup can kill it, and its pid is not alive.

    Dies on: `sync_tree(tree, live)` replaced by a swap of `live/staged` for a
    freshly written directory (the edit is never served: "not within 20.0 s");
    the `sync_tree` call removed (no home page: "the preview loop ended");
    the `print(problem.render(), ...)` removed (no problem lines);
    `live/staged` removed before the failure lines are printed (`/why/` then
    answers 404); `_terminate(process)` removed ("the serve process outlived
    the stop").

    Replacing it with `write_tree(tree, live)`, or deleting `live/` and
    renaming a freshly written directory into its place, stays green here, because
    `zensical serve` picks those up (`test_a_later_success_syncs_live_in_place`
    reds both). Renaming `live/` aside and renaming a fresh directory in is a
    rename-swap and goes red like the `live/staged` swap.
    """
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    broken = copy_fixture_tree(FIXTURE, tmp_path, "broken-reference")
    why = "why.md"
    pristine = (content / why).read_text(encoding="utf-8")
    assert pristine.count("A single valid tree") == 1
    assert pristine.count("section: Why\n") == 1
    edited = pristine.replace(
        "A single valid tree", "EDITMARKERONE a single valid tree"
    )
    breakage = edited.replace("section: Why\n", "section: Nowhere\n")
    fixed = pristine.replace("A single valid tree", "EDITMARKERTWO a single valid tree")
    write(broken / why, breakage)
    reference = build(broken, tmp_path / "reference", repo_root=REPO_ROOT)
    assert not reference.ok
    reference_lines = [p.render() for p in reference.problems]
    assert reference_lines

    procs: list[subprocess.Popen[bytes]] = []

    def recording_start(live: Path, addr: str) -> subprocess.Popen[bytes]:
        process = generator.start_serve(live, addr)
        procs.append(process)
        return process

    monkeypatch.setattr(preview, "start_serve", recording_start)
    addr = f"127.0.0.1:{free_port()}"
    stop = threading.Event()
    out = LockedOut()
    result: list[int] = []
    raised: list[BaseException] = []

    def target() -> None:
        try:
            result.append(
                preview.serve(
                    content,
                    tmp_path / "preview",
                    repo_root=REPO_ROOT,
                    addr=addr,
                    poll_interval=0.1,
                    stop=stop,
                    out=out,
                )
            )
        except BaseException as error:
            raised.append(error)

    thread = threading.Thread(target=target, daemon=True)
    pages: dict[str, str] = {}

    def served(path: str, needle: str) -> Callable[[], bool]:
        def check() -> bool:
            status, body = fetch(addr, path)
            pages[path] = body
            return status == 200 and needle in body

        return check

    def status_is(path: str, code: int) -> Callable[[], bool]:
        return lambda: fetch(addr, path)[0] == code

    def unchanged_across(label: str, ready: Callable[[], bool]) -> Callable[[], bool]:
        """Wrap a wait so the content copy is hashed before it and after it."""
        before = dir_hash(content)
        assert before[0] > 0

        def check() -> bool:
            done = ready()
            assert dir_hash(content) == before, f"content changed during: {label}"
            return done

        return check

    home = unchanged_across("startup", status_is("/", 200))
    try:
        thread.start()
        wait_for("the home page", home, thread)
        wait_for(
            "the original text of /why/",
            unchanged_across("startup", served("/why/", "A single valid tree")),
            thread,
        )
        assert "EDITMARKERONE" not in pages["/why/"]

        write(content / why, edited)
        wait_for(
            "the edited text of /why/",
            unchanged_across("edit", served("/why/", "EDITMARKERONE")),
            thread,
        )

        extra = content / "get-started" / "extra.md"
        assert fetch(addr, "/get-started/extra/")[0] == 404
        write(
            extra,
            "---\ntitle: Extra page\ndescription: An added page.\n"
            "section: Get started\norder: 9\n---\n\nADDEDPAGEMARKER here.\n",
        )
        wait_for(
            "the added page",
            unchanged_across("add", served("/get-started/extra/", "ADDEDPAGEMARKER")),
            thread,
        )

        extra.unlink()
        wait_for(
            "a 404 for the deleted page",
            unchanged_across("delete", status_is("/get-started/extra/", 404)),
            thread,
        )
        assert out.text() == ""

        write(content / why, breakage)
        wait_for(
            "the problem lines",
            unchanged_across(
                "break", lambda: out.text().splitlines() == reference_lines
            ),
            thread,
        )
        time.sleep(1.0)
        assert out.text().splitlines() == reference_lines
        status, body = fetch(addr, "/why/")
        assert status == 200
        assert "EDITMARKERONE" in body
        assert "Nowhere" not in body

        write(content / why, fixed)
        wait_for(
            "the fixed text of /why/",
            unchanged_across("fix", served("/why/", "EDITMARKERTWO")),
            thread,
        )
        assert "EDITMARKERONE" not in pages["/why/"]
        assert out.text().splitlines() == reference_lines
        assert len(procs) == 1
        assert procs[0].poll() is None
    finally:
        stop.set()
        thread.join(30)
        after_stop = [process.poll() for process in procs]
        for process in procs:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert not thread.is_alive(), "the preview loop did not stop"
    assert raised == []
    assert result == [0]
    assert len(procs) == 1
    assert after_stop[0] is not None, "the serve process outlived the stop"
    with pytest.raises(ProcessLookupError):
        os.kill(procs[0].pid, 0)
