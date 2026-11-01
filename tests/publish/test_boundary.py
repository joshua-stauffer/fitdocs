"""The `fitdocs.publish` package boundary (publish-core task 1.3; Req 6.1,
7.5). See the "Allowed Dependencies" section of
`.kiro/specs/publish-core/design.md`.

Modelled on `tests/connectors/test_boundary.py`, narrowed to what this
package needs:

1. **Direct non-standard-library imports per module**, pinned by equality
   against the hand-written `_ALLOWED_IMPORT_TARGETS` literal, which is checked
   against the package directory in both directions.
2. **Forbidden names**, independent of that literal: the render layer and
   its siblings, the standard-library modules whose purpose is opening
   connections plus the URL-fetching XML parsers, and any
   third-party name outside the one the design admits.
3. **Clock and randomness spellings**, so `now` and the publication-id
   source stay injected by the CLI rather than read inside the package.

**Resolved design conflict.** The design's "Allowed Dependencies" bullet says
no publish module imports `urllib`. `fitdocs.publish.request` imports
`urllib.parse.urlsplit` for the link rule, which only parses text and opens
nothing. The guard therefore forbids `urllib` as a whole *except*
`urllib.parse`; `urllib.request`, `urllib.error` and every other part of the
network-capable standard library stay forbidden, in both the `import` and the
`from ... import` forms.

**Adding a module.** Each later task appends one entry for its module to
`_ALLOWED_IMPORT_TARGETS` (the literal is written so that an added entry is a
one-hunk addition) and, if it needs a third-party name, one line to
`_THIRD_PARTY_ALLOWED_MODULES`. The clock and randomness scan reads raw
text, so a docstring or comment must not quote a spelling such as
`datetime.now(UTC)` or `secrets.token_hex`.

The guard is a static import-and-spelling scan. Reaching a module by
attribute through a module object (`__import__(...).x`, `import_module(...).x`,
`sys.modules[...]`, `exec`/`eval`) is outside its scope.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import warnings
from pathlib import Path
from typing import Final

import pytest

import fitdocs
import fitdocs.publish

# --------------------------------------------------------------------------- #
# The registry (append-friendly: one entry per module, appended by its task)
# --------------------------------------------------------------------------- #

#: Every module's exact set of direct *non-standard-library* import targets
#: (`fitdocs.*` dotted targets and third-party top-level names; the standard
#: library is decided by `sys.stdlib_module_names`). An equality pin: an added
#: import without an entry change fails, and a stale entry fails too.
#: APPEND a new entry here when you add a module under `fitdocs/publish/`.
_ALLOWED_IMPORT_TARGETS: Final[dict[str, frozenset[str]]] = {
    "fitdocs.publish": frozenset(),
    "fitdocs.publish.compose": frozenset(
        {
            "fitdocs.publish.outcomes",
            "fitdocs.publish.request",
            "fitdocs.publish.template",
            "fitdocs.publish.values",
        }
    ),
    "fitdocs.publish.ledger": frozenset(
        {
            "fitdocs.docio",
            "fitdocs.layout",
            "fitdocs.publish.request",
            "tomli_w",
        }
    ),
    "fitdocs.publish.outcomes": frozenset(),
    "fitdocs.publish.request": frozenset({"fitdocs.publish.outcomes"}),
    "fitdocs.publish.settings": frozenset(
        {
            "fitdocs.publish.template",
            "fitdocs.publish.values",
            "fitdocs.settings",
        }
    ),
    "fitdocs.publish.targets": frozenset(
        {
            "fitdocs.connectors.credentials",
            "fitdocs.connectors.errors",
            "fitdocs.connectors.http",
            "fitdocs.connectors.protocol",
            "fitdocs.connectors.secrets",
            "fitdocs.connectors.settings",
            "fitdocs.publish.outcomes",
            "fitdocs.publish.request",
        }
    ),
    "fitdocs.publish.template": frozenset(),
    "fitdocs.publish.values": frozenset({"fitdocs.contract"}),
}

#: Third-party top-level names admitted, and the modules each is admitted in.
#: Append-only like the registry.
_THIRD_PARTY_ALLOWED_MODULES: Final[dict[str, frozenset[str]]] = {
    "tomli_w": frozenset({"fitdocs.publish.ledger"}),
}

#: Forbidden `fitdocs` targets (the design's list: render, load, metrics,
#: ingestion, sync, index, query, dashboards, identity), plus the CLI (which
#: injects `now` and `mint_id` and so sits above this package) and
#: `fitdocs.tiles`, a module that opens network connections. The other such
#: module, `fitdocs.connectors` (`connectors.http`), is not listed: the design
#: lets `fitdocs.publish.targets` reach it, and the layer-1 registry pins that.
_FORBIDDEN_FITDOCS: Final[tuple[str, ...]] = (
    "fitdocs.render",
    "fitdocs.load",
    "fitdocs.metrics",
    "fitdocs.ingest",
    "fitdocs.sync",
    "fitdocs.index",
    "fitdocs.query",
    "fitdocs.dashboards",
    "fitdocs.identity",
    "fitdocs.cli",
    "fitdocs.tiles",
)

#: Standard-library modules whose purpose is opening connections, plus the
#: XML parsers that fetch a URL given as their source (`xml.sax.parse(url)`
#: calls `urlopen`), each forbidden together with its submodules. An entry may
#: be dotted (`logging.handlers`, whose `SocketHandler` opens sockets, while
#: plain `logging` stays allowed). Modules that only touch a socket
#: incidentally (`email.utils`, `mailbox`, `importlib.metadata`) are
#: deliberately not listed.
_FORBIDDEN_STDLIB: Final[tuple[str, ...]] = (
    "socket",
    "ssl",
    "http",
    "urllib",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "nntplib",
    "telnetlib",
    "xmlrpc",
    "socketserver",
    "asyncio",
    "selectors",
    "select",
    "webbrowser",
    "wsgiref",
    "_socket",
    "_ssl",
    "asyncore",
    "asynchat",
    "smtpd",
    "multiprocessing",
    "logging.handlers",
    "xml.sax",
    "xml.dom.xmlbuilder",
    "xml.dom.pulldom",
)

#: The one carve-out inside `_FORBIDDEN_STDLIB`: the link rule in
#: `fitdocs.publish.request` calls `urllib.parse.urlsplit`, which parses a
#: string and opens no connection. `urllib.request` / `urllib.error` stay out.
_STDLIB_ADMITTED: Final[tuple[str, ...]] = ("urllib.parse",)

_PUBLISH_MODULE_PREFIX: Final = "fitdocs.publish"

# --------------------------------------------------------------------------- #
# Enumeration, source access
# --------------------------------------------------------------------------- #


def _package_dir() -> Path:
    path = fitdocs.publish.__file__
    assert path is not None, "fitdocs.publish has no __file__"
    return Path(path).parent


def _module_names_under(root: Path) -> frozenset[str]:
    """Every `*.py` file under `root` as a dotted `fitdocs.publish...` name."""
    names: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        parts = (
            rel.parts[:-1] if rel.name == "__init__.py" else rel.with_suffix("").parts
        )
        names.add(".".join((_PUBLISH_MODULE_PREFIX, *parts)))
    return frozenset(names)


def _module_path(module_name: str, root: Path | None = None) -> Path:
    base = root if root is not None else _package_dir()
    rel = module_name.removeprefix(_PUBLISH_MODULE_PREFIX).lstrip(".")
    if not rel:
        return base / "__init__.py"
    as_path = base / Path(*rel.split("."))
    return as_path / "__init__.py" if as_path.is_dir() else as_path.with_suffix(".py")


def _enclosing_package(module_name: str, *, is_package: bool) -> str:
    return module_name if is_package else module_name.rsplit(".", 1)[0]


def _registry_mismatches(
    registry_names: frozenset[str], on_disk: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """(registered but absent from disk, on disk but unregistered)."""
    return registry_names - on_disk, on_disk - registry_names


class TestEnumerationIsComplete:
    def test_registry_names_equal_the_directory_listing(self) -> None:
        on_disk = _module_names_under(_package_dir())
        missing, unregistered = _registry_mismatches(
            frozenset(_ALLOWED_IMPORT_TARGETS), on_disk
        )
        assert not missing, f"registered but missing on disk: {sorted(missing)}"
        assert not unregistered, f"on disk but not registered: {sorted(unregistered)}"

    def test_the_walk_finds_the_two_seeded_leaves(self) -> None:
        on_disk = _module_names_under(_package_dir())
        assert {
            "fitdocs.publish",
            "fitdocs.publish.outcomes",
            "fitdocs.publish.request",
        } <= on_disk, f"the walk is looking at the wrong directory: {sorted(on_disk)}"

    def test_positive_control_an_unregistered_file_and_a_stale_entry_are_seen(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "outcomes.py").write_text("", encoding="utf-8")
        (tmp_path / "sneaky.py").write_text("", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "sub" / "deep.py").write_text("", encoding="utf-8")
        on_disk = _module_names_under(tmp_path)
        assert on_disk == {
            "fitdocs.publish",
            "fitdocs.publish.outcomes",
            "fitdocs.publish.sneaky",
            "fitdocs.publish.sub",
            "fitdocs.publish.sub.deep",
        }
        registered = frozenset(
            {"fitdocs.publish", "fitdocs.publish.outcomes", "fitdocs.publish.gone"}
        )
        missing, unregistered = _registry_mismatches(registered, on_disk)
        assert missing == {"fitdocs.publish.gone"}
        assert unregistered == {
            "fitdocs.publish.sneaky",
            "fitdocs.publish.sub",
            "fitdocs.publish.sub.deep",
        }


# --------------------------------------------------------------------------- #
# Import resolution
# --------------------------------------------------------------------------- #


def _is_importable_module(dotted: str) -> bool:
    # Resolving a name under a deprecated stdlib module (`asyncore`) imports
    # it; the deprecation warning is not this guard's business.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            return importlib.util.find_spec(dotted) is not None
        except (ImportError, ValueError):
            return False


def _from_targets(node: ast.ImportFrom, enclosing: str) -> set[str]:
    """The dotted target(s) one `from ... import ...` reaches.

    A name that is itself a real submodule resolves to that submodule
    (`from fitdocs.publish import outcomes` -> `fitdocs.publish.outcomes`,
    `from urllib import request` -> `urllib.request`); otherwise the statement
    resolves to its base module (`from fitdocs import __version__` ->
    `fitdocs`).
    """
    if node.level == 0:
        base = node.module
    else:
        try:
            base = importlib.util.resolve_name(
                "." * node.level + (node.module or ""), enclosing
            )
        except ImportError:
            return set()
    if base is None:
        return set()
    submodules = {
        f"{base}.{alias.name}"
        for alias in node.names
        if _is_importable_module(f"{base}.{alias.name}")
    }
    return submodules or {base}


_DYNAMIC_IMPORT_NAMES: Final = frozenset({"import_module", "__import__"})


def _dynamic_import_target(node: ast.Call, names: frozenset[str]) -> str | None:
    """`importlib.import_module("x")` / `import_module("x")` / `__import__("x")`
    -> `"x"`; a call whose first argument is not a string literal -> `"?"`
    (an unresolvable dynamic import is itself an offence); anything else ->
    None."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name not in names:
        return None
    if (
        node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return "?"


def _import_targets_of_tree(
    tree: ast.Module, module_name: str, *, is_package: bool = False
) -> frozenset[str]:
    """Every distinct dotted target the module directly imports, aliasing
    forms resolved (`import X as Y` -> `X`), dynamic imports included."""
    enclosing = _enclosing_package(module_name, is_package=is_package)
    targets: set[str] = set()
    # `from importlib import import_module as im` renames the call.
    names = set(_DYNAMIC_IMPORT_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            names.update(
                a.asname for a in node.names if a.asname and a.name == "import_module"
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
                # `import urllib.parse` binds `urllib`, through which
                # `urllib.request` is reachable; `import ... as x` binds
                # only the named submodule.
                top = alias.name.split(".", 1)[0]
                if alias.asname is None and top in _FORBIDDEN_STDLIB:
                    targets.add(top)
        elif isinstance(node, ast.ImportFrom):
            targets |= _from_targets(node, enclosing)
        elif isinstance(node, ast.Call):
            dynamic = _dynamic_import_target(node, frozenset(names))
            if dynamic is not None:
                targets.add(dynamic)
    return frozenset(targets)


def _module_source(module_name: str) -> str:
    return _module_path(module_name).read_text(encoding="utf-8")


def _import_targets(module_name: str) -> frozenset[str]:
    path = _module_path(module_name)
    return _import_targets_of_tree(
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path)),
        module_name,
        is_package=path.name == "__init__.py",
    )


def _is_stdlib(target: str) -> bool:
    return target.split(".", 1)[0] in sys.stdlib_module_names


def _non_stdlib(targets: frozenset[str]) -> frozenset[str]:
    return frozenset(t for t in targets if not _is_stdlib(t))


def _import_set_mismatch(
    measured: frozenset[str], allowed: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """(measured but not allowed, allowed but no longer measured)."""
    return measured - allowed, allowed - measured


# --------------------------------------------------------------------------- #
# Layer 1: direct non-stdlib imports, equality-pinned
# --------------------------------------------------------------------------- #


class TestImportClosure:
    def test_every_module_imports_exactly_its_allowed_non_stdlib_targets(
        self,
    ) -> None:
        scanned = 0
        for module_name, allowed in _ALLOWED_IMPORT_TARGETS.items():
            scanned += 1
            extra, stale = _import_set_mismatch(
                _non_stdlib(_import_targets(module_name)), allowed
            )
            assert not extra and not stale, (
                f"{module_name}: unexpected {sorted(extra)}; "
                f"pinned but no longer imported {sorted(stale)}"
            )
        assert scanned >= 3, "the walk is looking at the wrong set"

    def test_the_package_init_imports_nothing_at_all(self) -> None:
        """Design: `fitdocs/publish/__init__.py` imports nothing, so importing
        a leaf loads no other fitdocs module -- standard library included."""
        assert _import_targets("fitdocs.publish") == frozenset()

    def test_request_reaches_outcomes_and_only_outcomes_inside_fitdocs(self) -> None:
        reached = {
            t for t in _import_targets("fitdocs.publish.request") if "fitdocs" in t
        }
        assert reached == {"fitdocs.publish.outcomes"}

    def test_positive_control_an_extra_import_and_a_stale_entry_are_reported(
        self,
    ) -> None:
        tree = ast.parse(
            "from fitdocs.publish.outcomes import PublishCode\n"
            "from fitdocs.render import views\n"
        )
        measured = _non_stdlib(_import_targets_of_tree(tree, "fitdocs.publish.request"))
        allowed = _ALLOWED_IMPORT_TARGETS["fitdocs.publish.request"]
        extra, stale = _import_set_mismatch(measured, allowed)
        assert extra, "the added render import was not reported"
        assert not stale
        # A stale entry: the module drops its only pinned import.
        tree = ast.parse("import os\n")
        extra, stale = _import_set_mismatch(
            _non_stdlib(_import_targets_of_tree(tree, "fitdocs.publish.request")),
            allowed,
        )
        assert not extra
        assert stale == {"fitdocs.publish.outcomes"}

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("import fitdocs.render\n", {"fitdocs.render"}),
            ("import fitdocs.render as r\n", {"fitdocs.render"}),
            ("from fitdocs import render\n", {"fitdocs.render"}),
            ("from fitdocs import __version__\n", {"fitdocs"}),
            ("import urllib.parse\n", {"urllib.parse", "urllib"}),
            ("import urllib.parse as up\n", {"urllib.parse"}),
            ("import os.path\n", {"os.path"}),
            ("from fitdocs import render as r\n", {"fitdocs.render"}),
            ("from fitdocs.render import views\n", {"fitdocs.render.views"}),
            ("from .. import render\n", {"fitdocs.render"}),
            ("from ..render import views\n", {"fitdocs.render.views"}),
            ("from . import outcomes\n", {"fitdocs.publish.outcomes"}),
            ("from .outcomes import PublishCode\n", {"fitdocs.publish.outcomes"}),
            ("from . import outcomes as o\n", {"fitdocs.publish.outcomes"}),
            (
                'import importlib\nimportlib.import_module("fitdocs.render")\n',
                {"importlib", "fitdocs.render"},
            ),
            (
                'from importlib import import_module as im\nim("x")\n',
                {"importlib", "x"},
            ),
            (
                'from importlib import import_module\nimport_module("socket")\n',
                {"importlib", "socket"},
            ),
            ('__import__("socket")\n', {"socket"}),
            ("import importlib\nimportlib.import_module(name)\n", {"importlib", "?"}),
        ],
    )
    def test_resolution_of_every_import_form(
        self, source: str, expected: set[str]
    ) -> None:
        targets = _import_targets_of_tree(ast.parse(source), "fitdocs.publish.request")
        assert targets == expected, source


# --------------------------------------------------------------------------- #
# Layer 2: forbidden names, independent of the registry
# --------------------------------------------------------------------------- #


def _forbidden_reason(target: str) -> str | None:
    """Why `target` may not be imported by any publish module, or None."""
    if target == "?":
        return "unresolvable dynamic import"
    for forbidden in _FORBIDDEN_FITDOCS:
        if target == forbidden or target.startswith(forbidden + "."):
            return f"forbidden fitdocs module {forbidden}"
    for forbidden in _FORBIDDEN_STDLIB:
        if target == forbidden or target.startswith(forbidden + "."):
            if any(target == a or target.startswith(a + ".") for a in _STDLIB_ADMITTED):
                return None
            return f"network-capable standard library {forbidden}"
    return None


def _third_party_violation(target: str, module_name: str) -> str | None:
    top = target.split(".", 1)[0]
    if _is_stdlib(target) or top == "fitdocs" or target == "?":
        return None
    if module_name in _THIRD_PARTY_ALLOWED_MODULES.get(top, frozenset()):
        return None
    return f"third-party {top} not admitted in {module_name}"


def _violations(targets: frozenset[str], module_name: str) -> list[str]:
    found: list[str] = []
    for target in sorted(targets):
        reason = _forbidden_reason(target) or _third_party_violation(
            target, module_name
        )
        if reason is not None:
            found.append(f"{module_name} imports {target!r}: {reason}")
    return found


def _tree_violations(source: str) -> list[str]:
    return _violations(
        _import_targets_of_tree(ast.parse(source), "fitdocs.publish.request"),
        "fitdocs.publish.request",
    )


class TestForbiddenNames:
    def test_no_publish_module_imports_a_forbidden_name(self) -> None:
        scanned = 0
        violations: list[str] = []
        for module_name in _ALLOWED_IMPORT_TARGETS:
            scanned += 1
            violations += _violations(_import_targets(module_name), module_name)
        assert scanned >= 3, "the walk is looking at the wrong set"
        assert not violations, "\n".join(violations)

    def test_urllib_parse_is_admitted_only_for_the_link_rule(self) -> None:
        """`request` really imports `urllib.parse` (so the carve-out is
        exercised, not idle) and the guard lets it through."""
        targets = _import_targets("fitdocs.publish.request")
        assert "urllib.parse" in targets
        assert _violations(frozenset({"urllib.parse"}), "fitdocs.publish.request") == []

    @pytest.mark.parametrize(
        "source",
        [
            # the render layer and siblings, in every import form
            "import fitdocs.render\n",
            "import fitdocs.render.views as v\n",
            "from fitdocs import render\n",
            "from fitdocs.render import views\n",
            "from .. import render\n",
            "from ..render import views\n",
            'import importlib\nimportlib.import_module("fitdocs.render")\n',
            '__import__("fitdocs.render")\n',
            "import importlib\nimportlib.import_module(name)\n",
            "from fitdocs import load\n",
            "from fitdocs import metrics\n",
            "from fitdocs import ingest\n",
            "from fitdocs import sync\n",
            "from fitdocs import index\n",
            "from fitdocs import query\n",
            "from fitdocs import dashboards\n",
            "from fitdocs import identity\n",
            "import fitdocs.identity.matcher\n",
            "from fitdocs import cli\n",
            "from fitdocs import tiles\n",
            # a socket and the rest of the network-capable standard library
            "import socket\n",
            "import socket as s\n",
            "from socket import create_connection\n",
            "import ssl\n",
            "import http.client\n",
            "from http import client\n",
            "from http.client import HTTPSConnection\n",
            "import ftplib\n",
            "import smtplib\n",
            "import poplib\n",
            "import imaplib\n",
            "import nntplib\n",
            "import telnetlib\n",
            "import xmlrpc.client\n",
            "import socketserver\n",
            "import asyncio\n",
            "import selectors\n",
            "import select\n",
            "import webbrowser\n",
            "import wsgiref.simple_server\n",
            '__import__("socket")\n',
            'import importlib\nimportlib.import_module("http.client")\n',
            # urllib: everything except `urllib.parse`
            "import urllib\n",
            "import urllib.request\n",
            "import urllib.request as ur\n",
            "import urllib.error\n",
            "from urllib import request\n",
            "from urllib import request as ur\n",
            "from urllib import error\n",
            "from urllib.request import urlopen\n",
            "from urllib.error import URLError\n",
            "from urllib import parse, request\n",
            'import importlib\nimportlib.import_module("urllib.request")\n',
            # `import urllib.parse` binds `urllib`: urllib.request is reachable
            "import urllib.parse\n",
            "import urllib.parse, os\n",
            # newly listed network-capable modules, every import form
            "import _socket\n",
            "import _socket as s\n",
            "from _socket import socket\n",
            "import _ssl\n",
            "from _ssl import SSLError\n",
            "import asyncore\n",
            "from asyncore import dispatcher\n",
            "import asynchat\n",
            "from asynchat import async_chat\n",
            "import smtpd\n",
            "from smtpd import SMTPServer\n",
            "import multiprocessing\n",
            "import multiprocessing.connection\n",
            "import multiprocessing.connection as mc\n",
            "from multiprocessing import connection\n",
            "from multiprocessing.connection import Client\n",
            'import importlib\nimportlib.import_module("multiprocessing.connection")\n',
            "import xml.sax\n",
            "from xml.sax import parse\n",
            "from xml import sax\n",
            "import xml.dom.pulldom\n",
            "from xml.dom import pulldom\n",
            "import xml.dom.xmlbuilder\n",
            "from xml.dom.xmlbuilder import DOMBuilder\n",
            "import logging.handlers\n",
            "import logging.handlers as lh\n",
            "from logging import handlers\n",
            "from logging import handlers as lh\n",
            "from logging.handlers import SocketHandler\n",
            'import importlib\nimportlib.import_module("logging.handlers")\n',
            # a third-party name no entry admits (HTTP clients and others)
            "import requests\n",
            "import httpx\n",
            "from tomli_w import dumps\n",
        ],
    )
    def test_positive_control_forbidden_form_is_caught(self, source: str) -> None:
        assert _tree_violations(source), source

    @pytest.mark.parametrize(
        "source",
        [
            "from urllib.parse import urlsplit\n",
            "import logging\n",
            "import xml.etree.ElementTree\n",
            "from xml.dom import minidom\n",
            "from xml.etree import ElementTree\n",
            "from logging import getLogger\n",
            "import logging as lg\n",
            "import urllib.parse as up\n",
            "from urllib import parse\n",
            "from urllib import parse as up\n",
            "import os\nimport pathlib\nimport datetime\n",
            "from fitdocs.publish.outcomes import PublishCode\n",
            "from .outcomes import PublishCode\n",
            "from . import outcomes\n",
            "from fitdocs import layout\n",
            'import importlib\nimportlib.import_module("urllib.parse")\n',
        ],
    )
    def test_negative_control_permitted_form_is_clean(self, source: str) -> None:
        assert _tree_violations(source) == [], source

    def test_positive_control_a_third_party_name_is_admitted_only_where_registered(
        self,
    ) -> None:
        """`tomli_w` is admitted in the registered module and flagged elsewhere
        and in the same module once its registration is removed."""
        assert _third_party_violation("tomli_w", "fitdocs.publish.ledger") is None
        assert _third_party_violation("tomli_w", "fitdocs.publish.request")
        original = dict(_THIRD_PARTY_ALLOWED_MODULES)
        try:
            _THIRD_PARTY_ALLOWED_MODULES.clear()
            assert _third_party_violation("tomli_w", "fitdocs.publish.ledger")
        finally:
            _THIRD_PARTY_ALLOWED_MODULES.clear()
            _THIRD_PARTY_ALLOWED_MODULES.update(original)

    def test_the_urllib_carve_out_is_one_entry_and_names_only_parse(self) -> None:
        assert _STDLIB_ADMITTED == ("urllib.parse",)


# --------------------------------------------------------------------------- #
# Layer 3: clock reads and randomness
# --------------------------------------------------------------------------- #

#: Clock spellings, matched against raw text so a docstring example is caught
#: too; `datetime.datetime.now` and `datetime.date.today` contain two of them.
_CLOCK_SPELLINGS: Final[tuple[str, ...]] = (
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "date.today",
    "time.time",
    "time.monotonic",
    "time.perf_counter",
    "time.process_time",
    "time.localtime",
    "time.gmtime",
    "time.ctime",
    "time.asctime",
    "time.clock_gettime",
)

#: Randomness spellings: the publication id is minted by the injected
#: `mint_id`, never inside the package.
_RANDOM_SPELLINGS: Final[tuple[str, ...]] = (
    "secrets.",
    "uuid.uuid",
    "uuid4",
    "uuid1",
    "uuid6",
    "uuid7",
    "uuid8",
    "os.urandom",
    "urandom",
    "SystemRandom",
    "getrandbits",
    "getrandom",
)
_RANDOM_PATTERN: Final = re.compile(r"\brandom\.\w")

#: Modules whose mere import is an offence (a randomness or clock source).
_FORBIDDEN_SOURCE_MODULES: Final[frozenset[str]] = frozenset(
    {"random", "_random", "secrets", "time"}
)


def _clock_and_random_offenders(source: str) -> list[str]:
    # A spelling must start at an identifier boundary: `datetime.timedelta`
    # contains the text `time.time` and is not a clock read.
    found = [
        s
        for s in (*_CLOCK_SPELLINGS, *_RANDOM_SPELLINGS)
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(s), source)
    ]
    if _RANDOM_PATTERN.search(source):
        found.append("random.<name>")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top = node.module.split(".", 1)[0]
            if top in _FORBIDDEN_SOURCE_MODULES:
                found.append(f"from {node.module} import ...")
            elif node.module == "datetime":
                # `from datetime import datetime as dt` hides `dt.now()` from
                # a spelling scan; an unaliased import is the module's own
                # name and is caught as `datetime.now` when it is called.
                found.extend(
                    f"datetime.{a.name} as {a.asname}"
                    for a in node.names
                    if a.asname and a.name in {"datetime", "date"}
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in _FORBIDDEN_SOURCE_MODULES:
                    found.append(f"import {alias.name}")
                elif alias.asname and alias.name == "datetime":
                    found.append(f"import datetime as {alias.asname}")
    return found


class TestClockAndRandomness:
    def test_no_publish_module_reads_a_clock_or_draws_randomness(self) -> None:
        paths = [_module_path(n) for n in _ALLOWED_IMPORT_TARGETS]
        assert len(paths) >= 3
        offenders = [
            f"{p.name}: {hit!r}"
            for p in paths
            for hit in _clock_and_random_offenders(p.read_text(encoding="utf-8"))
        ]
        assert not offenders, "\n".join(offenders)

    @pytest.mark.parametrize(
        "source",
        [
            "x = datetime.now()\n",
            "x = datetime.datetime.now()\n",
            "x = datetime.datetime.now(datetime.UTC)\n",
            "x = datetime.utcnow()\n",
            "x = datetime.today()\n",
            "x = date.today()\n",
            "x = datetime.date.today()\n",
            "x = time.time()\n",
            "x = time.time_ns()\n",
            "x = time.monotonic()\n",
            "x = time.perf_counter()\n",
            "x = time.process_time()\n",
            "x = time.localtime()\n",
            "x = time.gmtime()\n",
            "x = time.ctime()\n",
            "x = time.asctime()\n",
            "x = time.clock_gettime(0)\n",
            '"""e.g. datetime.now(UTC)"""\n',
            "# time.time() lives in the CLI\n",
            "from time import time\n",
            "from time import monotonic as m\n",
            "import time\n",
            "import time as t\n",
            "from datetime import datetime as dt\n",
            "from datetime import date as d\n",
            "import datetime as dtm\n",
            "x = secrets.token_hex(16)\n",
            "x = secrets.token_urlsafe()\n",
            "import secrets\n",
            "from secrets import token_hex\n",
            "x = uuid.uuid4()\n",
            "x = uuid.uuid1()\n",
            "from uuid import uuid6\n",
            "from uuid import uuid7\n",
            "from uuid import uuid8\n",
            "from uuid import uuid4\n",
            "x = random.random()\n",
            "x = random.choice(xs)\n",
            "import random\n",
            "import _random\n",
            "from _random import Random\n",
            "x = os.getrandom(16)\n",
            "from random import choice\n",
            "x = random.SystemRandom()\n",
            "x = os.urandom(8)\n",
            "from os import urandom\n",
            "x = r.getrandbits(32)\n",
        ],
    )
    def test_positive_control_each_form_is_detected(self, source: str) -> None:
        assert _clock_and_random_offenders(source), source

    @pytest.mark.parametrize(
        "source",
        [
            "from datetime import datetime\n"
            "def f(now):\n    return now() if now else None\n",
            "import datetime\nx = datetime.timedelta(days=1)\n",
            "from datetime import datetime, timedelta\n"
            "x = datetime.fromisoformat('2026-01-01T00:00:00+00:00')\n",
            "def f(mint_id):\n    return mint_id()\n",
            "x = 'a random value'\n",
            "x = value.uuid_text\n",
            "import uuid\nx = uuid.UUID(text)\n",
        ],
    )
    def test_negative_control_injected_clock_and_id_source_are_clean(
        self, source: str
    ) -> None:
        assert _clock_and_random_offenders(source) == [], source
