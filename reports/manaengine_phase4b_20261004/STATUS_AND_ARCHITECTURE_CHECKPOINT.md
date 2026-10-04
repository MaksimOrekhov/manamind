# Phase 4B: H6 completion and damage-timing review checkpoint

Baseline: `84130657f303622b52a096a1129a1eb265a48751`, branch `codex/manaengine-first-deck`, initially clean. RosettaStone remains reference backend, pinned at `f34da0d3fcb5ad312f7e2acf634d0536b044d29a`.
First recorded active timer: 2026-10-04 10:29:17 UTC. Hard limit: four active hours or earlier architecture/rules stop. No training/search/backend switch or user-response waiting.

## H6 complete

Policy action features now include `card_spell_damage`, `choice_card_cost` and explicit presence flags. Known zero differs from missing/negative sentinel values. Prepare/Shatter/Choice/targeting/effective-cost features remain distinct; transient entity handles are ignored. Policy action schema is explicitly version 2, saved by the existing checkpoint producer. Name-based legacy migration retains old columns, zero-initializes new ones and reports migration; unknown future versions fail. Fast loading also checks state feature names.

Tests cover +0/+1 per-card Spell Damage, Choice effective-cost differences, missing values, ignored handles, eight existing action distinctions and schema migration. Real Kalec -> Fireball adapter actions assert different Policy rows. A legacy fixture was corrected to exclude newly added features from its old feature list. Initial focused run: 24 PASS / 1 fixture failure; corrected: 25 PASS. One fixture correction, no native implementation change or new declaration.

## Stop: reviewed damage timing is unsettled

Current `resolve_spell` snapshots `spell_damage_for(owner)` once and passes it into all `resolve_effects` instructions. Old native source-death assertions describe this prototype model, not independent Hearthstone truth; the prior correctness audit already records the limitation.

Pinned END_022 is an undamaged 1/3 Time-Twisted Seer with +2 Spell Damage while damaged. Pinned CATA_485 first deals 2 targeted damage, then 1 to a random enemy minion. Targeting one's own undamaged Seer leaves it at 1 Health and activates the aura. The second hit distinguishes cast snapshot (1) from refreshed aura evaluation (3).

[A first-person forum account](https://us.forums.blizzard.com/en/hearthstone/t/my-initial-thoughts-on-kalec-mage/158738/13) specifically reports a second hit of 3 in this combination. It is a reported observation, not official comprehensive rules or replay proof. It challenges the snapshot assumption but cannot certify all death/target-selection timing.

Pinned Rosetta `Generic::TakeDamageToCharacter` reads current Spell Power on each invocation. `ConsecutiveDamageTask` also calls `ProcessDestroyAndUpdateAura` between iterations. Generic helpers and the unverified generated Sleet Storm route cannot be an unquestioned oracle for exact historical rules. CATA_485 is canonical IMPLEMENTED_UNVERIFIED; no TIME_855 CardSet implementation was found.

Further unresolved choices: when Barrage chooses its two distinct targets relative to the first hit; when mandatory death processing affects that pool; when aura refresh happens relative to damage/reactions. Card text establishes amounts/exclusion/distinctness, not the complete timing. No decisive reviewed game trace was found.

### Architecture options

| Option | Change | Tradeoff |
|---|---|---|
| Local versioned damage-boundary contract | Shared ordered composition with explicit instruction/group boundaries; re-evaluate aura at reviewed boundaries, retain cast-instance bonus separately. | Recommended next design direction. Seer can be handled without a global rewrite, but death/sampling boundaries still need evidence. |
| Global effect/death continuation model | Typed spell continuation and explicit reaction/death checkpoints; re-review old multi-step consumers. | More complete, materially changes core ordering/continuation; requires architecture review. |
| Keep snapshot and partial routes | Development routes with fail-closed ambiguous cases. | Does not close the requested exact environment; not used to claim progress/DECK_READY. |

Recommendation is not an implemented decision. Blindly calling `stabilize()` between instructions can drain unrelated queued Battlecries/after-play Secrets and alter terminal/death ordering. No such change was made. Stop follows Phase 4B section 17 exact-rules/core-ordering conditions, not workload/pool cardinality. Later packages B-E were not started after the stop condition.

## Exact progress

- Frozen deck unchanged: 17 roots / 30 slots. New implemented/closed roots: 0; new dependency outcomes closed: 0; new native capability families: 0. H6 action gap closed.
- Six main missing roots: CATA_485, TIME_855, CATA_452, TLC_226, CATA_488, CATA_484.
- IMPLEMENTED_BUT_RULES_BLOCKED: CATA_489, JAIL_321, CATA_487 and partial Secret/transform/ordering paths recorded in the correctness audit. No statuses promoted.
- Whelp runtime manifest/transitive audit not reached. Historical 77 is provisional, not reviewed membership. Exact remaining pool/dependency sizes: UNKNOWN, not zero.
- No 1000-match validation/performance claim: deck closure remains incomplete. Synthetic matches do not establish the frozen deck.
- Canonical evidence/closure/training counts are unchanged unless real fingerprint regeneration invalidates evidence. No manual PASS.
- Root throughput is zero for this bounded cleanup/design checkpoint, not an estimate of future card implementation rate.

Local/hosted checks and elapsed intervals will be recorded in `H6_VERIFICATION_COMPLETION.md`. Verdict: `ARCHITECTURE_REVIEW_REQUIRED`, not DECK_READY. Preserve and push this work, then stop for a reviewed damage-boundary contract and decisive independent expectations.
