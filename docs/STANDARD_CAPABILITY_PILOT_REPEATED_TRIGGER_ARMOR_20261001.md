# Capability pilot 3: repeated-trigger armor extension

Date: 2026-10-01  
Registry snapshot: `standard_registry_20261001_v1`  
Status: **completed as scoped extension; not training-ready**

## Hypothesis

The second pilot's repeated Battlecry/Deathrattle declaration can cover another fixed effect without adding a new activation model. Underking (`CORE_RLK_657`) gains 6 Armor on both events; Rush continues to come from pinned card metadata.

## Change and validation

- Added Underking to the existing strict allowlist using `ARMOR_SELF_6`; the generated CardDef emits `ArmorTask(6)` in both task lists.
- The independent scenario checks +6 Armor on play and a further +6 after death. The Death Knight draw cards remain covered by their previous tests.
- Combined package suite: 4 cases, 34 assertions passed; 2,520 unrelated tests skipped.
- Bridge smoke: Druid Standard deck validation, session, visible hand and legal-action enumeration passed for Underking.
- The generator initially rejected the catalog's `[x]` display marker; normalized validation was updated to remove that marker. The native scenario caught an emitted amount of 1 where 6 was required; the effect-to-task mapping was corrected. These are two distinct correction cycles.
- The successful focused incremental C++ build/link took about **6.7 sec**. Full authoring/review elapsed time and bridge relink time were not separately timed.
- One card definition is generated; no card-specific native handler was added.

## Current registry impact

This extends the repeated-trigger generator to three roots total: Prize Vendor, Chillfallen Baron and Underking. All three now have current `VERIFIED_SCOPED` rules evidence. Across the whole Standard registry, six roots are currently `VERIFIED_SCOPED`; generated registrations total 30. No root has verified full dependency closure or training eligibility. Full-pool admission stays **BLOCKED**.

The scoped evidence covers these event/effect cases only. It does not prove complete Rush interactions, all death processing, draw-pool closure, deck/session readiness, or the complete Standard rules surface.
