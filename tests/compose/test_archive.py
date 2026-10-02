"""Composing a page's listed archived files (channel-merge Req 6.3, 7.2;
design.md § ArchiveComposition).

Every test builds a temporary data root laid out as sync lays one out: each
file is stored at `fit-archive/<sha256 of its bytes>.fit` and listed by the
data-root-relative ref `source_ref` gives. The fixture bytes come from
`tests/fixtures/merge.py`: `run_trio_fit_bytes()` is `(healthfit, stryd_a,
stryd_b)` where the two Stryd files differ in form power by one watt at every
sample, so which one donated is readable from the composed values.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from fitdocs import parse_fit
from fitdocs.compose.archive import compose_listed
from fitdocs.compose.composer import compose_activity
from fitdocs.ingest.errors import FitDecodeError
from fitdocs.layout import archive_path, source_ref
from fitdocs.model import Activity
from tests.fixtures import merge


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive(root: Path, data: bytes) -> str:
    """Store `data` under its own hash in `root`'s archive; return its ref."""
    sha = _sha(data)
    path = archive_path(root, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return source_ref(sha)


def _shas(composition_extras: tuple[object, ...]) -> list[str]:
    return [getattr(c, "sha256") for c in composition_extras]  # noqa: B009


@pytest.fixture
def trio() -> tuple[bytes, bytes, bytes]:
    return merge.run_trio_fit_bytes()


class TestOrder:
    def test_extras_compose_in_reverse_list_order(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, stryd_b = trio
        refs = [
            _archive(tmp_path, stryd_a),
            _archive(tmp_path, stryd_b),
            _archive(tmp_path, healthfit),
        ]
        base = parse_fit(healthfit)

        result = compose_listed(tmp_path, refs, base)

        # the premise: the two orders give different composed values
        in_list_order = compose_activity(base, [parse_fit(stryd_a), parse_fit(stryd_b)])
        in_reverse = compose_activity(base, [parse_fit(stryd_b), parse_fit(stryd_a)])
        assert in_list_order.activity.samples.form_power_w != (
            in_reverse.activity.samples.form_power_w
        )
        assert any(v is not None for v in in_reverse.activity.samples.form_power_w)

        assert result.provenance.base.sha256 == _sha(healthfit)
        assert _shas(result.provenance.extras) == [_sha(stryd_b), _sha(stryd_a)]
        assert result.activity.samples.form_power_w == (
            in_reverse.activity.samples.form_power_w
        )
        assert result.provenance.extras[0].channels != ()
        assert result.provenance.extras[1].channels == ()


class TestSkips:
    def test_a_missing_file_is_skipped(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, stryd_b = trio
        refs = [
            _archive(tmp_path, stryd_a),
            source_ref(_sha(stryd_b)),
            _archive(tmp_path, healthfit),
        ]
        assert not archive_path(tmp_path, _sha(stryd_b)).exists()

        result = compose_listed(tmp_path, refs, parse_fit(healthfit))

        assert _shas(result.provenance.extras) == [_sha(stryd_a)]

    def test_a_directory_at_the_archive_path_is_skipped(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, stryd_b = trio
        refs = [
            _archive(tmp_path, stryd_a),
            source_ref(_sha(stryd_b)),
            _archive(tmp_path, healthfit),
        ]
        not_a_file = archive_path(tmp_path, _sha(stryd_b))
        not_a_file.mkdir(parents=True)
        assert not_a_file.exists()
        assert not not_a_file.is_file()

        result = compose_listed(tmp_path, refs, parse_fit(healthfit))

        assert _shas(result.provenance.extras) == [_sha(stryd_a)]

    def test_a_traversal_shaped_ref_is_skipped(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, _ = trio
        (tmp_path / "stray.fit").write_bytes(stryd_a)
        refs = [
            "fit-archive/../stray.fit",
            _archive(tmp_path, healthfit),
        ]
        assert (tmp_path / refs[0]).is_file()

        result = compose_listed(tmp_path, refs, parse_fit(healthfit))

        assert result.provenance.extras == ()

    def test_a_foreign_ref_is_skipped(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, _ = trio
        foreign = f"elsewhere/{_sha(stryd_a)}.fit"
        (tmp_path / "elsewhere").mkdir()
        (tmp_path / foreign).write_bytes(stryd_a)
        refs = [foreign, _archive(tmp_path, healthfit)]
        assert (tmp_path / foreign).is_file()
        assert not archive_path(tmp_path, _sha(stryd_a)).exists()

        result = compose_listed(tmp_path, refs, parse_fit(healthfit))

        assert result.provenance.extras == ()

    def test_a_ref_repeating_the_bases_hash_is_skipped(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, _ = trio
        base_ref = _archive(tmp_path, healthfit)
        refs = [base_ref, _archive(tmp_path, stryd_a), base_ref]
        base = parse_fit(healthfit)
        assert refs[0] == refs[2]
        assert archive_path(tmp_path, base.provenance.sha256).is_file()

        result = compose_listed(tmp_path, refs, base)

        assert len(result.provenance.extras) == 1
        assert _shas(result.provenance.extras) == [_sha(stryd_a)]

    def test_a_ref_repeating_an_earlier_extras_hash_is_skipped(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, stryd_b = trio
        ref_a = _archive(tmp_path, stryd_a)
        refs = [
            ref_a,
            _archive(tmp_path, stryd_b),
            ref_a,
            _archive(tmp_path, healthfit),
        ]
        assert refs[0] == refs[2]
        assert archive_path(tmp_path, _sha(stryd_a)).is_file()

        result = compose_listed(tmp_path, refs, parse_fit(healthfit))

        # reversed the extras are a, b, a: the second a is the repeat
        assert len(result.provenance.extras) == 2
        assert _shas(result.provenance.extras) == [_sha(stryd_a), _sha(stryd_b)]


class TestErrorsPropagate:
    def test_a_truncated_extra_raises_the_decode_error(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, _ = trio
        truncated = stryd_a[: len(stryd_a) // 2]
        with pytest.raises(FitDecodeError):
            parse_fit(truncated)
        refs = [_archive(tmp_path, truncated), _archive(tmp_path, healthfit)]

        with pytest.raises(FitDecodeError):
            compose_listed(tmp_path, refs, parse_fit(healthfit))

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads unreadable files")
    def test_an_unreadable_extra_raises_the_read_error(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, stryd_a, _ = trio
        refs = [_archive(tmp_path, stryd_a), _archive(tmp_path, healthfit)]
        path = archive_path(tmp_path, _sha(stryd_a))
        path.chmod(0)
        try:
            with pytest.raises(PermissionError):
                path.read_bytes()
            with pytest.raises(PermissionError):
                compose_listed(tmp_path, refs, parse_fit(healthfit))
        finally:
            path.chmod(0o600)


class TestBaseAlone:
    def test_a_page_listing_only_its_base_returns_the_base_object(
        self, tmp_path: Path, trio: tuple[bytes, bytes, bytes]
    ) -> None:
        healthfit, _, _ = trio
        base: Activity = parse_fit(healthfit)

        result = compose_listed(tmp_path, [_archive(tmp_path, healthfit)], base)

        assert result.activity is base
        assert result.provenance.extras == ()
