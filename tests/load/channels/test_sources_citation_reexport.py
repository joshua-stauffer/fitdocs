"""Task 8.2: ``fitdocs.load.channels.sources`` re-points its citation types to
the shared ``fitdocs.citation`` vocabulary instead of declaring its own.

Covers Requirement 16.1 -- see ``.kiro/specs/fit-ingest/requirements.md`` and
the "CitationVocabulary (`src/fitdocs/citation.py`)" component and "Modified
Files" table in design.md. This module is deliberately separate from
``tests/load/channels/test_sources.py``, which stays unedited by this task
(design.md: unedited passing is itself the evidence the re-export is
behavior-preserving) and from ``tests/test_citation.py``, which is
load-channels-agnostic.
"""

from __future__ import annotations

import ast
import pathlib

import fitdocs.citation as citation_module
import fitdocs.load.channels.sources as sources_module


def _class_def_names(module: object, class_name: str) -> list[pathlib.Path]:
    """Every ``.py`` file under ``src/fitdocs`` that contains a top-level
    ``class <class_name>`` *definition* (not a reference or an import)."""
    src_root = pathlib.Path(citation_module.__file__).resolve().parent
    assert src_root.name == "fitdocs" and src_root.exists(), src_root
    hits: list[pathlib.Path] = []
    files = list(src_root.rglob("*.py"))
    assert files, "the walk over src/fitdocs found no source files"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                hits.append(path)
    return hits


def test_exactly_one_verificationstatus_definition_exists_in_the_tree() -> None:
    """The observable literal to task 8.2: exactly one ``class
    VerificationStatus`` definition exists anywhere under ``src/fitdocs``,
    not merely that ``sources.py`` no longer has one."""
    hits = _class_def_names(sources_module, "VerificationStatus")
    assert hits == [pathlib.Path(citation_module.__file__).resolve()], hits


def test_exactly_one_citation_definition_exists_in_the_tree() -> None:
    """Same shape for ``Citation``: the load-channels module must import it,
    not redeclare it."""
    hits = _class_def_names(sources_module, "Citation")
    assert hits == [pathlib.Path(citation_module.__file__).resolve()], hits


def test_sources_verificationstatus_is_the_shared_object_not_a_copy() -> None:
    """A re-export binds the same class object; a parallel, separately
    declared enum with identical members would satisfy the two tests above
    only if this test were absent (two ``class VerificationStatus`` bodies
    with the same members are still two definitions by identity, even though
    a naive single-definition check by name across modules could miss it if
    it only checked value-set equality instead of object identity)."""
    assert sources_module.VerificationStatus is citation_module.VerificationStatus
    assert sources_module.Citation is citation_module.Citation


def test_sources_module_declares_no_verificationstatus_or_citation_class() -> None:
    """Direct, sources.py-local check: no ``class VerificationStatus`` or
    ``class Citation`` statement appears in ``sources.py`` itself. Narrower
    than the tree-wide walk above -- this pins the specific file the task
    names."""
    source_path = pathlib.Path(sources_module.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    assert "VerificationStatus" not in class_names
    assert "Citation" not in class_names
    # Divergence stays local to this module -- it is load-channels' own type
    # and is not part of this task's move.
    assert "Divergence" in class_names
