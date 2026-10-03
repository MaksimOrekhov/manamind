# Phase 3 package A completion — held spell threshold transform

Package: shaman_spell_threshold_hand_transform_v1  
Contract: held_spell_threshold_transform_v1  
Completed: 2026-10-03  
Branch baseline: 550da819b7e21f26e2e5fccca526b303ded15d74  
Rosetta data revision: f34da0d3fcb5ad312f7e2acf634d0536b044d29a

## Completion record

| Field | Result |
|---|---|
| Elapsed time | 26 minutes from candidate-audit start (18:11 UTC) through passing native and adapter tests (18:37 UTC), measured by the worktree edit/test timestamps. |
| Candidate cards | JAIL_801 Molten Gold → JAIL_801t; JAIL_803 Frostshatter → JAIL_803t; JAIL_805 Stormfury → JAIL_805t. These are three real wanted_mug_shaman profile roots, six deck slots. |
| Declaration-only consumers | 3/3. Threshold, transform target, stats, target selectors, Battlecry effects and Lifesteal are declarative. No card-ID behavioral branch was added. |
| CUSTOM / deferred outliers | None among the three selected consumers. Internal replay/auto/nested spell-resolution paths remain outside this prototype contract and fail closed because the engine has no supported path that resolves them internally. Hand-copy/bounce semantics remain unsupported. |
| Shared Python changes | CardDefinition adapter fields for threshold/target/Lifesteal; fixed token metadata for all three generated minions; declared enemy-character selector and effect-level Lifesteal. |
| Shared C++ changes | Per-hand-instance spell event increment and declared transform; generic typed Battlecry effect dispatch; enemy-only character legality; damage dealt accounting for minion Lifesteal; Divine Shield damage interaction; Lifesteal minion observation and combat. No global event order change. |
| Correction cycles | 4 focused corrections: missing loop brace found by first build; native test expectation corrected for one-card draw; post-play instance index corrected; adapter test advanced to a turn with sufficient mana before playing the token. |
| Native scenarios / assertions | 21 scenario groups, 369 assertions passed. New real-root scenarios cover all three root/token pairs, progress 1→2→3, pre-resolution transform, new later copy at zero, per-instance and clone divergence, action/type export, Battlecry target legality, damage/draw/freeze, Divine Shield, AOE Lifesteal and combat Lifesteal. |
| Python adapter checks | experiments/manaengine/tests/test_adapter.py and tests/test_pipeline.py: 21 passed. The new adapter scenario observes the actual profile root, its transformed token, legal Battlecry action and four-damage result. |
| Registry / closure delta | 0. Canonical Standard registry and Meta Profile evidence were not edited or promoted. Prototype-only evidence: +3 reviewed candidate roots / +6 deck slots exercised; dependency closure gain 0; training eligibility gain 0. |
| Profile effect | One frozen deck advanced from 3 unsupported roots to 3 prototype-supported roots; it remains blocked by its other unsupported roots and dependencies. |

## Semantic boundary

The count observes the active player's spell PlayCard action from hand, after that played card leaves hand and before its effect resolves. Generated cards played from hand count. Opponent spells and internal spell resolutions without that action do not count. Transform preserves the hand entity ID and position, swaps to the fixed token definition and clears the counter. A card drawn by the third spell's effect starts at zero. This is prototype evidence for the reviewed bounded event contract, not proof of all Hearthstone spell-cast paths or canonical Standard verification.

## Independent effect checks

The tests assert the transformed tokens' actual effects independently of Rosetta parity: Molten Gold Elemental targets a character for four; Frostshatter Elemental offers enemy character targets only, freezes the chosen enemy and draws two; Stormfury Elemental damages each enemy minion, consumes Divine Shield without healing for shielded damage, and restores health for damage dealt. Its Lifesteal keyword is visible and also heals during minion combat.

No training, deck readiness or production migration is claimed.
