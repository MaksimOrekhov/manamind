# Verification harvest — 2026-10-03, batch 2

## Scope and result

This batch continued the prioritized candidates from the current low-hanging verification report. It stopped after three successful clean verification packages, as requested. No new production engine code or declarations were added. The two C++ additions were focused native test cases only.

| Package | Roots newly scoped-verified | Native result | Bridge result | Observed elapsed | Production changes |
|---|---:|---|---|---:|---:|
| `cost_discount_expiry_verification_v1` | 2 (`CORE_EX1_145`, `CORE_BT_416`) | 2 cases / 28 assertions passed | Preparation next-spell consumption + turn-end expiry; Felscreamer Demon-only filter + first-Demon consumption | 798.898 s | 0 |
| `spider_rider_hero_attack_draw_verification_v1` | 1 (`JAIL_872`) | 1 focused case / 3 assertions passed | Existing bridge scenario passed: hero attack drew exactly one card | 295.115 s | 0 |
| `end_turn_enemy_damage_verification_v1` | 2 (`CATA_999`, `CATA_475`) | 2 cases / 11 assertions passed | Both roots caused expected damage only at their controller's turn end | 342.877 s | 0 |

Successful packages added **5 current Meta Profile scoped-verified roots** in **1,436.890 seconds total** (23 min 56.890 s), averaging **1.67 roots per package** and **478.963 seconds per package**. They added no dependency-closure edges and no training-eligible roots. `CATA_999` and `CATA_475` share the turn-end verification boundary; this does not claim a shared implementation capability.

Spider Rider and CATA_999 required two focused test-only scenarios in `ManaMindEffectCompositionTests.cpp`, followed by one `UnitTests` rebuild. Because that changed the native binary hash, current scoped evidence for the earlier profile packages was replayed against the final binary identity: Core aliases (3 roots), minion-cost/summon (2), targeted damage/hero attack (2), and single-target/enemy-board spell damage (6). Those refreshes passed. The measured `end_turn_enemy_damage` duration includes the artifact identity refresh needed after the test-only rebuild.

The shared manifest/evidence rebind at batch start was separately measured at **235.755 seconds**. It is not included in the package average.

## Deferred candidates

| Candidate | Observed elapsed | Findings | Result |
|---|---:|---|---|
| Power Word: Shield / Haunt | 366.029 s | Both focused native cases passed (4 + 15 assertions). PWS friendly-target bridge case passed, but no legal enemy-minion action was exposed even though the source has no friendly-only requirement. The family cannot be marked verified until target-side parity is explained. | Deferred; no evidence promoted |
| Royal Librarian | 262.545 s | Base and composition native cases passed (4 + 4 assertions). The configured bridge’s free-minion assumption failed; a deterministic follow-up with a supported friendly minion still did not expose a `PLAY_CARD` action for Librarian. | Deferred; no evidence promoted |

The next ranked candidates, Gravedawn Sunbloom / The Unseen Atlas, were not attempted: the three-success limit had been reached. These findings are preserved in [the Priest proposal](../../docs/proposals/20261003_priest_minion_enchant_verification_v1.md) and [the Royal Librarian proposal](../../docs/proposals/20261003_royal_librarian_verification_v1.md).

## Profile checkpoint

- Meta Profile current scoped-verified roots: **18 of 156**, up from 13 before this batch.
- Canonical Standard current verified roots: **3**; scoped Meta evidence does not upgrade canonical Standard evidence.
- Fully closed Meta decks: **0**. Training eligibility gained: **0**.
- Registry root/dependency delta and reviewed closure delta: **0**.
- Production engine changes: **0**. Test-only native additions: **2**. CUSTOM outliers added: **0**.

Evidence is in `integrations/rosettastone/card_rules/profile_verification_harvest_20261003_v2.evidence.json`. Each completed package has a `time.perf_counter_ns()` observed duration and an individual proposal/completion record.
