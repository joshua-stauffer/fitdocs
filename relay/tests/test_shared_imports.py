"""The relay can import its pinned copies of the shared modules."""

from __future__ import annotations

from fitdocs_relay.shared import relay_codes, relay_envelope


def test_the_envelope_copy_resolves_its_sibling_import() -> None:
    # relay_envelope does `from .relay_codes import RELAY_CODES, ...`; that must
    # bind to the sibling copy inside fitdocs_relay.shared, not to fitdocs.
    assert vars(relay_envelope)["RELAY_CODES"] is relay_codes.RELAY_CODES
    assert relay_envelope.__name__ == "fitdocs_relay.shared.relay_envelope"
    assert relay_codes.__name__ == "fitdocs_relay.shared.relay_codes"


def test_the_copies_carry_a_real_vocabulary() -> None:
    assert len(relay_codes.RELAY_CODES) >= 22
    assert relay_envelope.is_target_id.__module__ == relay_envelope.__name__
