# Spellweaver's Brilliance — Completion Record

package_id: direct_spell_damage_turn_cost_fixed_summon_v1
contract_version: 1
baseline: 28baac6fe21bd1715e1c2c670f01502572474f14
branch: codex/manaengine-first-deck
RosettaStone: f34da0d3fcb5ad312f7e2acf634d0536b044d29a (unchanged)
implementation_status: CATA_452 IMPLEMENTED_SCOPED_VERIFIED in ManaEngine; canonical RosettaStone evidence unchanged

## Root and exact dependency

CATA_452 is one production declaration-only consumer: base cost 10, spell_damage_cost_reduction coefficient 1, SUMMON_FIXED(Self, count 1, CATA_452t). No card-ID behavior branch or CUSTOM implementation. A separate test-only declaration varies base cost/coefficient/count/dependency using the same implementation.

CATA_452t is Azure Warden, dbfId 122455, Mage MINION/DRAGON, 6 cost, 6 attack, 6 health, noncollectible; no text or mechanics. It is declared through the reviewed vanilla guard, with a new finite metadata archive at experiments/manaengine/data/fixed_summon_dependency_metadata.json. Old archives, Standard membership and frozen decklists are preserved.

Read-only canonical verification actually asserted full-feed CATA_452 equals the pinned Oct1 root, full-feed CATA_452t equals the new archive and complete-response SHA matches the archive. Feed SHA-256: e8ea569a7ca1790c2258ed57c60798d808ffb057acb7bb73663c00ea174dae65. Token normalized metadata SHA-256 (sorted compact UTF-8 JSON): 3ce8e1c928a603290c33209ae0abf22e81943c8d4fbe25719000a937b4df1ac8. Metadata identity is not by itself rules evidence.

## Damage accounting / cost contract

Explicit DamageAttribution::DirectSpell is required; DamageKind::Spell alone is insufficient. Only full successful packet amounts update a saturating 64-bit controller counter. Shield/Immune give zero; Armor still counts; overkill counts the full unprevented amount. Combat, minion effects, hero power, fatigue and ExternalSpellEffect give zero. No Skeleton Key implementation or unsupported custom source was added.

Ordinary spell Damage, composed spell steps, missile unit packets and actual Explosive Runes damage explicitly qualify. The existing Flames of Infinity destroy-via-damage placeholder does not qualify as direct damage; its broader historical limitations are not repaired or certified by this package. Raincaller remains an independent once-per-turn event consumer.

Both counters reset at GLOBAL turn rotation after end-turn reactions, before next draw. Tests credit off-turn Runes damage to its controller and then demonstrate cost returning to 10 at the next own turn. No global event/death ordering redesign.

The shared effective-cost path handles the per-damage coefficient without changing base metadata, with overflow-safe zero clamping. GameState hand current_cost and legal-action card_cost expose the result, and existing Policy card_cost encoding distinguishes 4 from 10. No public state field, encoder feature, observation schema or Policy checkpoint schema changes. The internal counter is cloned; changing one branch leaves its sibling's effective costs unchanged.

Fixed summon creates the exact normal owned instance, board position and activation, with summoning sickness. At full capacity the SPELL is still legal/consumed; no extra token entity, burned token, graveyard token or death event is created. Unknown/unsupported dependencies, invalid count/selector/field combinations and minion cost-coefficient misuse fail closed.

## Actual verification and corrections

| Check | Observed local result |
|---|---|
| Full Debug native suite | 32 scenario groups / 601 assertions passed (baseline 31 / 567) |
| Adapter/pipeline/Policy suite | 43 passed in 33.48s |
| Full Python suite | 88 passed in 10.96s |
| Ruff, no cache | All checks passed |
| Generic identity guard | PASS, same 201 reviewed exceptions |
| Canonical regeneration | 36 pinned outputs reproduced, no delta on first run |
| Whitespace | git diff --check passed |

One core/binding/test rebuild in the existing configured Debug build %TEMP%/ManaEngineCorrectnessBuild; native passed on its first run. Adapter explicitly loaded that rebuilt extension through MANAMIND_MANAENGINE_BUILD. First adapter run: 41 passed / 2 failed; one correction cycle fixed ONLY new fixture assumptions about the existing Python API (untargeted action omits target_entity_id; BoardEntity stores metadata under card). Second complete run passed all 43. No existing regression was waived or reclassified as baseline. The independent metadata comparison initially required explicit UTF-8 decoding and then passed; no source identity was copied or guessed.

Reproduce using the existing ManaEngine CI build instructions and native CTest/executable; then PYTHONPATH=src and MANAMIND_MANAENGINE_BUILD=<build>/python for `python -m pytest -q -p no:cacheprovider experiments/manaengine/tests/test_adapter.py tests/test_pipeline.py tests/test_policy_action_semantics.py`. Run full pytest, Ruff, generic guard and check_generated_artifacts separately. Hosted CI will independently build Release on Windows/Ubuntu and actual jobs/logs will be saved in SPELLWEAVER_CI_EVIDENCE.json.

Shared implementation changes: C++ header/core/bindings add 56 physical lines/remove 14; Python adapter adds 12/removes 8 (allowlist/dependency loading). Physical counts include editing existing minified lines and do not quantify complexity. Two shared contracts delivered: direct-spell global-turn cost accounting and fixed summon. One production root, one exact token, one independent test consumer; zero CUSTOM consumers.

## Closure, limitations and remaining roots

New experimental route: one root (two frozen slots) plus one verified fixed dependency edge/token. Canonical RosettaStone verified-root/evidence/closure delta remains zero; generated outputs reproduce unchanged. No dynamic pool was narrowed. No deck readiness, Standard-wide correctness, training/search or backend switch follows from this package.

Remaining wholly unimplemented frozen Mage roots: TIME_855 Arcane Barrage (2 slots), TLC_226 Conjured Bookkeeper (2), CATA_488 Vulcanos (1), CATA_484 Winterspring Whelp (2): four roots / seven slots. CATA_485 Sleet Storm is implemented but partial at mortality/selection boundaries. Existing Arcane Flow/Shatter, Tricksy Improviser/Secrets, Raincaller and dependency/event limitations remain as documented; implementation presence is not complete closure. Frozen deck remains 17 roots / 30 slots, not DECK_READY.

Timer start: 2026-10-04 11:34:30 UTC. Review, identity resolution, proposal, implementation and local checks through 11:50:10 UTC took 15m40s observed elapsed, with no user-response wait. Report/commit/hosted acceptance time will be recorded separately. This is observed wall-clock task time, not sampled CPU time or a future throughput estimate.

STOP after push and green Windows/Ubuntu Source/ManaEngine CI. Do not implement another root or start training/search before the next explicit user instruction.

## Hosted acceptance

Implementation commit d01ffde3c292e3fa03322bf35126875e28c20269: [Source CI](https://github.com/MaksimOrekhov/manamind/actions/runs/37200195427) green on Windows and Ubuntu, both reproduced all 36 outputs and actually ran 88 Python tests (7.22s Windows / 10.93s Ubuntu). [ManaEngine CI](https://github.com/MaksimOrekhov/manamind/actions/runs/37200195447) green on both OSes: fresh Release build, native CTest (1.95s Windows / 0.82s Ubuntu) and all 43 adapter/policy tests (19.37s / 14.03s).

SPELLWEAVER_CI_EVIDENCE.json contains actual completed job steps, fetched log excerpts and computed source identities. Acceptance was observed at 2026-10-04 11:57:30 UTC. Report, identity recheck, commit/push and hosted acceptance added 7m20s after the local interval; total through hosted implementation acceptance is 23m00s observed elapsed, including CI wait. Final evidence-only commit changes no engine/adapter/test source; its workflows are checked again before stopping.
