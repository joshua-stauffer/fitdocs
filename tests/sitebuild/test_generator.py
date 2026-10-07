"""The generator wrapper: locate, run, translate (6.1, 6.2, 6.5).

None of these tests needs Zensical installed. The constants
`STRICT_WARNINGS`, `CONFIG_ERROR` and `TEMPLATE_ERROR` below are the output of
`zensical build -f mkdocs.yml` 0.0.65 over throwaway projects (a broken page
link in one file and a broken anchor in another; invalid config YAML; a missing
`template:`), stdout followed by
stderr, ANSI intact. The only edit is the repository checkout path in the
traceback frames, replaced by `/path/to/repo`. The same builds under
`TERM=dumb NO_COLOR=1` produced byte-identical output, so there is no second
set of constants.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.sitebuild import generator
from scripts.sitebuild.generator import (
    GeneratorMissing,
    generator_executable,
    run_build,
    start_serve,
    translate,
)
from scripts.sitebuild.model import Problem

ANSI = re.compile(r"\x1b\[[0-9;]*m")
TRACEBACK_HEADER = "Traceback (most recent call last):"

STRICT_WARNINGS = (
    "Build started\n"
    "\u001b[33mWarning:\u001b[0m page does not exist\n"
    "   \u001b[38;5;246m╭\u001b[0m\u001b[38;5;246m─\u001b[0m\u001b[38;5"
    ";246m[\u001b[0m index.md:3:12 \u001b[38;5;246m]\u001b[0m\n"
    "   \u001b[38;5;246m│\u001b[0m\n"
    " \u001b[38;5;246m3 │\u001b[0m \u001b[38;5;249mS\u001b[0m\u001b[38;"
    "5;249me\u001b[0m\u001b[38;5;249me\u001b[0m\u001b[38;5;249m \u001b["
    "0m\u001b[38;5;249m[\u001b[0m\u001b[38;5;249mg\u001b[0m\u001b[38;5;"
    "249mo\u001b[0m\u001b[38;5;249mn\u001b[0m\u001b[38;5;249me\u001b[0m"
    "\u001b[38;5;249m]\u001b[0m\u001b[38;5;249m(\u001b[0m\u001b[33mm"
    "\u001b[0m\u001b[33mi\u001b[0m\u001b[33ms\u001b[0m\u001b[33ms\u001b"
    "[0m\u001b[33mi\u001b[0m\u001b[33mn\u001b[0m\u001b[33mg\u001b[0m"
    "\u001b[33m.\u001b[0m\u001b[33mm\u001b[0m\u001b[33md\u001b[0m\u001b"
    "[38;5;249m)\u001b[0m\u001b[38;5;249m \u001b[0m\u001b[38;5;249mh"
    "\u001b[0m\u001b[38;5;249me\u001b[0m\u001b[38;5;249mr\u001b[0m"
    "\u001b[38;5;249me\u001b[0m\u001b[38;5;249m.\u001b[0m\n"
    " \u001b[38;5;240m  │\u001b[0m            \u001b[33m─\u001b[0m"
    "\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b"
    "[33m─\u001b[0m\u001b[33m┬\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─"
    "\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m  \n"
    " \u001b[38;5;240m  │\u001b[0m                 \u001b[33m╰\u001b[0m"
    "\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b"
    "[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m page does n"
    "ot exist\n"
    "\u001b[38;5;246m───╯\u001b[0m\n"
    "\u001b[33mWarning:\u001b[0m anchor does not exist\n"
    "   \u001b[38;5;246m╭\u001b[0m\u001b[38;5;246m─\u001b[0m\u001b[38;5"
    ";246m[\u001b[0m other.md:3:28 \u001b[38;5;246m]\u001b[0m\n"
    "   \u001b[38;5;246m│\u001b[0m\n"
    " \u001b[38;5;246m3 │\u001b[0m \u001b[38;5;249mT\u001b[0m\u001b[38;"
    "5;249me\u001b[0m\u001b[38;5;249mx\u001b[0m\u001b[38;5;249mt\u001b["
    "0m\u001b[38;5;249m \u001b[0m\u001b[38;5;249m[\u001b[0m\u001b[38;5;"
    "249mb\u001b[0m\u001b[38;5;249ma\u001b[0m\u001b[38;5;249md\u001b[0m"
    "\u001b[38;5;249m \u001b[0m\u001b[38;5;249ma\u001b[0m\u001b[38;5;24"
    "9mn\u001b[0m\u001b[38;5;249mc\u001b[0m\u001b[38;5;249mh\u001b[0m"
    "\u001b[38;5;249mo\u001b[0m\u001b[38;5;249mr\u001b[0m\u001b[38;5;24"
    "9m]\u001b[0m\u001b[38;5;249m(\u001b[0m\u001b[38;5;249mi\u001b[0m"
    "\u001b[38;5;249mn\u001b[0m\u001b[38;5;249md\u001b[0m\u001b[38;5;24"
    "9me\u001b[0m\u001b[38;5;249mx\u001b[0m\u001b[38;5;249m.\u001b[0m"
    "\u001b[38;5;249mm\u001b[0m\u001b[38;5;249md\u001b[0m\u001b[38;5;24"
    "9m#\u001b[0m\u001b[33ma\u001b[0m\u001b[33mb\u001b[0m\u001b[33ms"
    "\u001b[0m\u001b[33me\u001b[0m\u001b[33mn\u001b[0m\u001b[33mt\u001b"
    "[0m\u001b[38;5;249m)\u001b[0m\u001b[38;5;249m.\u001b[0m\n"
    " \u001b[38;5;240m  │\u001b[0m                            \u001b[33"
    "m─\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b[33m┬"
    "\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m  \n"
    " \u001b[38;5;240m  │\u001b[0m                               \u001b"
    "[33m╰\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─\u001b[0m\u001b[33m─"
    "\u001b[0m\u001b[33m─\u001b[0m anchor does not exist\n"
    "\u001b[38;5;246m───╯\u001b[0m\n"
    "2 issues found\n"
    "Traceback (most recent call last):\n"
    '  File "/path/to/repo/.venv/bin/zensical", line 10, in <module>'
    "\n"
    "    sys.exit(cli())\n"
    "             ^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 1631, in __call__\n'
    "    return self.main(*args, **kwargs)\n"
    "           ^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 1552, in main\n'
    "    rv = self.invoke(ctx)\n"
    "         ^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 2032, in invoke\n'
    "    return _process_result(sub_ctx.command.invoke(sub_ctx))\n"
    "                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 1415, in invoke\n'
    "    return ctx.invoke(self.callback, **ctx.params)\n"
    "           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 910, in invoke\n'
    "    return callback(*args, **kwargs)\n"
    "           ^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/zensical'
    '/main.py", line 81, in execute_build\n'
    "    build(os.path.abspath(config_file), kwargs)\n"
    "RuntimeError: Aborted because --strict flag is set\n"
)

CONFIG_ERROR = (
    "Error: Encountered an error parsing the configuration file: while "
    "parsing a flow sequence\n"
    '  in "<unicode string>", line 1, column 12:\n'
    "    site_name: [unclosed\n"
    "               ^\n"
    "expected ',' or ']', but got ':'\n"
    '  in "<unicode string>", line 2, column 9:\n'
    "    docs_dir: staged\n"
    "            ^\n"
)

TEMPLATE_ERROR = (
    "Build started\n"
    "No issues found\n"
    "Traceback (most recent call last):\n"
    '  File "/path/to/repo/.venv/bin/zensical", line 10, in <module>'
    "\n"
    "    sys.exit(cli())\n"
    "             ^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 1631, in __call__\n'
    "    return self.main(*args, **kwargs)\n"
    "           ^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 1552, in main\n'
    "    rv = self.invoke(ctx)\n"
    "         ^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 2032, in invoke\n'
    "    return _process_result(sub_ctx.command.invoke(sub_ctx))\n"
    "                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 1415, in invoke\n'
    "    return ctx.invoke(self.callback, **ctx.params)\n"
    "           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/click/co'
    're.py", line 910, in invoke\n'
    "    return callback(*args, **kwargs)\n"
    "           ^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/path/to/repo/.venv/lib/python3.11/site-packages/zensical'
    '/main.py", line 81, in execute_build\n'
    "    build(os.path.abspath(config_file), kwargs)\n"
    'RuntimeError: template not found: template "nope.html" does not '
    "exist\n"
)


# A traceback whose last line is not one Zensical produced: the exception line
# is invented, the frames are the real ones.
UNPARSED_TRACEBACK = TEMPLATE_ERROR.replace(
    'RuntimeError: template not found: template "nope.html" does not exist\n',
    "ValueError: unexpected generator failure\n",
)
# The same output cut off before its exception line.
TRUNCATED_TRACEBACK = TEMPLATE_ERROR.split("RuntimeError:")[0].rstrip("\n")
# Output with no report line and no traceback; the last non-empty line is coloured.
UNPARSED_TAIL = (
    "Build started\n"
    "something the parser has never seen\n"
    "\x1b[31mthe last real line\x1b[0m\n"
    "\n"
    "   \n"
)

CONTENT_ENV = ("FITDOCS_SITE_CONTENT", "FITDOCS_FORBIDDEN_STRINGS", "FITDOCS_DATA")


def traceback_body(output: str) -> list[str]:
    """The stripped, non-empty indented lines that follow each traceback header."""
    body: list[str] = []
    in_traceback = False
    for line in ANSI.sub("", output).splitlines():
        if line == TRACEBACK_HEADER:
            in_traceback = True
        elif in_traceback and line[:1].isspace():
            if line.strip():
                body.append(line.strip())
        else:
            in_traceback = False
    return body


def assert_no_traceback(output: str, problems: tuple[Problem, ...]) -> None:
    body = traceback_body(output)
    assert len(body) >= 10, "the output has no traceback to keep out"
    assert "sys.exit(cli())" in body
    rendered = [problem.render() for problem in problems]
    for line in body:
        assert not any(line in text for text in rendered), line
    assert not any(TRACEBACK_HEADER in text for text in rendered)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CONTENT_ENV:
        monkeypatch.delenv(name, raising=False)


def fake_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `sys.executable` at `tmp_path/bin/python` and return that bin dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(sys, "executable", str(bin_dir / "python"))
    return bin_dir


def write_stub(path: Path, script: str) -> None:
    path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    path.chmod(0o755)


def record_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# -- translate ---------------------------------------------------------------


def test_strict_capture_gives_one_problem_per_warning() -> None:
    """Two warnings in two files become two located problems, in order.

    The report is coloured, carries the message a second time inside each
    frame, ends in a traceback and then the strict-abort RuntimeError line,
    and the exit status is 1.

    Dies on: `_ANSI.sub` dropped from `translate` (no coloured `Warning:`
    line matches, so the only problem is the fallback's strict-abort line);
    `translate` stopping after the first warning (`break` after the first
    append); `_warning` scanning `following` in reverse with no `break` on
    the next report line, so it reads the last frame of the output; the
    `elif message != _ABORT_MESSAGE` guard replaced by `elif True` (a third
    problem carries the abort line).
    """
    problems = translate(STRICT_WARNINGS, 1)
    assert "\x1b[" in STRICT_WARNINGS
    assert problems == (
        Problem("index.md", "3:12", "page does not exist"),
        Problem("other.md", "3:28", "anchor does not exist"),
    )
    assert_no_traceback(STRICT_WARNINGS, problems)


def test_config_error_capture_is_one_generator_problem() -> None:
    """A config `Error:` line is one path-less problem: its first line only.

    The YAML detail lines under it are not part of the problem.

    Dies on: `Error` removed from `_REPORT_LINE` (the fallback then reports
    the last non-empty line, a YAML caret line).
    """
    assert translate(CONFIG_ERROR, 1) == (
        Problem(
            "site generator",
            "",
            "Encountered an error parsing the configuration file: "
            "while parsing a flow sequence",
        ),
    )


def test_template_runtime_error_capture_is_one_generator_problem() -> None:
    """A non-abort `RuntimeError:` is one path-less problem and no traceback.

    The capture holds `No issues found` and a traceback before the line.

    Dies on: `RuntimeError` dropped from `_REPORT_LINE` (the fallback then
    reports the same text with a `RuntimeError: ` prefix, so the expected
    problem differs); the abort test inverted to `==`.
    """
    problems = translate(TEMPLATE_ERROR, 1)
    assert problems == (
        Problem(
            "site generator",
            "",
            'template not found: template "nope.html" does not exist',
        ),
    )
    assert_no_traceback(TEMPLATE_ERROR, problems)


def test_unparsed_failure_falls_back_to_the_last_non_empty_line() -> None:
    """Non-zero exit and nothing parsed: the last non-empty line, uncoloured.

    Blank and whitespace-only lines follow it, and other lines precede it.

    Dies on: the fallback taking `tail[0]` (`Build started`); taking
    `report[-1]` (a blank line); `_ANSI.sub` dropped from `translate`.
    """
    assert translate(UNPARSED_TAIL, 2) == (
        Problem("site generator", "", "the last real line"),
    )


def test_padded_last_line_is_stripped() -> None:
    """The fallback line has no surrounding whitespace.

    Dies on: `.strip()` removed from the `tail` comprehension in `translate`.
    """
    assert translate("boom\n   padded failure line \t\n", 1) == (
        Problem("site generator", "", "padded failure line"),
    )


def test_zero_exit_with_unparsed_output_reports_nothing() -> None:
    """The last-line fallback belongs to failures only.

    Dies on: `if problems or returncode == 0` reduced to `if problems`.
    """
    assert UNPARSED_TAIL.strip()
    assert translate(UNPARSED_TAIL, 0) == ()


def test_failure_with_no_output_names_the_exit_status() -> None:
    """A failing run that printed nothing still yields one problem.

    Dies on: the last `return` of `translate` replaced by `return ()`.
    """
    assert translate("", 4) == (Problem("site generator", "", "exited with status 4"),)
    assert translate("\n  \n", 5) == (
        Problem("site generator", "", "exited with status 5"),
    )


def test_unparsed_traceback_reports_only_its_exception_line() -> None:
    """A traceback ending in an unknown exception gives that one line.

    Dies on: the fallback taking `tail[0]` instead of `tail[-1]`.
    """
    problems = translate(UNPARSED_TRACEBACK, 1)
    assert problems == (
        Problem("site generator", "", "ValueError: unexpected generator failure"),
    )
    assert_no_traceback(UNPARSED_TRACEBACK, problems)


def test_truncated_traceback_reports_no_frame() -> None:
    """A traceback cut off before its exception line leaves the last line before it.

    The cut output ends on an indented frame line; that line is not
    reported.

    Dies on: `_outside_traceback` returning `lines` unchanged (the last
    frame's source line becomes the problem).
    """
    assert TRUNCATED_TRACEBACK.splitlines()[-1].startswith(" ")
    problems = translate(TRUNCATED_TRACEBACK, 1)
    assert problems == (Problem("site generator", "", "No issues found"),)
    assert_no_traceback(TRUNCATED_TRACEBACK, problems)


def test_warning_takes_its_own_frame_or_none() -> None:
    """A warning with no frame is path-less and does not borrow the next one.

    The following warning keeps its own frame, and a colon inside a path is
    part of the path.

    Dies on: the `break` on the next report line removed from `_warning`
    (the first warning takes the second's frame); the path group of `_FRAME`
    made `[^:]+` (the frame no longer matches, so the warning loses its
    path); `_warning` reading only the next line (a blank line sits between
    the warning and its frame).
    """
    output = (
        "\x1b[33mWarning:\x1b[0m no frame for this one\n"
        "\x1b[33mWarning:\x1b[0m has a frame\n"
        "\n"
        "   \x1b[38;5;246m╭\x1b[0m\x1b[38;5;246m─[\x1b[0m a:b.md:7:9 "
        "\x1b[38;5;246m]\x1b[0m\n"
    )
    assert translate(output, 1) == (
        Problem("site generator", "", "no frame for this one"),
        Problem("a:b.md", "7:9", "has a frame"),
    )


def test_report_words_inside_a_quoted_source_line_are_not_reports() -> None:
    """Only a line that starts with the word is a report line.

    A frame shows the document's own text, which can say `Error:` or
    `Warning:`.

    Dies on: `_REPORT_LINE` changed to `^.*?(Warning|Error|RuntimeError):(.*)$`.
    """
    output = (
        "Warning: real one\n"
        "   ╭─[ doc.md:2:1 ]\n"
        "   │\n"
        " 2 │ Error: quoted from the page\n"
        " 3 │ RuntimeError: also quoted, Warning: as well\n"
        "───╯\n"
    )
    assert translate(output, 1) == (Problem("doc.md", "2:1", "real one"),)


# -- generator_executable ----------------------------------------------------


def test_executable_is_found_next_to_the_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The result is `<dir of sys.executable>/zensical`, not a PATH hit.

    A different `zensical` sits first on PATH.

    Dies on: the executable taken from `shutil.which("zensical")`; `.parent`
    dropped from `Path(sys.executable).parent`.
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    write_stub(bin_dir / "zensical", "exit 0\n")
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    write_stub(decoy / "zensical", "exit 0\n")
    monkeypatch.setenv("PATH", str(decoy))
    assert generator_executable() == bin_dir / "zensical"


def test_missing_executable_raises_with_the_fix_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing next to the interpreter raises `GeneratorMissing`.

    A `zensical` on PATH does not count, and the message carries the fix.

    Dies on: the `raise` replaced by a call that returns; the message losing
    `uv sync --group docs`.
    """
    fake_interpreter(tmp_path, monkeypatch)
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    write_stub(decoy / "zensical", "exit 0\n")
    monkeypatch.setenv("PATH", str(decoy))
    with pytest.raises(GeneratorMissing, match=r"uv sync --group docs"):
        generator_executable()


def test_a_directory_named_zensical_is_not_the_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a file counts.

    Dies on: `executable.is_file()` changed to `executable.exists()`.
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    (bin_dir / "zensical").mkdir()
    with pytest.raises(GeneratorMissing):
        generator_executable()


# -- run_build ---------------------------------------------------------------


def build_stub(
    bin_dir: Path, tmp_path: Path, *, stdout: str, stderr: str, code: int
) -> Path:
    """Install a `zensical` that records its argv and cwd, prints, and exits."""
    record = tmp_path / "record"
    record.mkdir(exist_ok=True)
    (record / "stdout").write_bytes(stdout.encode("utf-8"))
    (record / "stderr").write_bytes(stderr.encode("utf-8"))
    write_stub(
        bin_dir / "zensical",
        f"printf '%s\\n' \"$@\" > '{record}/argv'\n"
        f"pwd -P > '{record}/cwd'\n"
        f"cat '{record}/stdout'\n"
        f"cat '{record}/stderr' >&2\n"
        f"exit {code}\n",
    )
    return record


def test_run_build_invokes_the_pinned_command_in_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command is `zensical build -f mkdocs.yml --clean`, run in the root.

    Both streams come back translated. The stdout text has no trailing
    newline and the stderr text begins with a report line, and
    `GeneratorResult.output` is the ANSI-stripped stdout then stderr.

    Dies on: `--clean` dropped, `-f` dropped or `build` changed to `serve`
    in `run_build`; `cwd=root` dropped; `capture_output` reduced to
    stdout only; the newline added after unterminated stdout removed (the
    first warning is glued to `Build started`); `ok` computed as `True`.
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    started, _, report = STRICT_WARNINGS.partition("\n")
    assert started == "Build started"
    record = build_stub(bin_dir, tmp_path, stdout=started, stderr=report, code=1)
    root = tmp_path / "root"
    root.mkdir()
    result = run_build(root)
    assert record_lines(record / "argv") == ["build", "-f", "mkdocs.yml", "--clean"]
    assert record_lines(record / "cwd") == [str(root.resolve())]
    assert result.ok is False
    assert result.problems == translate(STRICT_WARNINGS, 1)
    assert len(result.problems) == 2
    assert result.output == ANSI.sub("", STRICT_WARNINGS)
    assert "\x1b" not in result.output


def test_run_build_success_is_ok_with_no_problems(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit status 0 is `ok`, and the output is kept for `--verbose`.

    Dies on: `ok=completed.returncode == 0` changed to `ok=False`; the
    fallback in `translate` firing on exit status 0.
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    build_stub(
        bin_dir, tmp_path, stdout="\x1b[32mBuild started\x1b[0m\n", stderr="", code=0
    )
    root = tmp_path / "root"
    root.mkdir()
    result = run_build(root)
    assert result == generator.GeneratorResult(
        ok=True, problems=(), output="Build started\n"
    )


def test_run_build_survives_undecodable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A byte that is not UTF-8 does not abort the wrapper.

    Dies on: `errors="replace"` removed from the `subprocess.run` call.
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    write_stub(bin_dir / "zensical", "printf 'bad \\377 byte\\n'\nexit 1\n")
    root = tmp_path / "root"
    root.mkdir()
    result = run_build(root)
    assert result.problems == (Problem("site generator", "", "bad � byte"),)


def test_run_build_without_the_generator_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing executable surfaces as `GeneratorMissing`, not a `FileNotFoundError`.

    Dies on: `run_build` building the argv from `"zensical"` instead of
    `generator_executable()`.
    """
    fake_interpreter(tmp_path, monkeypatch)
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(GeneratorMissing):
        run_build(root)


# -- start_serve -------------------------------------------------------------


def test_start_serve_returns_the_live_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`zensical serve -f mkdocs.yml -a <addr>` runs in the root, unwaited.

    The stub holds until a release file appears, so the process is still
    running when the function returns.

    Dies on: `-a` changed to `--addr`, or the address dropped; `cwd=root`
    dropped; `Popen` replaced by `subprocess.run` (the call waits for the
    stub and returns no process).
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    record = tmp_path / "record"
    record.mkdir()
    write_stub(
        bin_dir / "zensical",
        f"printf '%s\\n' \"$@\" > '{record}/argv'\n"
        f"pwd -P > '{record}/cwd'\n"
        "i=0\n"
        f"while [ ! -f '{record}/release' ] && [ $i -lt 100 ]; do\n"
        "  sleep 0.1\n"
        "  i=$((i+1))\n"
        "done\n",
    )
    root = tmp_path / "root"
    root.mkdir()
    process = start_serve(root, "127.0.0.1:8123")
    try:
        assert isinstance(process, subprocess.Popen)
        assert process.poll() is None
        (record / "release").write_text("", encoding="utf-8")
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert record_lines(record / "argv") == [
        "serve",
        "-f",
        "mkdocs.yml",
        "-a",
        "127.0.0.1:8123",
    ]
    assert record_lines(record / "cwd") == [str(root.resolve())]


def test_start_serve_selects_the_polling_watcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The serve process polls for changes and keeps the caller's environment.

    The native watcher relies on macOS FSEvents. When `fseventsd` is saturated,
    those events arrive late or not at all, and the preview keeps serving stale
    pages (`.kiro/queue/2026-10-06-preview-delete-readiness-race.md`). Zensical
    uses its polling watcher when `ZENSICAL_POLL_WATCHER` is set.

    Dies on: the variable dropped (`unset`); the inherited environment replaced
    by the variable alone (the sentinel is lost).
    """
    bin_dir = fake_interpreter(tmp_path, monkeypatch)
    monkeypatch.delenv("ZENSICAL_POLL_WATCHER", raising=False)
    monkeypatch.setenv("FITDOCS_SERVE_SENTINEL", "kept")
    record = tmp_path / "record"
    record.mkdir()
    write_stub(
        bin_dir / "zensical",
        f"printf '%s\\n' \"${{ZENSICAL_POLL_WATCHER-unset}}\" > '{record}/poll'\n"
        f"printf '%s\\n' \"${{FITDOCS_SERVE_SENTINEL-unset}}\" > '{record}/sentinel'\n",
    )
    root = tmp_path / "root"
    root.mkdir()
    process = start_serve(root, "127.0.0.1:8123")
    try:
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert record_lines(record / "poll") == ["1"]
    assert record_lines(record / "sentinel") == ["kept"]
