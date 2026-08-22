# Vendored baseline for
# tests/test_cli_drain_report.py::test_report_function_is_left_byte_untouched.
#
# Provenance: this is the ``_report`` function exactly as it existed in
# ``src/fitdocs/cli.py`` at commit faa6d09 -- the last commit that touched
# ``cli.py`` *before* the task that added ``_report_drain`` (inbox Req 2.3,
# 7.1, 7.3). It was extracted with:
#
#     git show faa6d09:src/fitdocs/cli.py
#
# and then narrowed to just the ``_report`` FunctionDef.
#
# It is vendored here -- rather than fetched from git history at test time --
# because a depth-limited clone (e.g. GitHub Actions' default
# ``actions/checkout`` at ``fetch-depth: 1``, or any shallow/partial clone)
# does not carry the ``faa6d09`` object, and a test that shells out to
# ``git show`` for it fails with a missing-object error instead of reporting
# the drift it exists to catch. Vendoring this source makes the test's
# baseline independent of what history happens to be present in the checkout.
#
# This module is parsed by the test for its ``_report`` FunctionDef's AST
# only; it is never imported or executed by that test. The real imports below
# exist solely so this file satisfies ruff/mypy when they lint `tests/` --
# they play no role in the baseline comparison, which only ever looks inside
# the FunctionDef node.
#
# Do not "clean up" or reformat the ``_report`` function below -- any edit
# there changes what the test considers the pre-task baseline. If ``_report``
# is intentionally changed by a future task, this fixture must be re-vendored
# from the new pre-task commit, not hand-edited to match.
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from fitdocs.sync import SyncReport


def _report(report: SyncReport, *, command: str) -> None:
    """Print the end-of-run summary: a counts table plus the per-file detail (1.4).

    The rich table carries the written / skipped / failed / warnings counts; the
    written documents, every failure (its source and reason), and every
    :class:`~fitdocs.sync.DocWarning` (the document it names and its detail) are
    listed beneath it -- see :attr:`~fitdocs.sync.SyncReport.warnings` for the
    causes that can appear there rather than re-enumerating them here, since that
    list grows independently of this presentation layer. Warnings are a separate,
    additive channel: they are reported but never alter the exit code (Req 4.4).
    Detail lines are printed with
    ``soft_wrap`` so long paths and reasons are never truncated, and with markup
    disabled so bracketed reason text is shown verbatim.
    """
    console = Console()
    table = Table(title=f"fitdocs {command}")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Written", str(len(report.written)))
    table.add_row("Skipped", str(len(report.skipped)))
    table.add_row("Failed", str(len(report.failures)))
    table.add_row("Warnings", str(len(report.warnings)))
    console.print(table)

    if report.written:
        console.print("Written:")
        for ref in report.written:
            console.print(f"  {ref}", markup=False, highlight=False, soft_wrap=True)
    if report.failures:
        console.print("Failed:")
        for failure in report.failures:
            console.print(
                f"  {failure.source}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {failure.reason}", markup=False, highlight=False, soft_wrap=True
            )
    if report.warnings:
        console.print("Warnings:")
        for warning in report.warnings:
            console.print(
                f"  {warning.doc}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {warning.detail}", markup=False, highlight=False, soft_wrap=True
            )
