"""The packaged-skill registry and by-name locator (design: AgentSkillLocator).

fitdocs ships one or more "agent skills" -- self-contained markdown
directories an LLM agent copies into its own skills directory -- inside the
installed package under :data:`SKILLS_DIR`. This module is the *one*
mechanism every packaged skill is located through: a declared registry of
names (:data:`PACKAGED_SKILLS`), not a directory scan, so a skill can never
silently fall out of the wheel while a scan-based listing still looks
"correct". The CLI's ``skill`` command and every test that needs a skill's
installed location resolve it here.

Two skills are registered today: :data:`BLOCK_SKILL_NAME`
(``build-training-block``, an athlete-facing plan-authoring workflow) and
:data:`INBOX_SKILL_NAME` (``fitdocs-workouts``, the turnkey inbox-drain
workflow for an LLM-managed wiki, distribution task 4.2). Both live under
:data:`PACKAGED_SKILLS` in registration order; nothing about resolution
distinguishes one registered name from another.

Resolution goes through :func:`importlib.resources.files`, bound at module
level (rather than imported and called inline) so a test has exactly one
attribute to monkeypatch: ``fitdocs.agentskill.files``. Nothing happens at
import time -- every function below does its filesystem work when called, not
when this module is imported -- and a root is only ever *present* when it
resolves to a real directory holding :data:`SKILL_FILENAME`; any other case
(missing name, missing directory, missing file, or a zipped/import-time
resource that has no real filesystem path) resolves as absent (``None`` or
``()``), never an exception. A zipped install (for example a zipapp or an
egg whose resources are not extracted to disk) therefore degrades to "the
skill is absent" rather than raising -- callers that want to *fail* on an
incomplete installation (the CLI command) turn that absence into their own
error path.

This module imports nothing from :mod:`fitdocs`: it is a pure leaf, holds no
package-wide state, and is not part of :data:`fitdocs.__all__`.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Final

SKILLS_DIR: Final[str] = "skills"
SKILL_FILENAME: Final[str] = "SKILL.md"
BLOCK_SKILL_NAME: Final[str] = "build-training-block"
INBOX_SKILL_NAME: Final[str] = "fitdocs-workouts"
PACKAGED_SKILLS: Final[tuple[str, ...]] = (BLOCK_SKILL_NAME, INBOX_SKILL_NAME)


def _resolved_directory(name: str) -> Path | None:
    """Return the filesystem directory for ``name``'s package resource, or ``None``.

    Converts the :class:`importlib.resources.abc.Traversable` returned by
    ``files()`` to a :class:`~pathlib.Path` via ``str()`` -- the documented way
    to obtain a filesystem path for an unzipped install, which every supported
    fitdocs install is -- and guards that the result both exists and is a
    directory before returning it.
    """
    traversable = files("fitdocs") / SKILLS_DIR / name
    candidate = Path(str(traversable))
    if not candidate.is_dir():
        return None
    return candidate


def skill_root(name: str) -> Path | None:
    """The installed directory for the packaged skill ``name``, or ``None``.

    Present iff ``name`` resolves to a real directory that itself holds
    :data:`SKILL_FILENAME`. Never raises: an unregistered name, a packaging
    defect that dropped the directory or the file, or a zipped import all
    resolve as absent.
    """
    directory = _resolved_directory(name)
    if directory is None:
        return None
    if not (directory / SKILL_FILENAME).is_file():
        return None
    return directory


def skill_file(name: str) -> Path | None:
    """``skill_root(name) / SKILL_FILENAME``, or ``None`` when the root is absent."""
    root = skill_root(name)
    if root is None:
        return None
    return root / SKILL_FILENAME


def skill_files(name: str) -> tuple[Path, ...]:
    """Every regular file under ``name``'s root, sorted by relative POSIX path.

    ``()`` when the root is absent. This is the one source of truth for "the
    skill's files": the wheel-membership test and the installation copy
    recipe both read it.
    """
    root = skill_root(name)
    if root is None:
        return ()
    return tuple(
        sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )
