# Completion: `manaengine_overload_turn_lock_v1`

- Roots: `CORE_EX1_238` Lightning Bolt and `CORE_BOT_451` Voltaic Burst.
- Shared contract: a directly played, non-countered spell records its printed Overload amount after spell resolution. On the owner's next turn start, the engine grows max crystals, transfers pending to current locked crystals, clears pending, and refills only unlocked crystals. Multiple spells add. Counterspell prevents the text phase and therefore prevents Overload.
- Declaration-only consumers: 2/2. Lightning Bolt uses existing target damage. Voltaic Burst uses existing fixed summon plus exact `BOT_102t` Spark metadata. No card-ID behavior branches.
- Shared implementation: internal current/pending mana counters; generic play and turn-start transitions; pinned Overload amount import; public observation mapping through already-existing `PlayerObservation.overloaded_mana` and `pending_overload`; exact token definition; declarations.
- CUSTOM/deferred outliers: none among the two roots. Package bounds are direct-play spells and exact reviewed consumers. Overload minions, unlock effects, temporary mana crystals and special overflow interactions remain unsupported.
- Native: PASS, 43 scenario groups / 722 assertions. Tests cover each consumer, stacking, turn transition, locked amount, refilling on the next own turn and Counterspell.
- Adapter/action: PASS, full adapter file 25 passed. Public pending/current values cross the adapter, legal action vectors encode, and two Rush Sparks appear.
- Correction cycles: 2 (missing vanilla support declaration for token; test helper initially discarded the returned observation).
- Build attempts: 1; final build and native suite passed.
- Observed elapsed: 13m51s from proposal at 16:29 UTC to adapter verification at 16:42:51 UTC.
- Schema: no change; both mana fields already exist in the shared observation model and encoder.
- Rules evidence: [Blizzard Core Card Library](https://hearthstone.blizzard.com/en-us/cards?set=core&viewMode=table) for the Core cards; current Overload timing and Counterspell interaction cross-checked against the [Overload rules reference](https://hearthstone.wiki.gg/wiki/Overload-generating). Counterspell ordering is secondary rules evidence, not canonical rules proof. No card-specific client replay captured.
- Canonical registry/evidence: not regenerated or promoted. `IMPLEMENTED_SCOPED_VERIFIED` is task-local ManaEngine status only; no RosettaStone, bridge, pool-closure or training status is implied.
