from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from fitdocs.load.render import LoadPayload


@contextmanager
def _restore_recursion_limit() -> Iterator[int]:
    original_limit = sys.getrecursionlimit()
    try:
        yield original_limit
    finally:
        sys.setrecursionlimit(original_limit)


def _producer_module() -> Any:
    return importlib.import_module("fitdocs.index.producer")


def test_public_aliases_and_load_status_are_exact() -> None:
    producer = _producer_module()

    sql_value = vars(producer)["SqlValue"]
    row = vars(producer)["Row"]
    rows = vars(producer)["Rows"]
    assert sql_value == (
        str | int | float | bool | date | datetime | tuple[str, ...] | None
    )
    assert get_origin(row) is tuple
    assert get_args(row) == (sql_value, Ellipsis)
    assert get_origin(rows) is Mapping
    assert get_args(rows)[0] is str
    row_sequence = get_args(rows)[1]
    assert get_origin(row_sequence) is Sequence
    assert get_args(row_sequence) == (row,)
    assert get_args(producer.LoadStatus) == (
        "computed",
        "unsupported",
        "not_computed",
        "unreadable",
    )
    assert get_type_hints(producer.LoadRegionReading) == {
        "status": producer.LoadStatus,
        "payload": LoadPayload | None,
    }


def test_carrier_fields_types_and_frozen_contract_are_exact() -> None:
    producer = _producer_module()
    from fitdocs.compose.types import ChannelProvenance
    from fitdocs.index.producer import (
        CorpusLeftOut,
        CorpusPage,
        CorpusSnapshot,
        LoadRegionReading,
        PageComputed,
        PageDocument,
    )
    from fitdocs.metrics.types import AthleteInputs, DerivedMetrics
    from fitdocs.model import Activity

    expected = {
        LoadRegionReading: (
            ("status", "payload"),
            {"status": producer.LoadStatus, "payload": LoadPayload | None},
        ),
        PageDocument: (
            ("page_key", "path", "text", "frontmatter", "sources", "load"),
            {
                "page_key": str,
                "path": str,
                "text": str,
                "frontmatter": Mapping[str, object],
                "sources": tuple[str, ...],
                "load": LoadRegionReading,
            },
        ),
        PageComputed: (
            (
                "document",
                "activity",
                "metrics",
                "provenance",
                "athlete",
                "athlete_fingerprint",
            ),
            {
                "document": PageDocument,
                "activity": Activity,
                "metrics": DerivedMetrics,
                "provenance": ChannelProvenance,
                "athlete": AthleteInputs | None,
                "athlete_fingerprint": str,
            },
        ),
        CorpusPage: (
            ("page_key", "path", "frontmatter", "document_fingerprint"),
            {
                "page_key": str,
                "path": str,
                "frontmatter": Mapping[str, object],
                "document_fingerprint": str,
            },
        ),
        CorpusLeftOut: (
            ("path", "document_fingerprint"),
            {"path": str, "document_fingerprint": str},
        ),
        CorpusSnapshot: (
            ("data_root", "pages", "left_out", "today", "athlete_fingerprint"),
            {
                "data_root": Path,
                "pages": tuple[CorpusPage, ...],
                "left_out": tuple[CorpusLeftOut, ...],
                "today": date,
                "athlete_fingerprint": str,
            },
        ),
    }
    for carrier, (names, expected_hints) in expected.items():
        assert tuple(field.name for field in fields(carrier)) == names
        assert get_type_hints(carrier) == expected_hints
        assert vars(carrier)["__dataclass_params__"].frozen is True


def test_protocol_signatures_are_exact() -> None:
    _producer_module()
    from fitdocs.index.producer import (
        ComputedProducer,
        CorpusProducer,
        CorpusSnapshot,
        DocumentProducer,
        PageComputed,
        PageDocument,
        Rows,
    )
    from fitdocs.index.schema import TableSpec

    for protocol, input_type in (
        (DocumentProducer, PageDocument),
        (ComputedProducer, PageComputed),
        (CorpusProducer, CorpusSnapshot),
    ):
        assert get_type_hints(vars(protocol)["name"].fget) == {"return": str}
        assert get_type_hints(vars(protocol)["tables"].fget) == {
            "return": tuple[TableSpec, ...]
        }
        arg_name = "corpus" if protocol is CorpusProducer else "page"
        assert get_type_hints(vars(protocol)["rows"]) == {
            arg_name: input_type,
            "return": Rows,
        }
    assert get_type_hints(CorpusProducer.fingerprint) == {
        "corpus": CorpusSnapshot,
        "return": str,
    }


def test_protocols_accept_frozen_producers_and_reject_wrong_inputs(
    tmp_path: Path,
) -> None:
    _producer_module()
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "producer_protocol_probe.py"
    source.write_text(
        """from dataclasses import dataclass
from typing import Mapping, Sequence
from fitdocs.index.producer import (CorpusProducer, CorpusSnapshot, DocumentProducer,
    PageDocument, ComputedProducer, PageComputed, Rows)
from fitdocs.index.schema import TableSpec

@dataclass(frozen=True)
class Doc:
    name: str
    tables: tuple[TableSpec, ...]
    def rows(self, page: PageDocument) -> Rows: return {}
@dataclass(frozen=True)
class Computed:
    name: str
    tables: tuple[TableSpec, ...]
    def rows(self, page: PageComputed) -> Rows: return {}
@dataclass(frozen=True)
class Corpus:
    name: str
    tables: tuple[TableSpec, ...]
    def fingerprint(self, corpus: CorpusSnapshot) -> str: return "fingerprint"
    def rows(self, corpus: CorpusSnapshot) -> Rows: return {}

doc: DocumentProducer = Doc("doc", ())
computed: ComputedProducer = Computed("computed", ())
corpus: CorpusProducer = Corpus("corpus", ())
""",
        encoding="utf-8",
    )
    with _restore_recursion_limit() as original_limit:
        import mypy.api

        args = [
            "--config-file",
            str(root / "pyproject.toml"),
            "--cache-dir",
            str(tmp_path / "cache"),
            str(source),
        ]
        stdout, stderr, status = mypy.api.run(args)
        assert status == 0, stdout + stderr

        negative_cases = (
            ("DocumentProducer", "page: PageDocument", "page: PageComputed"),
            ("ComputedProducer", "page: PageComputed", "page: PageDocument"),
            ("CorpusProducer", "corpus: CorpusSnapshot", "corpus: PageDocument"),
        )
        original = source.read_text(encoding="utf-8")
        for protocol, expected_input, wrong_input in negative_cases:
            if protocol == "CorpusProducer":
                original_method = (
                    "def rows(self, corpus: CorpusSnapshot) -> Rows: return {}"
                )
                wrong_method = f"def rows(self, {wrong_input}) -> Rows: return {{}}"
            else:
                original_method = (
                    f"def rows(self, {expected_input}) -> Rows: return {{}}"
                )
                wrong_method = f"def rows(self, {wrong_input}) -> Rows: return {{}}"
            mutated = original.replace(original_method, wrong_method)
            bad_source = tmp_path / f"wrong_{protocol}.py"
            bad_source.write_text(mutated, encoding="utf-8")
            bad_out, bad_err, bad_status = mypy.api.run(
                [
                    "--config-file",
                    str(root / "pyproject.toml"),
                    "--cache-dir",
                    str(tmp_path / f"cache_{protocol}"),
                    str(bad_source),
                ]
            )
            assert bad_status != 0, bad_out + bad_err
            assert "error:" in bad_out and protocol in bad_out and "rows" in bad_out

    assert sys.getrecursionlimit() == original_limit
