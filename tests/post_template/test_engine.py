"""Fill one page (post-templates task 3.1).

Requirements 3.3, 3.10, 4.1 to 4.6, 5.6 to 5.9, 6.5, 10.4, 10.9 and 10.11. The
engine runs over a FAKE resolver that records every call, so the order of the
calls, their arguments and the absence of calls are all observable. Pages are
built by hand with CRLF line ends and distinctive bytes around the `post`
region; the expected file is spliced by plain byte arithmetic, not by the
production splice.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.docmerge import region_block
from fitdocs.post_template import engine
from fitdocs.post_template.engine import PageRead, _fill_page, read_for_fill
from fitdocs.post_template.model import (
    Binding,
    FillCode,
    PageResult,
    RegionState,
    VariableOutcome,
)
from fitdocs.post_template.region import render_filled
from fitdocs.post_template.template import PostTemplate, Variable, parse_post_template
from fitdocs.publish.ledger import (
    PublicationRecord,
    PublishLedger,
    workout_page_key,
)
from fitdocs.publish.pages import SelectedPage
from fitdocs.publish.request import Post

_Make = Callable[[str], Path]

_KEY_A = hashlib.sha256(b"older source").hexdigest()
_KEY_B = hashlib.sha256(b"base source").hexdigest()
_OTHER = hashlib.sha256(b"someone else").hexdigest()
_START = "2021-09-08T06:05:00+02:00"
_AS_OF = datetime(2021, 9, 8, 6, 5, 0)  # the wall clock, not UTC
_REL = "workouts/2021-09-08-0605-run.md"
_SINCE = date(2021, 9, 8)

_BEGIN = b"<!-- fitdocs:begin:post -->\n"
_END = b"\n<!-- fitdocs:end:post -->"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _page_text(
    *,
    version: int | None = contract.DOC_VERSION,
    start: str | None = _START,
    title: str = "Run",
    day: str | None = "2021-09-08",
    sources: tuple[str, ...] = (_KEY_A, _KEY_B),
    post: str = contract.POST_PLACEHOLDER,
    post_region: bool = True,
    close_post: bool = True,
    notes: str = "kept\r\nnotes\r\n",
    raw_last_ref: str | None = None,
) -> str:
    """A page with LF markers and CRLF prose, non-ASCII text and a trailer."""
    lines = ["---", f"title: {json.dumps(title)}"]
    lines += [f"type: {contract.WORKOUT_TYPE}", "generator: fitdocs"]
    if version is not None:
        lines.append(f"doc_version: {version}")
    if day is not None:
        lines.append(f"date: {day}")
    if start is not None:
        lines.append(f"start_time: '{start}'")
    lines += ["sport: Run", "modality: run"]
    refs = ", ".join(f"fit-archive/{sha}.fit" for sha in sources)
    if raw_last_ref is not None:
        refs += f", {raw_last_ref}"
    lines.append(f"sources: [{refs}]")
    lines += ["load_value: 35.0", "load_methodology: threshold", "load_basis: pace"]
    lines += ["---", ""]
    text = "\n".join(lines) + "\n"
    text += "# Run\r\n\r\nPrologue é — ünïcode\r\n\r\n"
    text += region_block("notes", notes)
    text += "\r\n" + region_block("load", contract.LOAD_NOT_COMPUTED) + "\r\n"
    if post_region:
        block = region_block("post", post)
        if not close_post:
            block = block.replace("<!-- fitdocs:end:post -->\n", "")
        text += block
    text += "\r\n" + region_block("published", "")
    text += "\r\ntrailer é\r\nlast line, no newline"
    return text


@dataclass
class Case:
    root: Path
    selected: SelectedPage

    def write(self, text: str) -> bytes:
        data = text.encode("utf-8")
        self.selected.path.write_bytes(data)
        return data

    def bytes(self) -> bytes:
        return self.selected.path.read_bytes()


@pytest.fixture
def case(per_test_directory: _Make) -> Case:
    root = per_test_directory("engine")
    (root / "workouts").mkdir()
    selected = SelectedPage(root / _REL, _REL, named=False)
    return Case(root, selected)


def _template(
    title: str = "{zulu} {alpha} {mike} {sport}",
    description: str = "",
    names: tuple[str, ...] = ("alpha", "mike", "zulu"),
) -> PostTemplate:
    text = f"since = 2021-09-01\ntitle = {json.dumps(title)}\n"
    if description:
        text += f"description = {json.dumps(description)}\n"
    for name in names:
        text += f'\n[vars.{name}]\nsql = "SELECT 1 -- {name}"\n'
    return parse_post_template(text.encode(), path=Path("/data/post-template.toml"))


def _ok(name: str, value: str | None) -> VariableOutcome:
    return VariableOutcome(name, value, None, None)


def _failed(name: str, code: FillCode, detail: str) -> VariableOutcome:
    return VariableOutcome(name, None, code, detail)


_DEFAULTS = {"alpha": "A", "mike": "M", "zulu": "Z"}


class FakeResolver:
    """Records every call; answers from `outcomes`, else the default value."""

    def __init__(
        self,
        outcomes: dict[str, VariableOutcome] | None = None,
        *,
        current: bool = True,
        on_resolve: Callable[[str], None] | None = None,
    ) -> None:
        self.outcomes = outcomes or {}
        self.current = current
        self.on_resolve = on_resolve
        self.calls: list[tuple[object, ...]] = []

    def check(self, template: PostTemplate) -> tuple[str, ...]:
        raise AssertionError("_fill_page must not check the template")

    def page_is_current(self, page_key: str | None, path: str, data: bytes) -> bool:
        self.calls.append(("current", page_key, path, data))
        return self.current

    def resolve(
        self, variable: Variable, binding: Binding, *, timeout_s: float
    ) -> VariableOutcome:
        self.calls.append(("resolve", variable, binding, timeout_s))
        if self.on_resolve is not None:
            self.on_resolve(variable.name)
        return self.outcomes.get(variable.name) or _ok(
            variable.name, _DEFAULTS[variable.name]
        )

    def close(self) -> None:
        raise AssertionError("_fill_page must not close the resolver")

    def resolved(self) -> list[str]:
        return [c[1].name for c in self.calls if c[0] == "resolve"]  # type: ignore[attr-defined]


def _read(case: Case, ledgers: tuple[PublishLedger, ...] = ()) -> PageRead:
    read = read_for_fill(case.selected, since=_SINCE, ledgers=ledgers)
    assert isinstance(read, PageRead), read
    return read


def _run(
    case: Case,
    template: PostTemplate,
    resolver: FakeResolver,
    *,
    writing: bool = True,
    timeout_s: float = 7.5,
    ledgers: tuple[PublishLedger, ...] = (),
) -> PageResult:
    return _fill_page(
        _read(case, ledgers), template, resolver, writing=writing, timeout_s=timeout_s
    )


def _splice(original: bytes, content: str) -> bytes:
    """`original` with only the post region's inner content replaced."""
    start = original.index(_BEGIN) + len(_BEGIN)
    stop = original.index(_END, start)
    return original[:start] + content.encode("utf-8") + original[stop:]


def _filled(template: PostTemplate, title: str, description: str = "") -> str:
    return render_filled(
        Post(title, description), template_digest=template.digest, as_of=_AS_OF
    )


# --------------------------------------------------------------------------- #
# A fill
# --------------------------------------------------------------------------- #


class TestFill:
    def test_a_waiting_page_is_filled_and_only_the_region_changes(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())
        template = _template()
        result = _run(case, template, FakeResolver())
        content = _filled(template, "Z A M Run")
        assert result == PageResult(
            page=_REL,
            state=RegionState.WAITING,
            in_window=True,
            landed=False,
            code=FillCode.FILLED,
            detail=None,
            variables=tuple(_ok(n, _DEFAULTS[n]) for n in ("alpha", "mike", "zulu")),
            post=Post("Z A M Run", ""),
            changed=True,
        )
        assert case.bytes() == _splice(original, content)
        # The surrounding bytes are the CRLF prose, the non-ASCII text and the
        # unterminated trailer, all untouched.
        assert case.bytes().startswith(original[: original.index(_BEGIN)])
        assert case.bytes().endswith(b"\r\ntrailer \xc3\xa9\r\nlast line, no newline")
        assert b"\r\n" in case.bytes()

    def test_the_region_records_the_template_digest_and_the_local_start(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        template = _template()
        _run(case, template, FakeResolver())
        text = case.bytes().decode()
        assert f"template={template.digest} as_of=2021-09-08T06:05:00 text=" in text
        assert "+02:00 -->" not in text

    def test_page_values_and_variable_values_both_compose(self, case: Case) -> None:
        case.write(_page_text(title="Morning"))
        template = _template(title="{title} {zulu}", names=("zulu",))
        result = _run(case, template, FakeResolver())
        assert result.post == Post("Morning Z", "")

    def test_a_multi_line_description_is_written_as_composed(self, case: Case) -> None:
        original = case.write(_page_text())
        template = _template(
            title="{alpha}", description="  line one {mike}\n\n  line two {zulu}  \n\n"
        )
        result = _run(case, template, FakeResolver())
        post = Post("A", "  line one M\n\n  line two Z")
        assert result.post == post
        assert case.bytes() == _splice(
            original, _filled(template, "A", post.description)
        )

    def test_braces_in_values_are_written_escaped_and_composed_literally(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())
        template = _template(title="{alpha}", names=("alpha",))
        result = _run(case, template, FakeResolver({"alpha": _ok("alpha", "{x} }{")}))
        assert result.post == Post("{x} }{", "")
        assert case.bytes() == _splice(original, _filled(template, "{x} }{"))
        assert b"{{x}} }}{{" in case.bytes()

    def test_an_optional_clause_with_an_absent_value_is_dropped(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        template = _template(title="{zulu}{? and {alpha}}{? / {mike}}")
        result = _run(case, template, FakeResolver({"alpha": _ok("alpha", None)}))
        assert result.code is FillCode.FILLED
        assert result.post == Post("Z / M", "")
        assert result.variables[0] == _ok("alpha", None)

    def test_a_dry_run_composes_and_writes_nothing(self, case: Case) -> None:
        original = case.write(_page_text())
        template = _template()
        resolver = FakeResolver()
        result = _run(case, template, resolver, writing=False)
        assert result.code is FillCode.WOULD_FILL
        assert result.post == Post("Z A M Run", "")
        assert result.changed is True
        assert case.bytes() == original

    def test_a_dry_run_does_not_reread_the_file(self, case: Case) -> None:
        """An edit made during a dry run is no conflict: nothing is written."""
        original = case.write(_page_text())

        def edit(_name: str) -> None:
            case.selected.path.write_bytes(original + b"edit")

        result = _run(case, _template(), FakeResolver(on_resolve=edit), writing=False)
        assert result.code is FillCode.WOULD_FILL

    def test_the_write_goes_through_the_atomic_helper(
        self, case: Case, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = case.write(_page_text())
        template = _template()
        seen: list[tuple[Path, bytes]] = []
        real = engine.write_bytes_if_changed

        def spy(path: Path, data: bytes) -> bool:
            seen.append((path, data))
            return real(path, data)

        monkeypatch.setattr(engine, "write_bytes_if_changed", spy)
        _run(case, template, FakeResolver())
        assert seen == [
            (case.selected.path, _splice(original, _filled(template, "Z A M Run")))
        ]


# --------------------------------------------------------------------------- #
# Reading the variables: order, binding, stopping
# --------------------------------------------------------------------------- #


class TestResolving:
    def test_variables_resolve_in_name_order_whatever_the_declaration_order(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        template = _template()
        declared = replace(
            template,
            variables=tuple(
                sorted(template.variables, key=lambda v: v.name, reverse=True)
            ),
        )
        assert [v.name for v in declared.variables] == ["zulu", "mike", "alpha"]
        resolver = FakeResolver()
        result = _run(case, declared, resolver)
        assert resolver.resolved() == ["alpha", "mike", "zulu"]
        assert [v.name for v in result.variables] == ["alpha", "mike", "zulu"]

    def test_each_variable_gets_its_own_definition_the_binding_and_the_timeout(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        template = _template()
        resolver = FakeResolver()
        _run(case, template, resolver, timeout_s=3.25)
        resolves = [c for c in resolver.calls if c[0] == "resolve"]
        by_name = {v.name: v for v in template.variables}
        assert [c[1] for c in resolves] == [
            by_name[n] for n in ("alpha", "mike", "zulu")
        ]
        assert {c[2] for c in resolves} == {Binding(_AS_OF, _KEY_B)}
        assert [c[3] for c in resolves] == [3.25, 3.25, 3.25]

    def test_the_binding_is_the_wall_clock_start_and_the_last_source(
        self, case: Case
    ) -> None:
        """Two sources and a +05:30 offset: UTC or the first source would differ."""
        case.write(_page_text(start="2021-09-08T23:45:30+05:30"))
        resolver = FakeResolver()
        _run(case, _template(), resolver, writing=False)
        binding = next(c[2] for c in resolver.calls if c[0] == "resolve")
        assert binding == Binding(datetime(2021, 9, 8, 23, 45, 30), _KEY_B)
        assert binding.as_of.tzinfo is None

    def test_a_page_without_sources_binds_no_key_and_is_not_current(
        self, case: Case
    ) -> None:
        original = case.write(_page_text(sources=()))
        resolver = FakeResolver(current=False)
        result = _run(case, _template(), resolver)
        assert resolver.calls == [("current", None, _REL, original)]
        assert result.code is FillCode.INDEX_BEHIND

    def test_the_first_failure_stops_the_page(self, case: Case) -> None:
        original = case.write(_page_text())
        failure = _failed("mike", FillCode.STATEMENT_FAILED, "no such column")
        resolver = FakeResolver({"mike": failure})
        result = _run(case, _template(), resolver)
        assert resolver.resolved() == ["alpha", "mike"]
        assert result.code is FillCode.STATEMENT_FAILED
        assert result.detail == "no such column"
        assert result.variables == (_ok("alpha", "A"), failure)
        assert result.post is None
        assert result.changed is None
        assert case.bytes() == original

    def test_a_failure_of_the_first_variable_resolves_no_other(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        resolver = FakeResolver(
            {"alpha": _failed("alpha", FillCode.SHAPE_INVALID, "x")}
        )
        result = _run(case, _template(), resolver)
        assert resolver.resolved() == ["alpha"]
        assert len(result.variables) == 1

    @pytest.mark.parametrize(
        "code",
        [
            FillCode.SHAPE_INVALID,
            FillCode.VALUE_REFUSED,
            FillCode.STATEMENT_FAILED,
            FillCode.TIMED_OUT,
        ],
    )
    def test_a_variable_failure_is_the_pages_code_and_leaves_the_bytes(
        self, case: Case, code: FillCode
    ) -> None:
        original = case.write(_page_text())
        resolver = FakeResolver({"zulu": _failed("zulu", code, f"detail of {code}")})
        result = _run(case, _template(), resolver)
        assert (result.code, result.detail) == (code, f"detail of {code}")
        assert result.variables[-1].name == "zulu"
        assert resolver.resolved() == ["alpha", "mike", "zulu"]
        assert case.bytes() == original


# --------------------------------------------------------------------------- #
# The index must hold this exact file
# --------------------------------------------------------------------------- #


class TestIndexBehind:
    def test_no_variable_is_resolved_and_nothing_is_written(self, case: Case) -> None:
        original = case.write(_page_text())
        resolver = FakeResolver(current=False)
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.INDEX_BEHIND
        assert result.variables == ()
        assert result.post is None
        assert resolver.calls == [("current", _KEY_B, _REL, original)]
        assert case.bytes() == original

    def test_the_freshness_check_gets_the_bytes_as_read_not_as_decoded(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())
        assert b"\r\n" in original
        resolver = FakeResolver()
        _run(case, _template(), resolver, writing=False)
        assert resolver.calls[0] == ("current", _KEY_B, _REL, original)


# --------------------------------------------------------------------------- #
# Composition refusals
# --------------------------------------------------------------------------- #


class TestComposition:
    def test_a_missing_page_value_outside_a_clause_is_value_missing(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())  # the page records no distance
        template = _template(title="{zulu} {distance_km}", names=("zulu",))
        result = _run(case, template, FakeResolver())
        assert (result.code, result.detail) == (FillCode.VALUE_MISSING, "distance_km")
        assert result.post is None
        assert result.variables == (_ok("zulu", "Z"),)
        assert case.bytes() == original

    def test_an_absent_variable_outside_a_clause_is_value_missing_by_name(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())
        result = _run(case, _template(), FakeResolver({"mike": _ok("mike", None)}))
        assert (result.code, result.detail) == (FillCode.VALUE_MISSING, "mike")
        assert [v.name for v in result.variables] == ["alpha", "mike", "zulu"]
        assert case.bytes() == original

    def test_a_missing_description_value_is_value_missing(self, case: Case) -> None:
        original = case.write(_page_text())
        template = _template(
            title="{zulu}", description="{distance_mi}", names=("zulu",)
        )
        result = _run(case, template, FakeResolver())
        assert (result.code, result.detail) == (FillCode.VALUE_MISSING, "distance_mi")
        assert case.bytes() == original

    def test_an_empty_title_is_title_empty(self, case: Case) -> None:
        original = case.write(_page_text())
        template = _template(
            title="{?{alpha}}", description="{zulu}", names=("alpha", "zulu")
        )
        result = _run(case, template, FakeResolver({"alpha": _ok("alpha", None)}))
        assert (result.code, result.detail) == (FillCode.TITLE_EMPTY, None)
        assert result.post is None
        assert case.bytes() == original

    @pytest.mark.parametrize("marker", ["<!--", "-->", "--!>"])
    def test_a_marker_in_a_variable_value_in_the_title_is_unsafe(
        self, case: Case, marker: str
    ) -> None:
        original = case.write(_page_text())
        resolver = FakeResolver({"mike": _ok("mike", f"x {marker} y")})
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.UNSAFE_TEXT
        assert result.detail == f"the composed title holds {marker!r}"
        assert [v.name for v in result.variables] == ["alpha", "mike", "zulu"]
        assert result.post is None
        assert case.bytes() == original

    @pytest.mark.parametrize("marker", ["<!--", "-->", "--!>"])
    def test_a_marker_in_the_description_is_unsafe(
        self, case: Case, marker: str
    ) -> None:
        original = case.write(_page_text())
        template = _template(
            title="{zulu}", description="{alpha}", names=("alpha", "zulu")
        )
        resolver = FakeResolver({"alpha": _ok("alpha", f"a{marker}b")})
        result = _run(case, template, resolver)
        assert result.code is FillCode.UNSAFE_TEXT
        assert result.detail == f"the composed description holds {marker!r}"
        assert case.bytes() == original

    @pytest.mark.parametrize("marker", ["<!--", "-->", "--!>"])
    def test_a_marker_in_a_page_value_is_unsafe(self, case: Case, marker: str) -> None:
        original = case.write(_page_text(title=f"Run {marker} end"))
        template = _template(title="{title} {zulu}", names=("zulu",))
        result = _run(case, template, FakeResolver())
        assert result.code is FillCode.UNSAFE_TEXT
        assert case.bytes() == original

    def test_a_marker_in_neighbouring_text_that_is_not_one_is_fine(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        resolver = FakeResolver({"mike": _ok("mike", "<! -- -- > !>")})
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.FILLED


# --------------------------------------------------------------------------- #
# Pages that are not filled for what they are
# --------------------------------------------------------------------------- #


class TestPageGates:
    @pytest.mark.parametrize(
        "start",
        [None, "2021-09-08T06:05:00", "tomorrow"],
        ids=["absent", "naive", "unparseable"],
    )
    def test_no_aware_start_is_no_start_time(
        self, case: Case, start: str | None
    ) -> None:
        original = case.write(_page_text(start=start))
        resolver = FakeResolver()
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.NO_START_TIME
        assert result.state is RegionState.WAITING
        assert resolver.calls == []
        assert case.bytes() == original

    @pytest.mark.parametrize(
        "version",
        [contract.DOC_VERSION - 1, contract.DOC_VERSION + 1, None],
        ids=["older", "newer", "unversioned"],
    )
    def test_a_page_of_another_format_is_never_written_or_resolved(
        self, case: Case, version: int | None
    ) -> None:
        original = case.write(_page_text(version=version))
        resolver = FakeResolver()
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.PAGE_NOT_CURRENT
        assert result.state is None
        assert result.detail
        assert resolver.calls == []
        assert case.bytes() == original

    def test_older_and_newer_pages_say_which(self, case: Case) -> None:
        case.write(_page_text(version=contract.DOC_VERSION - 1))
        older = _run(case, _template(), FakeResolver())
        case.write(_page_text(version=contract.DOC_VERSION + 1))
        newer = _run(case, _template(), FakeResolver())
        assert older.detail != newer.detail
        assert "older" in (older.detail or "")
        assert "newer" in (newer.detail or "")

    @pytest.mark.parametrize(
        "kwargs",
        [{"post_region": False}, {"close_post": False}],
        ids=["no-post-region", "unclosed-post-region"],
    )
    def test_a_page_with_damaged_markers_is_never_written(
        self, case: Case, kwargs: dict[str, bool]
    ) -> None:
        original = case.write(_page_text(**kwargs))  # type: ignore[arg-type]
        resolver = FakeResolver()
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.PAGE_NOT_CURRENT
        assert result.detail
        assert resolver.calls == []
        assert case.bytes() == original

    def test_an_athletes_page_is_reported_and_never_resolved_or_written(
        self, case: Case
    ) -> None:
        original = case.write(_page_text(post="My own words"))
        resolver = FakeResolver()
        result = _run(case, _template(), resolver)
        assert result.code is FillCode.ATHLETES_TEXT
        assert result.state is RegionState.ATHLETES
        assert resolver.calls == []
        assert case.bytes() == original

    def test_an_athletes_page_without_a_start_is_still_the_athletes(
        self, case: Case
    ) -> None:
        case.write(_page_text(post="Mine", start=None))
        assert _run(case, _template(), FakeResolver()).code is FillCode.ATHLETES_TEXT


# --------------------------------------------------------------------------- #
# Refill: the same text is not a change
# --------------------------------------------------------------------------- #


class TestRefill:
    def test_the_same_text_is_unchanged_and_nothing_is_written(
        self, case: Case, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        case.write(_page_text())
        template = _template()
        assert _run(case, template, FakeResolver()).code is FillCode.FILLED
        filled = case.bytes()
        os.utime(case.selected.path, ns=(1, 1))

        def refuse(path: Path, data: bytes) -> bool:
            raise AssertionError("an unchanged page must not be written")

        monkeypatch.setattr(engine, "write_bytes_if_changed", refuse)
        result = _run(case, template, FakeResolver())
        assert result.code is FillCode.UNCHANGED
        assert result.state is RegionState.FILLED
        assert result.changed is False
        assert result.post == Post("Z A M Run", "")
        assert case.bytes() == filled
        assert case.selected.path.stat().st_mtime_ns == 1

    def test_the_same_text_from_another_template_digest_leaves_the_stamp(
        self, case: Case
    ) -> None:
        """Only the text decides: a new template digest alone is not a change."""
        case.write(_page_text())
        first = _template(title="{zulu} {alpha} {mike} {sport}")
        _run(case, first, FakeResolver())
        filled = case.bytes()
        other = _template(
            title="{zulu} {alpha} {mike} {sport}",
            description="",
            names=("alpha", "mike", "zulu"),
        )
        other = replace(other, digest="cd" * 32)
        result = _run(case, other, FakeResolver())
        assert result.code is FillCode.UNCHANGED
        assert case.bytes() == filled
        assert b"cd" * 32 not in filled

    def test_changed_text_replaces_the_filled_region_with_a_new_stamp(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        template = _template()
        _run(case, template, FakeResolver())
        before = case.bytes()
        other = replace(template, digest="cd" * 32)
        result = _run(case, other, FakeResolver({"alpha": _ok("alpha", "A2")}))
        assert result.code is FillCode.FILLED
        assert result.state is RegionState.FILLED
        assert result.changed is True
        assert case.bytes() == _splice(before, _filled(other, "Z A2 M Run"))

    def test_a_filled_region_is_judged_by_its_text_not_its_whole_content(
        self, case: Case
    ) -> None:
        """A changed description alone, after an identical title, is a change."""
        case.write(_page_text())
        one = _template(title="{zulu}", description="{alpha}", names=("alpha", "zulu"))
        _run(case, one, FakeResolver())
        result = _run(case, one, FakeResolver({"alpha": _ok("alpha", "other")}))
        assert result.code is FillCode.FILLED
        assert result.post == Post("Z", "other")

    def test_a_dry_run_over_a_filled_page_reports_the_change_without_writing(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        template = _template()
        _run(case, template, FakeResolver())
        before = case.bytes()
        same = _run(case, template, FakeResolver(), writing=False)
        moved = _run(
            case,
            template,
            FakeResolver({"zulu": _ok("zulu", "Z2")}),
            writing=False,
        )
        assert (same.code, same.changed) == (FillCode.UNCHANGED, False)
        assert (moved.code, moved.changed) == (FillCode.WOULD_FILL, True)
        assert case.bytes() == before


# --------------------------------------------------------------------------- #
# Edits during the run, and write errors
# --------------------------------------------------------------------------- #


class TestConcurrentEdit:
    def test_an_edit_outside_the_region_wins(self, case: Case) -> None:
        original = case.write(_page_text())
        edited = original + b"\r\nathlete's late note"

        def edit(_name: str) -> None:
            case.selected.path.write_bytes(edited)

        result = _run(case, _template(), FakeResolver(on_resolve=edit))
        assert result.code is FillCode.PAGE_CHANGED
        assert result.changed is True
        assert result.post == Post("Z A M Run", "")
        assert case.bytes() == edited

    def test_an_edit_inside_the_region_wins(self, case: Case) -> None:
        original = case.write(_page_text())
        edited = _splice(original, "The athlete wrote this")

        def edit(_name: str) -> None:
            case.selected.path.write_bytes(edited)

        result = _run(case, _template(), FakeResolver(on_resolve=edit))
        assert result.code is FillCode.PAGE_CHANGED
        assert case.bytes() == edited

    def test_the_file_removed_during_the_run_is_not_recreated(self, case: Case) -> None:
        case.write(_page_text())

        def remove(_name: str) -> None:
            case.selected.path.unlink(missing_ok=True)

        result = _run(case, _template(), FakeResolver(on_resolve=remove))
        assert result.code is FillCode.PAGE_CHANGED
        assert not case.selected.path.exists()

    def test_the_file_replaced_by_a_symlink_is_left_alone(self, case: Case) -> None:
        original = case.write(_page_text())
        target = case.root / "elsewhere.md"
        target.write_bytes(original)

        def swap(_name: str) -> None:
            case.selected.path.unlink()
            case.selected.path.symlink_to(target)

        result = _run(case, _template(), FakeResolver(on_resolve=swap))
        assert result.code is FillCode.PAGE_CHANGED
        assert case.selected.path.is_symlink()
        assert target.read_bytes() == original

    def test_an_edit_that_restores_the_same_bytes_is_no_conflict(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())

        def rewrite(_name: str) -> None:
            case.selected.path.write_bytes(original)

        result = _run(case, _template(), FakeResolver(on_resolve=rewrite))
        assert result.code is FillCode.FILLED


@contextmanager
def _read_only(directory: Path) -> Iterator[None]:
    mode = stat.S_IMODE(directory.stat().st_mode)
    directory.chmod(0o500)
    try:
        yield
    finally:
        directory.chmod(mode)


class TestWriteFailure:
    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory modes")
    def test_an_unwritable_directory_is_write_failed_and_leaves_the_page(
        self, case: Case
    ) -> None:
        original = case.write(_page_text())
        with _read_only(case.root / "workouts"):
            result = _run(case, _template(), FakeResolver())
        assert result.code is FillCode.WRITE_FAILED
        assert result.detail and "could not be written" in result.detail
        assert result.post == Post("Z A M Run", "")
        assert result.changed is True
        assert case.bytes() == original
        assert [p.name for p in (case.root / "workouts").iterdir()] == [
            case.selected.path.name
        ]


class TestSpliceAndJunctions:
    def test_an_emptied_region_is_filled_in_place(self, case: Case) -> None:
        original = case.write(_page_text(post=""))
        template = _template()
        result = _run(case, template, FakeResolver())
        assert (result.code, result.state) == (FillCode.FILLED, RegionState.WAITING)
        assert case.bytes() == _splice(original, _filled(template, "Z A M Run"))

    def test_the_region_is_replaced_not_its_text_found_elsewhere(
        self, case: Case
    ) -> None:
        """The notes region holds the post's current content, earlier in the file."""
        original = case.write(_page_text(notes=contract.POST_PLACEHOLDER))
        assert original.count(contract.POST_PLACEHOLDER.encode()) == 2
        template = _template()
        _run(case, template, FakeResolver())
        assert case.bytes() == _splice(original, _filled(template, "Z A M Run"))

    @pytest.mark.parametrize(
        ("title", "value"),
        [("{zulu}->", "-"), ("<!{zulu}", "--"), ("{zulu}>", "--!")],
        ids=["closing", "opening", "bang-closing"],
    )
    def test_a_marker_formed_where_text_and_value_meet_is_unsafe(
        self, case: Case, title: str, value: str
    ) -> None:
        original = case.write(_page_text())
        template = _template(title=title, names=("zulu",))
        result = _run(case, template, FakeResolver({"zulu": _ok("zulu", value)}))
        assert result.code is FillCode.UNSAFE_TEXT
        assert case.bytes() == original

    def test_the_key_keeps_its_case(self, case: Case) -> None:
        upper = "AB" * 32
        case.write(_page_text(sources=("cd" * 32, upper)))
        resolver = FakeResolver()
        _run(case, _template(), resolver, writing=False)
        assert resolver.calls[0][1] == upper
        assert resolver.calls[1][2] == Binding(_AS_OF, upper)

    def test_a_last_ref_that_is_not_an_archive_ref_binds_no_key(
        self, case: Case
    ) -> None:
        case.write(_page_text(raw_last_ref="notes/other.fit"))
        resolver = FakeResolver(current=False)
        _run(case, _template(), resolver)
        assert resolver.calls[0][1] is None

    def test_a_variable_failure_over_a_filled_region_keeps_it(self, case: Case) -> None:
        case.write(_page_text())
        template = _template()
        _run(case, template, FakeResolver())
        filled = case.bytes()
        failure = _failed("mike", FillCode.TIMED_OUT, "slow")
        result = _run(case, template, FakeResolver({"mike": failure}))
        assert (result.code, result.state) == (FillCode.TIMED_OUT, RegionState.FILLED)
        assert case.bytes() == filled


# --------------------------------------------------------------------------- #
# Reading a page once
# --------------------------------------------------------------------------- #


def _filled_region(text: str = "Z A M Run") -> str:
    return render_filled(Post(text, ""), template_digest="ab" * 32, as_of=_AS_OF)


def _ledger(sha: str, *, digest: str | None) -> PublishLedger:
    record = PublicationRecord(
        page=workout_page_key(sha), publication_id="1" * 32, digest=digest
    )
    return PublishLedger("t", "c", (record,))


class TestReadForFill:
    def test_the_bytes_are_kept_exactly(self, case: Case) -> None:
        original = case.write(_page_text())
        read = _read(case)
        assert read.data == original
        assert read.selected is case.selected
        assert read.view.text == original.decode()

    @pytest.mark.parametrize(
        ("post", "state"),
        [
            (contract.POST_PLACEHOLDER, RegionState.WAITING),
            ("", RegionState.WAITING),
            (_filled_region(), RegionState.FILLED),
            ("Mine", RegionState.ATHLETES),
        ],
        ids=["placeholder", "emptied", "filled", "athletes"],
    )
    def test_the_state_is_the_regions(
        self, case: Case, post: str, state: RegionState
    ) -> None:
        case.write(_page_text(post=post))
        assert _read(case).state is state

    def test_a_crlf_edit_of_a_filled_region_makes_it_the_athletes(
        self, case: Case
    ) -> None:
        """Read as bytes: decoded text with CRLF folded would still look Filled."""
        region = render_filled(
            Post("T", "one\n\ntwo"), template_digest="ab" * 32, as_of=_AS_OF
        )
        case.write(_page_text(post=region))
        assert _read(case).state is RegionState.FILLED
        stamp, _, text = region.partition("\n")
        case.write(_page_text(post=stamp + "\n" + text.replace("\n", "\r\n")))
        assert _read(case).state is RegionState.ATHLETES

    def test_a_page_that_is_not_current_has_no_state(self, case: Case) -> None:
        case.write(_page_text(version=contract.DOC_VERSION - 1))
        read = _read(case)
        assert read.state is None
        assert read.view.regions is None

    @pytest.mark.parametrize(
        ("day", "in_window"),
        [
            ("2021-09-08", True),
            ("2021-09-09", True),
            ("2021-09-07", False),
            (None, False),
        ],
    )
    def test_the_window_is_the_pages_date_on_or_after_since(
        self, case: Case, day: str | None, in_window: bool
    ) -> None:
        case.write(_page_text(day=day))
        assert _read(case).in_window is in_window

    def test_a_landed_post_is_found_by_any_recorded_source(self, case: Case) -> None:
        case.write(_page_text())
        for sha in (_KEY_A, _KEY_B):
            assert _read(case, (_ledger(sha, digest="f" * 64),)).landed is True

    def test_a_record_without_a_digest_or_for_another_file_is_not_landed(
        self, case: Case
    ) -> None:
        case.write(_page_text())
        assert _read(case, (_ledger(_KEY_B, digest=None),)).landed is False
        assert _read(case, (_ledger(_OTHER, digest="f" * 64),)).landed is False
        assert _read(case, ()).landed is False

    def test_a_landed_post_in_any_ledger_counts(self, case: Case) -> None:
        case.write(_page_text())
        ledgers = (
            _ledger(_OTHER, digest="f" * 64),
            _ledger(_KEY_A, digest=None),
            _ledger(_KEY_B, digest="e" * 64),
        )
        assert _read(case, ledgers).landed is True

    def test_the_row_carries_the_pages_state_window_and_landed(
        self, case: Case
    ) -> None:
        case.write(_page_text(post=_filled_region(), day="2021-08-31"))
        result = _run(
            case,
            _template(),
            FakeResolver(),
            ledgers=(_ledger(_KEY_B, digest="f" * 64),),
        )
        assert (result.state, result.in_window, result.landed) == (
            RegionState.FILLED,
            False,
            True,
        )

    def test_a_landed_page_is_still_filled_when_asked(self, case: Case) -> None:
        """The pass drops landed pages before this; a named refill does not."""
        case.write(_page_text())
        result = _run(
            case,
            _template(),
            FakeResolver(),
            ledgers=(_ledger(_KEY_B, digest="f" * 64),),
        )
        assert (result.code, result.landed) == (FillCode.FILLED, True)

    def test_an_unreadable_page_is_a_not_current_row(self, case: Case) -> None:
        result = read_for_fill(case.selected, since=_SINCE, ledgers=())
        assert result == PageResult(
            page=_REL,
            state=None,
            in_window=False,
            landed=False,
            code=FillCode.PAGE_NOT_CURRENT,
            detail="the page could not be read as a workout page",
            variables=(),
            post=None,
            changed=None,
        )

    def test_a_file_that_is_not_a_workout_page_and_a_symlink_are_not_current(
        self, case: Case
    ) -> None:
        case.selected.path.write_text("---\ntype: note\n---\nbody\n", encoding="utf-8")
        result = read_for_fill(case.selected, since=_SINCE, ledgers=())
        assert isinstance(result, PageResult)
        assert result.code is FillCode.PAGE_NOT_CURRENT
        case.selected.path.unlink()
        target = case.root / "real.md"
        target.write_bytes(_page_text().encode())
        case.selected.path.symlink_to(target)
        result = read_for_fill(case.selected, since=_SINCE, ledgers=())
        assert isinstance(result, PageResult)
        assert result.code is FillCode.PAGE_NOT_CURRENT

    def test_a_page_with_unparseable_frontmatter_is_not_current(
        self, case: Case
    ) -> None:
        case.selected.path.write_text("no frontmatter at all\n", encoding="utf-8")
        result = read_for_fill(case.selected, since=_SINCE, ledgers=())
        assert isinstance(result, PageResult)
        assert result.page == _REL


def test_a_utc_start_binds_the_same_wall_clock_without_an_offset(case: Case) -> None:
    """A UTC start has the wall clock of UTC: the binding is naive all the same."""
    case.write(_page_text(start=datetime(2021, 9, 8, 6, 5, tzinfo=UTC).isoformat()))
    resolver = FakeResolver()
    _run(case, _template(), resolver, writing=False)
    binding = next(c[2] for c in resolver.calls if c[0] == "resolve")
    assert binding == Binding(_AS_OF, _KEY_B)
