"""Build logic for the fitdocs website.

Modules in this package import only the Python standard library, PyYAML
(``yaml``, already a runtime dependency of fitdocs) and this package itself
(design: Allowed Dependencies). The pinned site generator, ``zensical``, is
invoked as a subprocess and never imported. The package never ships in a built
artifact: the sdist allowlist in ``pyproject.toml`` excludes ``scripts/``.
"""
