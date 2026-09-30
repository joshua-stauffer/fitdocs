"""The only code that knows Zensical's command line and output format (6.1, 6.2, 6.5).

Zensical runs as a subprocess and is never imported. `translate` turns its
report into `Problem` lines; a traceback is never part of one.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.sitebuild.model import Problem

GENERATOR_PATH = "site generator"  # Problem.path for a problem naming no file
_ABORT_MESSAGE = "Aborted because --strict flag is set"
_TRACEBACK_HEADER = "Traceback (most recent call last):"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_REPORT_LINE = re.compile(r"^(Warning|Error|RuntimeError):(.*)$")
_FRAME = re.compile(r"^\s*╭─\[\s*(.+):(\d+):(\d+)\s*\]\s*$")


class GeneratorMissing(Exception):
    """The generator executable is not installed next to the interpreter."""


@dataclass(frozen=True)
class GeneratorResult:
    ok: bool
    problems: tuple[Problem, ...]
    output: str  # ANSI-stripped combined output, for --verbose


def generator_executable() -> Path:
    """`zensical` next to the running interpreter, never found through PATH."""
    executable = Path(sys.executable).parent / "zensical"
    if not executable.is_file():
        raise GeneratorMissing(
            f"the site generator is not installed at {executable}; "
            "run `uv sync --group docs`"
        )
    return executable


def run_build(root: Path) -> GeneratorResult:
    """Build the site in ``root``; the config's ``strict: true`` makes issues fail."""
    completed = subprocess.run(
        [str(generator_executable()), "build", "-f", "mkdocs.yml", "--clean"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout = completed.stdout
    if stdout and not stdout.endswith("\n"):
        stdout += "\n"
    output = _ANSI.sub("", stdout + completed.stderr)
    return GeneratorResult(
        ok=completed.returncode == 0,
        problems=translate(output, completed.returncode),
        output=output,
    )


def translate(output: str, returncode: int) -> tuple[Problem, ...]:
    """Turn the generator's report into problems, in output order."""
    lines = _ANSI.sub("", output).splitlines()
    report = _outside_traceback(lines)
    problems: list[Problem] = []
    for index, line in enumerate(report):
        match = _REPORT_LINE.match(line)
        if match is None:
            continue
        kind, message = match.group(1), match.group(2).strip()
        if kind == "Warning":
            problems.append(_warning(message, report[index + 1 :]))
        elif message != _ABORT_MESSAGE:
            problems.append(Problem(GENERATOR_PATH, "", message))
    if problems or returncode == 0:
        return tuple(problems)
    tail = [line.strip() for line in report if line.strip()]
    if tail:
        return (Problem(GENERATOR_PATH, "", tail[-1]),)
    return (Problem(GENERATOR_PATH, "", f"exited with status {returncode}"),)


def _outside_traceback(lines: list[str]) -> list[str]:
    """Drop each traceback header and its indented frames.

    The exception line that ends a traceback is not indented and stays.
    """
    kept: list[str] = []
    in_traceback = False
    for line in lines:
        if line == _TRACEBACK_HEADER:
            in_traceback = True
        elif in_traceback and line[:1].isspace():
            continue
        else:
            in_traceback = False
            kept.append(line)
    return kept


def _warning(message: str, following: list[str]) -> Problem:
    """Pair a warning with its own frame: the first one before the next report line."""
    for line in following:
        if _REPORT_LINE.match(line):
            break
        frame = _FRAME.match(line)
        if frame is not None:
            return Problem(
                frame.group(1), f"{frame.group(2)}:{frame.group(3)}", message
            )
    return Problem(GENERATOR_PATH, "", message)


def start_serve(root: Path, addr: str) -> subprocess.Popen[bytes]:
    """Start ``zensical serve`` in ``root``; the caller owns the process."""
    return subprocess.Popen(
        [str(generator_executable()), "serve", "-f", "mkdocs.yml", "-a", addr],
        cwd=root,
    )
