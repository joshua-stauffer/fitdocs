"""The Garmin attribution wording (intervals-connector task 2.2).

Pins :mod:`fitdocs.render.attribution` against design "GarminAttribution" and
requirements 8.1-8.4 and 8.6. Device tuples are hand-built; the base activity
is a parsed ride whose devices are replaced, so each fixture states exactly
the devices under test.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from fitdocs import parse_fit
from fitdocs.model import Activity, DeviceInfo
from fitdocs.render import attribution
from fitdocs.render.attribution import (
    attribution_line,
    garmin_label,
    recording_device,
)
from tests.fixtures import builder


def _dev(index: int | None, manufacturer: str | None, model: str | None) -> DeviceInfo:
    return DeviceInfo(
        device_index=index,
        manufacturer=manufacturer,
        product_name=model,
        serial_number=None,
        software_version=None,
        battery_status=None,
    )


def _base(*devices: DeviceInfo) -> Activity:
    return dataclasses.replace(parse_fit(builder.ride_fit_bytes()), devices=devices)


def _garmin(model: str | None, index: int = 0) -> DeviceInfo:
    return _dev(index, "garmin", model)


def _stryd(index: int = 0) -> DeviceInfo:
    return _dev(index, "stryd", "pod")


# recording_device -----------------------------------------------------------


def test_recording_device_is_the_first_index_zero_device() -> None:
    first, second = _garmin("edge_1040"), _stryd()
    assert recording_device((first, second)) is first


def test_recording_device_skips_a_leading_non_zero_index() -> None:
    other, zero = _garmin("fr965", index=1), _stryd()
    assert recording_device((other, zero)) is zero


def test_lone_index_one_device_is_no_recording_device() -> None:
    assert recording_device((_garmin("edge_1040", index=1),)) is None


def test_empty_tuple_is_no_recording_device() -> None:
    assert recording_device(()) is None


def test_device_with_absent_index_is_no_recording_device() -> None:
    assert recording_device((_dev(None, "garmin", "edge_1040"),)) is None


# garmin_label ---------------------------------------------------------------


def test_garmin_label_names_the_model() -> None:
    assert garmin_label((_garmin("edge_1040"),)) == "Garmin edge_1040"


def test_garmin_label_without_model_is_garmin_alone() -> None:
    assert garmin_label((_garmin(None),)) == "Garmin"


def test_garmin_label_with_blank_model_is_garmin_alone() -> None:
    assert garmin_label((_garmin(" \t\n "),)) == "Garmin"


def test_garmin_label_collapses_every_whitespace_run() -> None:
    assert garmin_label((_garmin("Edge\n1040"),)) == "Garmin Edge 1040"
    assert garmin_label((_garmin("  Edge \t\r\n  1040  "),)) == "Garmin Edge 1040"


@pytest.mark.parametrize("model", ["Garmin Edge 1040", "GARMIN edge 1040", "garmin"])
def test_garmin_label_does_not_double_the_brand(model: str) -> None:
    assert garmin_label((_garmin(model),)) == model


def test_garmin_label_collapses_whitespace_before_the_brand_check() -> None:
    assert garmin_label((_garmin("Garmin\nEdge"),)) == "Garmin Edge"


def test_a_model_merely_beginning_with_the_letters_is_prefixed() -> None:
    assert garmin_label((_garmin("Garminoid 3"),)) == "Garmin Garminoid 3"


def test_non_garmin_recording_device_has_no_label() -> None:
    assert garmin_label((_stryd(),)) is None


def test_manufacturer_must_be_exactly_garmin() -> None:
    assert garmin_label((_dev(0, "Garmin", "edge_1040"),)) is None
    assert garmin_label((_dev(0, None, "edge_1040"),)) is None


def test_garmin_at_index_one_before_a_stryd_recorder_gives_no_label() -> None:
    assert garmin_label((_garmin("edge_1040", index=1), _stryd())) is None


def test_two_index_zero_devices_attribute_the_first() -> None:
    assert garmin_label((_garmin("edge_1040"), _stryd())) == "Garmin edge_1040"


def test_empty_and_lone_index_one_tuples_have_no_label() -> None:
    assert garmin_label(()) is None
    assert garmin_label((_garmin("edge_1040", index=1),)) is None


# attribution_line -----------------------------------------------------------


def test_sole_garmin_creator_gives_the_single_source_line() -> None:
    assert (
        attribution_line(_base(_garmin("edge_1040"))) == "Data source: Garmin edge_1040"
    )


def test_absent_model_gives_garmin_alone() -> None:
    assert attribution_line(_base(_garmin(None))) == "Data source: Garmin"


def test_stryd_creator_gives_no_line() -> None:
    assert attribution_line(_base(_stryd())) is None


def test_garmin_at_index_one_before_stryd_recorder_gives_no_line() -> None:
    base = _base(_garmin("edge_1040", index=1), _stryd())
    assert attribution_line(base) is None


def test_empty_devices_give_no_line() -> None:
    assert attribution_line(_base()) is None


def test_lone_index_one_garmin_gives_no_line() -> None:
    assert attribution_line(_base(_garmin("edge_1040", index=1))) is None


def test_multiline_model_gives_one_line() -> None:
    line = attribution_line(_base(_garmin("Edge\n1040")))
    assert line == "Data source: Garmin Edge 1040"
    assert line is not None and len(line.splitlines()) == 1


def test_model_already_naming_garmin_is_not_doubled() -> None:
    line = attribution_line(_base(_garmin("Garmin Edge 1040")))
    assert line == "Data source: Garmin Edge 1040"


def test_two_index_zero_devices_attribute_the_garmin_one() -> None:
    line = attribution_line(_base(_garmin("edge_1040"), _stryd()))
    assert line == "Data source: Garmin edge_1040"


def test_two_index_zero_devices_stryd_first_gives_no_line() -> None:
    assert attribution_line(_base(_stryd(), _garmin("edge_1040"))) is None


def test_garmin_base_with_stryd_donor_adds_other_devices() -> None:
    line = attribution_line(_base(_garmin("edge_1040")), [(_stryd(),)])
    assert line == "Data sources: Garmin edge_1040 and other devices"


def test_stryd_base_with_garmin_donor_adds_other_devices() -> None:
    line = attribution_line(_base(_stryd()), [(_garmin("edge_1040"),)])
    assert line == "Data sources: Garmin edge_1040 and other devices"


def test_donor_recording_device_rule_applies_to_a_donor_tuple() -> None:
    donor = (_garmin("fr965", index=1), _stryd())
    line = attribution_line(_base(_garmin("edge_1040")), [donor])
    assert line == "Data sources: Garmin edge_1040 and other devices"


def test_empty_donor_tuple_adds_other_devices() -> None:
    line = attribution_line(_base(_garmin("edge_1040")), [()])
    assert line == "Data sources: Garmin edge_1040 and other devices"


def test_donor_with_leading_index_one_non_garmin_attributes_its_garmin_recorder() -> (
    None
):
    donor = (_stryd(index=1), _garmin("fr965"))
    assert donor[0].device_index != 0
    recorder = recording_device(donor)
    assert recorder is not None and recorder.manufacturer == "garmin"
    line = attribution_line(_base(_garmin("edge_1040")), [donor])
    assert line == "Data sources: Garmin edge_1040 and Garmin fr965"


def test_a_repeated_label_keeps_its_first_position() -> None:
    donors = [(_garmin("fr965"),), (_garmin("edge_1040"),)]
    line = attribution_line(_base(_garmin("edge_1040")), donors)
    assert line == "Data sources: Garmin edge_1040 and Garmin fr965"


_OTHERS = "Data sources: Garmin edge_1040 and other devices"
_BOTH = "Data sources: Garmin edge_1040 and Garmin fr965"


def _with_donors(*donors: tuple[DeviceInfo, ...]) -> str | None:
    return attribution_line(_base(_garmin("edge_1040")), list(donors))


def test_donor_with_non_garmin_first_index_zero_device_adds_other_devices() -> None:
    donor = (_stryd(), _garmin("fr965"))
    assert [d.device_index for d in donor] == [0, 0]
    assert _with_donors(donor) == _OTHERS


def test_donor_with_garmin_first_index_zero_device_is_attributed() -> None:
    donor = (_garmin("fr965"), _stryd())
    assert [d.device_index for d in donor] == [0, 0]
    assert _with_donors(donor) == _BOTH


def test_donor_with_only_an_index_one_garmin_adds_other_devices() -> None:
    assert _with_donors((_garmin("fr965", index=1),)) == _OTHERS


def test_donor_garmin_device_with_absent_index_adds_other_devices() -> None:
    donor = (_dev(None, "garmin", "fr965"),)
    assert donor[0].device_index is None
    assert _with_donors(donor) == _OTHERS


def test_label_repeated_between_donors_keeps_first_position_once() -> None:
    line = _with_donors((_garmin("fr965"),), (_garmin("hrm_pro"),), (_garmin("fr965"),))
    assert line == "Data sources: Garmin edge_1040, Garmin fr965 and Garmin hrm_pro"


def test_labels_keep_base_first_order_not_alphabetical() -> None:
    line = attribution_line(_base(_garmin("fr965")), [(_garmin("edge_1040"),)])
    assert line == "Data sources: Garmin fr965 and Garmin edge_1040"


def test_three_models_read_as_a_comma_list_with_a_final_and() -> None:
    line = attribution_line(_base(_garmin("C3")), [(_garmin("A1"),), (_garmin("B2"),)])
    assert line == "Data sources: Garmin C3, Garmin A1 and Garmin B2"


def test_three_labels_and_others_read_as_a_list_ending_in_other_devices() -> None:
    line = attribution_line(
        _base(_garmin("C3")), [(_garmin("A1"),), (_stryd(),), (_garmin("B2"),)]
    )
    assert line == "Data sources: Garmin C3, Garmin A1, Garmin B2 and other devices"


def test_donor_repeating_the_base_model_gives_one_label() -> None:
    line = attribution_line(_base(_garmin("edge_1040")), [(_garmin("edge_1040"),)])
    assert line == "Data source: Garmin edge_1040"


def test_labels_deduplicate_after_normalisation() -> None:
    line = attribution_line(_base(_garmin("Edge 1040")), [(_garmin("Edge\n1040"),)])
    assert line == "Data source: Garmin Edge 1040"


def test_repeated_label_with_other_contributor_keeps_one_label() -> None:
    line = attribution_line(
        _base(_garmin("edge_1040")), [(_garmin("edge_1040"),), (_stryd(),)]
    )
    assert line == "Data sources: Garmin edge_1040 and other devices"


def test_no_garmin_contributor_anywhere_gives_no_line() -> None:
    assert attribution_line(_base(_stryd()), [(_stryd(),), ()]) is None


def test_same_inputs_give_the_same_line() -> None:
    base = _base(_garmin("fr965"))
    donors = [(_garmin("edge_1040"),), (_stryd(),)]
    first = attribution_line(base, donors)
    assert first is not None
    assert attribution_line(base, donors) == first
    assert attribution_line(base, tuple(donors)) == first


# imports --------------------------------------------------------------------


def test_module_imports_nothing_from_fitdocs_but_the_model() -> None:
    path = Path(attribution.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import hides its target"
            assert node.module is not None
            targets.add(node.module)
    fitdocs_targets = {t for t in targets if t.split(".")[0] == "fitdocs"}
    assert targets, "the walk found no imports; it is looking at the wrong module"
    assert fitdocs_targets == {"fitdocs.model"}
