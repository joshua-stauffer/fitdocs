"""The closed publish vocabulary (publish-core Req 1.1-1.5)."""

from __future__ import annotations

import ast
import dataclasses
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

from fitdocs.publish import outcomes
from fitdocs.publish.outcomes import (
    FAILURE_CODES,
    LANDED_CODES,
    OUTCOMES,
    STATE_CODES,
    STOPPING_CODES,
    TARGET_CODES,
    CodeInfo,
    PublishCode,
    explanation,
)

C = PublishCode

# Landed literals, in the design's order. A prefix pin: appending is free.
PINNED_VALUES = [
    "would_post",
    "would_update",
    "unchanged",
    "not_opted_in",
    "opt_in_invalid",
    "unknown_target",
    "page_out_of_date",
    "page_newer",
    "page_damaged",
    "page_unreadable",
    "post_invalid",
    "template_invalid",
    "value_missing",
    "title_empty",
    "activity_facts_missing",
    "ledger_conflict",
    "posted",
    "uploaded",
    "not_found",
    "ambiguous",
    "not_updatable",
    "activity_file_missing",
    "not_connected",
    "credentials_unreadable",
    "auth_rejected",
    "permission_denied",
    "rate_limited",
    "unavailable",
    "rejected",
    "unconfirmed",
    "target_error",
    "not_attempted",
    "published_not_written",
    "ready",
    "local_record_unreadable",
]

PINNED_EXPLANATIONS = (
    "This page has no post on this target yet, and `fitdocs publish --yes` would post it.",  # noqa: E501
    "This page's post changed since it last landed on this target, and `fitdocs publish --yes` would update it.",  # noqa: E501
    "This target already carries this page's current post, so nothing is sent.",
    "This page's publish key does not name this target, so nothing is sent.",
    "This page's publish key is neither a target name nor a list of distinct target names, so nothing is sent from it.",  # noqa: E501
    "This page's publish key names something that is not a configured publish target, so nothing is sent to it.",  # noqa: E501
    "This page was written by an older fitdocs; run `fitdocs regen` before publishing it.",  # noqa: E501
    "This page was written by a newer fitdocs, so this installation does not publish it.",  # noqa: E501
    "This page's region markers are damaged or missing; restore them by hand before publishing it.",  # noqa: E501
    "This page could not be read as a workout page, so nothing is sent from it.",
    "This page's post region is not a title line, a blank line and a description, so nothing is sent from it.",  # noqa: E501
    "This page's post region has a template error, so nothing is sent from it.",
    "A placeholder outside an optional clause has no value on this page, so nothing is sent.",  # noqa: E501
    "The composed title is empty, so nothing is sent.",
    "The facts that identify this page's activity are missing, so nothing is sent.",
    "The publish ledger holds more than one record for this page, or one record matches several pages, or a new record's key would match several pages, so nothing is sent.",  # noqa: E501
    "The target's activity now carries this page's title and description.",
    "No matching activity existed, so the target created one from this page's activity file with its title and description.",  # noqa: E501
    "The target has no activity matching this page and uploading is not enabled for it, so nothing was changed.",  # noqa: E501
    "More than one activity on the target matches this page, so nothing was changed.",
    "The matching activity cannot be changed through this target, so nothing was changed.",  # noqa: E501
    "Uploading needs this page's activity file, which is not in the archive, so nothing was changed.",  # noqa: E501
    "This target has no usable credentials; run `fitdocs connect` for it.",
    "This target's stored credentials could not be read or are not private to you; fix the file or connect it again.",  # noqa: E501
    "The target refused the stored credentials; connect it again.",
    "The credentials do not allow this change; connect again and grant the permission it needs.",  # noqa: E501
    "The target's rate limit was reached, so nothing more is sent to it in this run; try again later.",  # noqa: E501
    "The target could not be reached or failed on its side, so nothing more is sent to it in this run; try again later.",  # noqa: E501
    "The target refused the request as invalid, so nothing was changed.",
    "The request was sent but its result is unknown; the next run checks the target before sending again.",  # noqa: E501
    "The target failed unexpectedly, which is a fitdocs defect, and nothing more was sent for this page.",  # noqa: E501
    "Nothing was sent, because an earlier result in this run stopped publishing to this target.",  # noqa: E501
    "The outcomes were recorded, but this page's published region could not be rewritten; the next `fitdocs publish --yes` rewrites it.",  # noqa: E501
    "This target is configured and has the credentials it needs.",
    "This target could not read its own local record of this connection's activities, so it could not rule out that the activity already exists and uploaded nothing.",  # noqa: E501
)

PINNED_LANDED = frozenset({C.POSTED, C.UPLOADED})
PINNED_FAILURE = frozenset(
    {
        C.OPT_IN_INVALID,
        C.UNKNOWN_TARGET,
        C.PAGE_OUT_OF_DATE,
        C.PAGE_NEWER,
        C.PAGE_DAMAGED,
        C.PAGE_UNREADABLE,
        C.POST_INVALID,
        C.TEMPLATE_INVALID,
        C.VALUE_MISSING,
        C.TITLE_EMPTY,
        C.ACTIVITY_FACTS_MISSING,
        C.LEDGER_CONFLICT,
        C.NOT_FOUND,
        C.AMBIGUOUS,
        C.NOT_UPDATABLE,
        C.ACTIVITY_FILE_MISSING,
        C.NOT_CONNECTED,
        C.CREDENTIALS_UNREADABLE,
        C.AUTH_REJECTED,
        C.PERMISSION_DENIED,
        C.RATE_LIMITED,
        C.UNAVAILABLE,
        C.REJECTED,
        C.UNCONFIRMED,
        C.TARGET_ERROR,
        C.NOT_ATTEMPTED,
        C.PUBLISHED_NOT_WRITTEN,
        C.LOCAL_RECORD_UNREADABLE,
    }
)
PINNED_TARGET = frozenset(
    {
        C.ACTIVITY_FACTS_MISSING,
        C.POSTED,
        C.UPLOADED,
        C.NOT_FOUND,
        C.AMBIGUOUS,
        C.NOT_UPDATABLE,
        C.ACTIVITY_FILE_MISSING,
        C.NOT_CONNECTED,
        C.AUTH_REJECTED,
        C.PERMISSION_DENIED,
        C.RATE_LIMITED,
        C.UNAVAILABLE,
        C.REJECTED,
        C.UNCONFIRMED,
        C.LOCAL_RECORD_UNREADABLE,
    }
)
PINNED_STOPPING = frozenset(
    {
        C.NOT_CONNECTED,
        C.CREDENTIALS_UNREADABLE,
        C.AUTH_REJECTED,
        C.PERMISSION_DENIED,
        C.RATE_LIMITED,
        C.UNAVAILABLE,
    }
)
PINNED_STATE = frozenset({C.NOT_CONNECTED, C.CREDENTIALS_UNREADABLE, C.READY})

# Codes a target must never return: 1-14, 16, 24, 31-34 of the design table.
NOT_FROM_TARGET = frozenset(
    {
        C.WOULD_POST,
        C.WOULD_UPDATE,
        C.UNCHANGED,
        C.NOT_OPTED_IN,
        C.OPT_IN_INVALID,
        C.UNKNOWN_TARGET,
        C.PAGE_OUT_OF_DATE,
        C.PAGE_NEWER,
        C.PAGE_DAMAGED,
        C.PAGE_UNREADABLE,
        C.POST_INVALID,
        C.TEMPLATE_INVALID,
        C.VALUE_MISSING,
        C.TITLE_EMPTY,
        C.LEDGER_CONFLICT,
        C.CREDENTIALS_UNREADABLE,
        C.TARGET_ERROR,
        C.NOT_ATTEMPTED,
        C.PUBLISHED_NOT_WRITTEN,
        C.READY,
    }
)


def test_values_are_the_pinned_prefix_in_order() -> None:
    values = [m.value for m in PublishCode]
    assert len(PINNED_VALUES) == 35
    assert values[: len(PINNED_VALUES)] == PINNED_VALUES


def test_every_member_has_exactly_one_outcome_entry() -> None:
    assert set(OUTCOMES) == set(PublishCode)
    for code, info in OUTCOMES.items():
        assert isinstance(info, CodeInfo)
        assert info.code is code


def test_flag_sets_are_the_pinned_literals() -> None:
    assert LANDED_CODES == PINNED_LANDED
    assert FAILURE_CODES == PINNED_FAILURE
    assert TARGET_CODES == PINNED_TARGET
    assert STOPPING_CODES == PINNED_STOPPING
    assert STATE_CODES == PINNED_STATE


def test_flag_sets_derive_from_the_per_code_flags() -> None:
    for code, info in OUTCOMES.items():
        assert (code in LANDED_CODES) is info.landed
        assert (code in FAILURE_CODES) is info.failure
        assert (code in TARGET_CODES) is info.from_target
        assert (code in STOPPING_CODES) is info.stops_target
        assert (code in STATE_CODES) is info.target_state


def test_local_record_unreadable_fails_and_comes_from_a_target() -> None:
    info = OUTCOMES[C.LOCAL_RECORD_UNREADABLE]
    assert (info.landed, info.failure, info.from_target) == (False, True, True)
    assert (info.stops_target, info.target_state) == (False, False)


def test_target_codes_exclude_offline_core_assigned_and_listing_only_codes() -> None:
    assert NOT_FROM_TARGET and not (TARGET_CODES & NOT_FROM_TARGET)
    assert C.LOCAL_RECORD_UNREADABLE in TARGET_CODES
    assert set(list(PublishCode)[:35]) == TARGET_CODES | NOT_FROM_TARGET


@pytest.mark.parametrize("code", list(PublishCode))
def test_explanation_is_one_fixed_sentence(code: PublishCode) -> None:
    text = explanation(code)
    assert text == OUTCOMES[code].explanation
    assert text.endswith(".")
    assert text.count(".") == 1
    assert "{" not in text and "}" not in text
    assert "\n" not in text


def test_explanations_are_distinct() -> None:
    texts = [explanation(c) for c in PublishCode]
    assert len(set(texts)) == len(texts)


def _module_path() -> Path:
    assert outcomes.__file__ is not None
    return Path(outcomes.__file__)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            assert node.module is not None
            roots.add(node.module.split(".")[0])
    return roots


def test_module_and_marker_import_only_the_standard_library() -> None:
    marker = _module_path().parent / "__init__.py"
    for path in (_module_path(), marker):
        roots = _imported_roots(path)
        assert roots <= set(sys.stdlib_module_names), (path.name, roots)
    assert _imported_roots(_module_path()), "the walk found no imports at all"


def test_fresh_interpreter_loads_no_other_fitdocs_module() -> None:
    code = (
        "import sys\n"
        "import fitdocs.publish.outcomes\n"
        "print(sorted(m for m in sys.modules\n"
        "             if m == 'fitdocs' or m.startswith('fitdocs.')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = ast.literal_eval(result.stdout.strip())
    assert loaded == ["fitdocs", "fitdocs.publish", "fitdocs.publish.outcomes"]


def test_explanations_are_the_pinned_literals_in_order() -> None:
    assert len(PINNED_EXPLANATIONS) == 35
    assert [explanation(c) for c in PublishCode][:35] == list(PINNED_EXPLANATIONS)


def test_outcomes_is_read_only() -> None:
    assert isinstance(OUTCOMES, MappingProxyType)
    with pytest.raises(TypeError):
        OUTCOMES[C.READY] = OUTCOMES[C.POSTED]  # type: ignore[index]


def test_code_info_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        OUTCOMES[C.READY].landed = True  # type: ignore[misc]


def test_marker_imports_nothing() -> None:
    marker = _module_path().parent / "__init__.py"
    tree = ast.parse(marker.read_text(encoding="utf-8"))
    assert len(tree.body) == 1
    node = tree.body[0]
    assert isinstance(node, ast.Expr)
    assert isinstance(node.value, ast.Constant)
    assert isinstance(node.value.value, str)
    assert _imported_roots(marker) == set()
