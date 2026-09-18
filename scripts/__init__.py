"""Makes `python -m scripts.<name>` resolvable from the repository root.

This package exists for that reason and nothing else (design: File Structure
Plan, `scripts/`). It never ships in a built artifact -- the sdist allowlist
in `pyproject.toml` and `release/artifact-policy.toml`'s `[forbidden]` table
both exclude `scripts/*` -- and it is never imported by `src/fitdocs`.
"""
