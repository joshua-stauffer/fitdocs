"""Byte determinism of the chart kit: in one process and across processes.

Requirements 16.1, 16.2. Every case of every registered kind (found through the
registry and the kind test modules' ``CASES``, the naming convention
``test_<name with - as _>.py``) is rendered twice in this process, then in two
child interpreters whose hash seed, time zone and locale differ. Each child
prints one SHA-256 per case; the two maps must be equal and equal to the
digests computed here. A request whose ``channels`` and ``options`` mappings
are built in reverse order must render the same bytes.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from fitdocs.render.charts.kit.api import render_chart
from fitdocs.render.charts.kit.registry import KINDS
from fitdocs.render.charts.kit.schema import ChartRequest
from tests.render.charts.kit._helpers import Case

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = "tests.render.charts.kit.test_determinism"

#: (PYTHONHASHSEED, TZ, LC_ALL) of the two child interpreters.
ENVIRONMENTS = (("0", "UTC", "C"), ("1", "Pacific/Auckland", "C.UTF-8"))


def _kind_modules() -> list[tuple[str, tuple[Case, ...]]]:
    return [
        (
            spec.name,
            importlib.import_module(
                f"tests.render.charts.kit.test_{spec.name.replace('-', '_')}"
            ).CASES,
        )
        for spec in KINDS
    ]


def _render(case: Case) -> str:
    return render_chart(case.request, case.data).text


def _digests() -> dict[str, str]:
    """``kind/case`` -> SHA-256 of the rendered bytes, for every registered case."""
    return {
        f"{kind}/{case.name}": hashlib.sha256(_render(case).encode("utf-8")).hexdigest()
        for kind, cases in _kind_modules()
        for case in cases
    }


def _reversed(request: ChartRequest) -> ChartRequest:
    return ChartRequest(
        request.ref,
        request.kind,
        request.title,
        dict(reversed(list(request.channels.items()))),
        dict(reversed(list(request.options.items()))),
    )


def _child(hash_seed: str, tz: str, lc_all: str) -> dict[str, str]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "TZ": tz, "LC_ALL": lc_all}
    done = subprocess.run(
        [sys.executable, "-m", MODULE],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    digests = json.loads(done.stdout)
    assert isinstance(digests, dict)
    return digests


def test_every_registered_kind_is_covered() -> None:
    modules = _kind_modules()
    assert len(modules) == len(KINDS) >= 8
    total = sum(len(cases) for _, cases in modules)
    assert all(cases for _, cases in modules)
    digests = _digests()
    assert len(digests) == total >= 60  # no two cases share a key
    assert len(set(digests.values())) > total // 2  # not one constant output


def test_two_renders_in_one_process_are_identical() -> None:
    cases = [case for _, cases in _kind_modules() for case in cases]
    assert cases
    for case in cases:
        first, second = _render(case), _render(case)
        assert first and first == second, case.name


def test_digests_agree_across_processes_and_with_this_one() -> None:
    here = _digests()
    first, second = (_child(*env) for env in ENVIRONMENTS)
    assert first == second
    assert first == here


def test_request_mapping_order_does_not_change_the_bytes() -> None:
    cases = [case for _, cases in _kind_modules() for case in cases]
    multi_channel = [c for c in cases if len(c.request.channels) >= 2]
    multi_option = [c for c in cases if len(c.request.options) >= 2]
    assert multi_channel and multi_option
    for case in cases:
        flipped = Case(case.name, _reversed(case.request), case.data)
        if len(case.request.channels) >= 2:
            assert list(flipped.request.channels) != list(case.request.channels)
        if len(case.request.options) >= 2:
            assert list(flipped.request.options) != list(case.request.options)
        assert _render(flipped) == _render(case), f"{case.request.kind}/{case.name}"


if __name__ == "__main__":
    print(json.dumps(_digests(), sort_keys=True))
