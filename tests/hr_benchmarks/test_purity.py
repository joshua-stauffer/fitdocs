"""Clock, prompt, network and pure-module I/O guards."""

from __future__ import annotations

import ast

import pytest

from tests.hr_benchmarks.test_boundary import _module_key, _module_paths

_NETWORK_CLOCK_PROMPT_MODULES = {
    "time",
    "socket",
    "ssl",
    "urllib",
    "http",
    "httpx",
    "requests",
    "urllib3",
    "ftplib",
    "smtplib",
    "getpass",
    "typer",
    "rich",
    "subprocess",
    "random",
}
_IO_MODULES = {"pathlib", "os", "io", "tempfile", "shutil", "glob"}
_PROMPT_NAMES = {"input", "help", "breakpoint"}
_PURE_IO_NAMES = {"open", "print"}
_CLOCK_ATTRIBUTES = {"today", "now", "utcnow", "fromtimestamp", "utcfromtimestamp"}
_IO_ATTRIBUTES = {
    "open",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "stat",
    "lstat",
    "glob",
    "rglob",
    "mkdir",
    "unlink",
    "rename",
    "read",
    "readline",
    "readlines",
    "readinto",
    "read1",
    "readinto1",
    "write",
    "writelines",
    "flush",
    "truncate",
    "seek",
    "tell",
    "close",
    "fileno",
    "isatty",
    "readable",
    "writable",
    "seekable",
    "exists",
    "is_file",
    "is_dir",
    "iterdir",
    "touch",
    "rmdir",
    "chmod",
    "resolve",
    "readlink",
    "symlink_to",
    "hardlink_to",
    "samefile",
    "owner",
    "group",
    "is_symlink",
    "is_mount",
    "is_socket",
    "is_fifo",
    "is_block_device",
    "is_char_device",
    "is_junction",
    "walk",
    "expanduser",
    "absolute",
    "lchmod",
    "readall",
    "peek",
    "detach",
    "reconfigure",
    "getvalue",
    "getbuffer",
    "cwd",
    "home",
    "link_to",
}
_ESCAPE_NAMES = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "getattr",
    "globals",
    "locals",
    "vars",
    "__builtins__",
}
_ESCAPE_ATTRIBUTES = {
    "__globals__",
    "__builtins__",
    "__dict__",
    "__getattribute__",
    "import_module",
}


_PATH_CONSTRUCTORS = {"Path", "PosixPath", "WindowsPath"}


class _PathReferences(ast.NodeVisitor):
    """Recognize imported Path constructors, annotations and simple bindings."""

    def __init__(self) -> None:
        self.bindings: dict[str, str] = {}
        self.replacements: set[int] = set()

    def _constructor(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id) == "constructor"
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and self.bindings.get(node.value.id) == "pathlib"
            and node.attr in _PATH_CONSTRUCTORS
        )

    def _annotation(self, node: ast.expr | None) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                node = ast.parse(node.value, mode="eval").body
            except SyntaxError:
                return False
        return node is not None and self._constructor(node)

    def _path(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id) == "path"
        if isinstance(node, ast.Call):
            return self._constructor(node.func)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return self._path(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self._path(node.left)
        return False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "pathlib":
                self.bindings[alias.asname or alias.name] = "pathlib"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.bindings[name] = (
                "constructor"
                if node.module == "pathlib" and alias.name in _PATH_CONSTRUCTORS
                else "other"
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        binding = "path" if self._path(node.value) else "other"
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = binding

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        if isinstance(node.target, ast.Name):
            self.bindings[node.target.id] = (
                "path"
                if self._annotation(node.annotation)
                or (node.value is not None and self._path(node.value))
                else "other"
            )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        outer = self.bindings
        self.bindings = outer.copy()
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            self.bindings[argument.arg] = (
                "path" if self._annotation(argument.annotation) else "other"
            )
        self.generic_visit(node)
        self.bindings = outer

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "replace" and self._path(node.value):
            self.replacements.add(id(node))
        self.generic_visit(node)


def _purity_violations(source: str, module: str) -> list[str]:
    violations: list[str] = []
    pure = module != "engine"
    tree = ast.parse(source)
    paths = _PathReferences()
    paths.visit(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            targets = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for target in targets:
                root = target.split(".")[0]
                if root in _NETWORK_CLOCK_PROMPT_MODULES or (
                    pure and root in _IO_MODULES
                ):
                    violations.append(f"L{node.lineno}: module {target}")
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in _ESCAPE_NAMES | _PROMPT_NAMES | {
                        "wellness_archive_path",
                    } or (pure and alias.name in _PURE_IO_NAMES):
                        violations.append(f"L{node.lineno}: imported {alias.name}")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in _ESCAPE_NAMES | _PROMPT_NAMES | {"wellness_archive_path"} or (
                pure and node.id in _PURE_IO_NAMES
            ):
                violations.append(f"L{node.lineno}: name {node.id}")
        elif isinstance(node, ast.Attribute):
            if (
                node.attr
                in _CLOCK_ATTRIBUTES
                | _ESCAPE_ATTRIBUTES
                | _PROMPT_NAMES
                | {
                    "wellness_archive_path",
                    "max_heart_rate_bpm",
                    "input",
                    "prompt",
                    "confirm",
                }
                or node.attr.startswith(
                    ("st_mtime", "st_ctime", "st_atime", "st_birthtime")
                )
                or (pure and node.attr in _IO_ATTRIBUTES | _PURE_IO_NAMES)
                or (pure and id(node) in paths.replacements)
            ):
                violations.append(f"L{node.lineno}: attribute {node.attr}")
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value == "max_heart_rate_bpm":
                violations.append(f"L{node.lineno}: summary maximum key")
    return violations


def test_package_purity() -> None:
    paths = _module_paths()
    assert paths, "empty purity walk"
    for path in paths:
        assert _purity_violations(path.read_text(), _module_key(path)) == [], str(path)


@pytest.mark.parametrize(
    "source,module",
    [
        ("from datetime import datetime\ndatetime.now()", "engine"),
        ("from datetime import date as D\nclock = D.today\nclock()", "engine"),
        ("import datetime as dt\ndt.datetime.utcnow()", "engine"),
        ("input('age?')", "engine"),
        ("from builtins import input as ask\nask('x')", "engine"),
        ("builtins.input('x')", "engine"),
        ("ask = input\nask('age?')", "engine"),
        ("import time as t\nt.time()", "engine"),
        ("import urllib.request as r\nr.urlopen('x')", "engine"),
        ("from socket import socket as S\nS()", "engine"),
        ("open('x')", "maximum"),
        ("reader = open\nreader('x')", "resting"),
        ("from pathlib import Path as P\nP('x')", "types"),
        ("p.read_text()", "timeline"),
        ("p.write_bytes(b'x')", "timeline"),
        ("p.stat().st_mtime", "engine"),
        ("p.stat().st_ctime_ns", "engine"),
        ("__import__('fitdocs.index')", "engine"),
        ("loader = __import__\nloader('fitdocs.index')", "engine"),
        ("import importlib as lib\nlib.import_module('fitdocs.index')", "engine"),
        ("eval('date.today()')", "engine"),
        ("getattr(date, 'today')()", "engine"),
        ("(lambda: None).__globals__['__builtins__']", "engine"),
        ("__builtins__['input']('x')", "engine"),
        ("samples.summary.max_heart_rate_bpm", "peaks"),
        ("summary['max_heart_rate_bpm']", "peaks"),
        ("from fitdocs.layout import wellness_archive_path", "engine"),
        ("layout.wellness_archive_path(root)", "engine"),
        ("def f():\n    return datetime.now()", "engine"),
    ],
)
def test_forbidden_reference(source: str, module: str) -> None:
    assert _purity_violations(source, module)


@pytest.mark.parametrize(
    "source,module",
    [
        ("from datetime import date\nday: date\nyear = day.year", "types"),
        ("from datetime import date, timedelta\nday = date(2042, 6, 7)", "engine"),
        ("from statistics import median\nx = median(values)", "maximum"),
        ("def f(values):\n    return sorted(values, key=lambda v: v.day)", "timeline"),
        ("from pathlib import Path\nPath('x').read_text()", "engine"),
        ("open('athlete.toml', 'w')", "engine"),
        ("samples.heart_rate_bpm", "peaks"),
        ("sources.MAX_WINDOW_DAYS.value", "maximum"),
        ("key = document.replace('.md', '')", "timeline"),
        ("import dataclasses\ncopy = dataclasses.replace(entry)", "timeline"),
    ],
)
def test_sanctioned_reference(source: str, module: str) -> None:
    assert _purity_violations(source, module) == []


@pytest.mark.parametrize("module", ["peaks", "engine"])
@pytest.mark.parametrize("name", ["print", "help", "breakpoint"])
@pytest.mark.parametrize("form", ["direct", "assigned", "qualified", "imported"])
def test_builtin_io_prompt_reference(module: str, name: str, form: str) -> None:
    sources = {
        "direct": f"{name}()",
        "assigned": f"operation = {name}\noperation()",
        "qualified": f"builtins.{name}()",
        "imported": f"from builtins import {name} as operation\noperation()",
    }
    kind = {"qualified": "attribute", "imported": "imported"}.get(form, "name")
    expected = [] if name == "print" and module == "engine" else [f"L1: {kind} {name}"]
    assert _purity_violations(sources[form], module) == expected


@pytest.mark.parametrize("module", ["peaks", "engine"])
@pytest.mark.parametrize("assigned", [False, True], ids=["direct", "assigned"])
@pytest.mark.parametrize(
    "method",
    [
        "read",
        "readline",
        "readlines",
        "readinto",
        "read1",
        "readinto1",
        "write",
        "writelines",
        "flush",
        "truncate",
        "seek",
        "tell",
        "close",
        "fileno",
        "isatty",
        "readable",
        "writable",
        "seekable",
        "exists",
        "is_file",
        "is_dir",
        "iterdir",
        "touch",
        "rmdir",
        "chmod",
        "resolve",
        "readlink",
        "symlink_to",
        "hardlink_to",
        "samefile",
        "owner",
        "group",
        "is_symlink",
        "is_mount",
        "is_socket",
        "is_fifo",
        "is_block_device",
        "is_char_device",
        "is_junction",
        "walk",
        "expanduser",
        "absolute",
        "lchmod",
        "readall",
        "peek",
        "detach",
        "reconfigure",
        "getvalue",
        "getbuffer",
        "cwd",
        "home",
        "link_to",
    ],
)
def test_stream_path_reference(module: str, assigned: bool, method: str) -> None:
    operation = (
        f"operation = handle.{method}\n    operation()"
        if assigned
        else f"handle.{method}()"
    )
    source = f"def probe(handle):\n    {operation}"
    expected = [] if module == "engine" else [f"L2: attribute {method}"]
    assert _purity_violations(source, module) == expected


@pytest.mark.parametrize(
    "source,line",
    [
        ("from pathlib import Path\nPath('x').replace(target)", 2),
        ("from pathlib import Path as P\np = P('x')\np.replace(target)", 3),
        ("import pathlib as paths\npaths.Path('x').replace(target)", 2),
        ("from pathlib import PosixPath as P\np = P('x')\np.replace(target)", 3),
        ("import pathlib\np = pathlib.WindowsPath('x')\np.replace(target)", 3),
        ("from pathlib import Path\np: Path\np.replace(target)", 3),
        ("from pathlib import Path as P\ndef probe(p: P):\n    p.replace(target)", 3),
        (
            "import pathlib as paths\ndef probe(p: paths.Path):\n    p.replace(target)",
            3,
        ),
        ('from pathlib import Path\ndef probe(p: "Path"):\n    p.replace(target)', 3),
        ("from pathlib import Path\np = Path('x')\nq = p\nq.replace(target)", 4),
        (
            "from pathlib import Path\np = Path('x')\n"
            "operation = p.replace\noperation(target)",
            3,
        ),
        ("from pathlib import Path\np = Path('x')\np.parent.replace(target)", 3),
        ("from pathlib import Path\np = Path('x') / child\np.replace(target)", 3),
    ],
    ids=[
        "constructor",
        "constructor-alias",
        "module-alias",
        "posix-alias",
        "windows",
        "variable-annotation",
        "argument-annotation",
        "qualified-annotation",
        "string-annotation",
        "path-alias",
        "method-alias",
        "parent",
        "join",
    ],
)
@pytest.mark.parametrize("module", ["peaks", "engine"])
def test_contextual_path_replace(source: str, line: int, module: str) -> None:
    replacements = [
        v for v in _purity_violations(source, module) if v.endswith("attribute replace")
    ]
    assert replacements == (
        [] if module == "engine" else [f"L{line}: attribute replace"]
    )


@pytest.mark.parametrize(
    "source",
    [
        "key = 'document.md'.replace('.md', '')",
        "document: str\nkey = document.replace('.md', '')",
        "document = 'document.md'\nkey = document.replace('.md', '')",
        "import dataclasses\ncopy = dataclasses.replace(entry)",
        "import dataclasses as dc\ncopy = dc.replace(entry)",
        "from dataclasses import replace as copy\ncopy(entry)",
    ],
    ids=[
        "string-literal",
        "string-annotation",
        "string-assignment",
        "dataclass",
        "dataclass-module-alias",
        "dataclass-function-alias",
    ],
)
def test_known_nonpath_replace(source: str) -> None:
    assert _purity_violations(source, "timeline") == []


@pytest.mark.parametrize(
    "source",
    [
        "def probe(handle):\n    return handle.replace(target)",
        "def probe(callback):\n    return callback()",
    ],
    ids=["untyped-replace", "injected-callback"],
)
def test_static_semantic_limits(source: str) -> None:
    assert _purity_violations(source, "peaks") == []
