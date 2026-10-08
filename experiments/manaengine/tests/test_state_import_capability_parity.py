"""ENGINE-STATE-IMPORT-0: the diagnostic capability view must agree with the native catalog it describes.

The readiness diagnostic derives "which cards ManaEngine can execute" from declarations in Python (no native build, so
Source CI can run it). This test, which needs the built module, is the check that the Python derivation and the real
native catalog (`_definition_rows`, with the engine's own text and dependency guards applied) never drift apart.
"""
from __future__ import annotations

from manamind.integrations.manaengine.engine import _definition_rows
from manamind.integrations.manaengine.state_import_capability import CapabilityIndex


def test_capability_index_matches_native_support_state_for_every_record():
    native = {row.card_id: row.support_state for row in _definition_rows()}
    index = CapabilityIndex()
    derived = {card_id: ("UNSUPPORTED" if not index.card(card_id).supported else index.card(card_id).declared_state)
               for card_id in native}
    assert derived == native
    assert {row.card_id for row in _definition_rows() if row.support_state != "UNSUPPORTED" and row.card_type == "HERO_POWER"} == set(
        index.supported_hero_power_ids)
