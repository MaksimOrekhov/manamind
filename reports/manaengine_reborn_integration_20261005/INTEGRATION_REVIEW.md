# Intrinsic Reborn v1 integration review and capability proposal

Baseline: `adbbc62edd664268ba30a4b267f2d3495bb49651`. Reference inspected with `git show`: `a35ddc6f0b0bd736d6a3b30e2a31884e39204cc1` (`claude/reborn-prototype`). No merge or cherry-pick.

## CAPABILITY PACKAGE PROPOSAL

- **package_id:** `intrinsic_reborn_v1`.
- **semantic capability:** one fresh intrinsic minion returns with current Health 1 after its batch Deathrattles; intrinsic max Health/stats/keywords restored, active Reborn consumed, arbitrary instance modifiers reset.
- **existing primitives:** CardDefinition/CardInstance, make_instance, death batch, FIFO Deathrattle queue, activation_sequence, board positions, UnsupportedSimulationError, EvidenceConstraint, domain Reborn feature/schema 16, admission gate.
- **reviewed candidate:** `CORE_ULD_723` Murmy. Independent synthetic declarations vary Rush/Taunt/Lifesteal and existing draw Deathrattle. No additional real roots enabled.
- **dependencies:** no generated card/dynamic pool. Cross-side order is currently inert: separate boards have no reviewed on-summon reactions.
- **required shared changes:** intrinsic/active flags; minimal death snapshot; sequential current-slot removal; Deathrattles before returns; board mutation guard; observation transport; stable evidence ID/domain validation.
- **expected unlocks:** one ManaEngine consumer; zero canonical verified-root/closure/training promotion.
- **test strategy:** single/multiple deaths and activation-order variations; combat/spell/effect lethals; reset/identity/second death; Silence/Transform/copy; Rush/clone/terminal; Deathrattle trace order; board mutation fail closed; constraint granularity/serialization/admission/feature isolation; all earlier regressions.
- **custom outliers:** none implemented. Granted/full-enchantment Reborn (`EDR_100t9`, `CAP_800`), board-changing Deathrattles and on-summon ordering remain unsupported.

## Integration mapping

| Claude component | Disposition | Mainline integration |
|---|---|---|
| Definition/instance flags | PORT | Intrinsic metadata and separately consumed live flag; minion-only validation |
| Fresh return at Health 1, reset modifiers | PORT | Current make_instance; new activation/entity, REBORN provenance |
| Minimal RebornPending | ADAPT | Current numeric slot recorded at sequential removal, no whole-instance copy |
| Pre-batch slots/original relative-order reconstruction | REJECT | Contradicted by follow-up; no survivor original-position keys |
| Deathrattle-before-Reborn phase | PORT | Current FIFO queue and local batch continuation |
| Survivor board guard | ADAPT | Snapshot survivor identity/card order after removals; reject unreviewed membership/mortality mutation |
| Multi-death evidence note | ADAPT | Typed constraint in Phase 4E.2 infrastructure |
| Prototype evidence/admission | SUPERSEDED | Current session debt, serialization and canonical gate |
| Reborn board observation | ADAPT | Existing domain feature/schema 16; no pending state exposure |
| Prototype tests | ADAPT | Replace relative-order expectations; retain Phase 4F/Dark Gift tests |

## Timing and evidence

Identify dead handles and stable-sort by activation sequence. Locate each handle on its CURRENT board, capture current numeric position, remove it, queue ordinary Deathrattle/minimal Reborn snapshot and move the original to graveyard. Capture survivor identities after removal, drain batch Deathrattles FIFO, then reject unreviewed board mutation/new mortality before processing returns. Insert returns in activation order at recorded positions clamped to current board size.

This is the user's reviewed sequential-removal model. The pinned Claude follow-up reports historical client evidence and explicitly leaves multi-death current-client correctness unresolved. Its original relative-order implementation is rejected. No current-client replay is claimed.

[Blizzard's official announcement](https://hearthstone.blizzard.com/en-us/news/23037181) corroborates first return with 1 Health. Pinned metadata owns Murmy identity/intrinsic fields. Historical attribution: [Jetz72 log](https://gist.github.com/Jetz72/6b60de57d22d901161861d71cf4bdaac), [client forum report](https://us.forums.blizzard.com/en/hearthstone/t/teleporting-reborn-minions/13808), and the locally retained [REBORN_RULES_EVIDENCE.md](REBORN_RULES_EVIDENCE.md). The historical URLs were not independently re-fetched during consolidation; no evidence status is upgraded.

Single same-side death uses the strongly corroborated slot model without new debt. A batch with >=2 deaths on one side and an active unsilenced Reborn return on THAT side remains mechanically valid but records `REBORN_MULTI_DEATH_SLOT_UNVERIFIED`; canonical admission independently rejects debt. Opposite-side single deaths and batches without Reborn do not trigger it. Clone preserves debt and does not contaminate an earlier clean branch.

Cross-side order is deferred without another constraint today. Order-sensitive summon reactions require review later. Board-fill/board-changing death-phase paths fail closed; the scheduler is not generalized. Control-changed Reborn sources fail closed under the bounded owner/controller contract.

## State and admission boundary

Returned instances use definition Attack/max Health/intrinsic Taunt/Lifesteal/Rush, current Health 1, fresh entity/activation, REBORN provenance and summoning sickness (intrinsic Rush can attack minions). Counters, damage, cost_delta, Prepare, spell_damage_bonus, Dark Gift grants, temporary keywords and enchantments are not copied. Silence prevents return; Transform uses the replacement's intrinsic definition. INSTANCE_COPY_V1 rejects active and intrinsically Reborn sources without broadening its contract.

Expose active unsilenced Reborn on both boards only. Schema 16 and Policy v3 retain their meanings. Domain evidence-ID changes may change observation source identity; regenerate honestly without manual evidence promotion. Debt stays outside gameplay features. Persisting Horror remains selectable unsupported and invalidates its branch.
