# INSTANCE_COPY_V1 — final review checkpoint

**Subsequent user decision:** the review below was accepted with a phase-model clarification: Kindred resolves after original entry and before After Play Secrets; Explosive Runes targets the original after the copy exists. Evidence status is RULES_REVIEWED_FROM_PHASE_MODEL, not DIRECT_REPLAY_VERIFIED. The historical MORE_RULES_EVIDENCE_REQUIRED verdict below is superseded for this explicitly scoped implementation. Field guards and Whelp-generated modifier blockers remain active. See BOOKKEEPER_COMPLETION.md for execution evidence; no actual Bookkeeper replay was captured.

Date: 2026-10-04
Scope: TLC_226 Conjured Bookkeeper in frozen tricky_burn_mage; design/audit only
ManaMind: 361fbd0013288de5d4106c65496ea4e2b6e2e6cf
RosettaStone reference: f34da0d3fcb5ad312f7e2acf634d0536b044d29a
Verdict: **MORE_RULES_EVIDENCE_REQUIRED**
Contract status: field/admission proposal complete; exact timing not established. This is not a finalized executable rules contract or permission to implement.

This review supersedes the unresolved copy alternatives in BOOKKEEPER_PROPOSAL_AND_RULES_REVIEW.md. A broad CardInstance redesign is not required for the proposed bounded state subset. The remaining blocker is rules evidence for a reachable timing interaction, not an architectural choice between a clean copy and a full rewrite.

## Evidence hierarchy and RULES ESTABLISHED

1. Pinned data/cards/source_snapshots/cards_collectible_20261001_enUS.json, SHA-256 d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930: TLC_226, Mage Elemental, 3 mana, 2 attack, 2 health, Deathrattle draw a spell, Kindred summon a copy of this. races=[ELEMENTAL]. mechanics=[DEATHRATTLE] does not exhaust the text contract.
2. [Blizzard's official copy rules](https://news.blizzard.com/en-gb/article/21965466/developer-insights-12-0-game-mechanics-update): copying between play zones retains enchantments; forward hand-to-play movement retains them too. CLEAN_BASE_COPY is therefore an incorrect general interpretation. This establishes retention, not the transfer semantics of arbitrary simulator bookkeeping fields.
3. [Blizzard's Kindred announcement](https://hearthstone.blizzard.com/en-us/news/24217084): matching minion type/spell school on the preceding own turn activates the bonus. Current/global opponent/two-turn-old history cannot substitute for it.
4. [Official card library](https://hearthstone.blizzard.com/en-gb/cards/117535-conjured-bookkeeper/) agrees with the pinned wording. It supplies no detailed timing or state-transfer specification.
5. [Blizzard's 36.0.2 hotfix announcement](https://us.forums.blizzard.com/en/hearthstone/t/3602-hotfix-patch/163357) removes extra Slagclaw Kindred activations caused by Battlecry doubling. Kindred cannot be treated as an ordinary repeatable Battlecry simply because our current engine has a Battlecry queue. This does not specify Bookkeeper's phase relative to Secrets.

The proposed source is the played original on the board at Kindred resolution, not its archived deck/hand/base definition and not its later graveyard record. This follows the play-triggered self-copy wording, the general copy rule and the reference implementation, but the precise snapshot instant remains an inference requiring confirmation for interfering reactions. Source lookup must use the original entity execution handle; searching by card ID could choose a sibling copy.

## RULES STILL UNKNOWN — do not invent defaults

- An authoritative Bookkeeper timing trace relative to summon reactions and an opposing Explosive Runes has not been found. The official sources above do not state that ordering. Battlecry ordering cannot establish Kindred ordering by analogy alone.
- Damage retention, Freeze expiry, silence, consumed Shield, temporary versus aura-derived stats, arbitrary counters and source-dependent enchantment lifetimes are not independently established here. Non-default occurrences are rejected by v1, not reset under a made-up rule.
- Copy placement relative to the source on a non-rightmost board position is not established. The proposed v1 admits only the current engine's rightmost played-source position; appending is then also immediately right of the source. Other positions require a separate reviewed contract.
- The complete recursively reachable state space through Winterspring Whelp is unresolved. Direct root inspection does not establish a closed dynamic dependency graph.

RosettaStone SummonCopyTask.cpp and Actions/Copy.cpp preserve internal attributes, applied enchantments and ongoing effects for appropriate source zones. They demonstrate an implementation pattern; they do not settle any of these unknown Hearthstone rules. The Thornmantle Musician / Crater Experiment [community report](https://us.forums.blizzard.com/en/hearthstone/t/thornmantle-musician-and-crater-experiment-ordering/153453) is a timing clue, not a rules oracle or reproducible Bookkeeper trace.

## INSTANCE_COPY_V1 field table

Exactly one policy is assigned to every current CardInstance member in engine.hpp. A FAIL_CLOSED field can retain its declared default only after the source guard succeeds. Defaults below are the scoped Bookkeeper contract, not a generic interpretation of all cards. A COPY assignment transfers a reviewed value explicitly; it does not imply acceptance of every possible source value.

| Current field | Policy | Allowed input and output contract |
|---|---|---|
| card_id | COPY | Copy the source's current supported minion identity. Consumer admission also requires unchanged played identity; transformed-source timing is excluded. No behavioral ID branch. |
| attack | COPY | Explicitly transfer source attack. Initial admitted subset requires attack equal to base attack; no ambiguous aura/modifier provenance. |
| health | COPY | Transfer current health explicitly only with zero damage, health=max_health>0. Never heal a damaged source silently. |
| max_health | COPY | Transfer max health; initial subset requires equality with base health. |
| cost_delta | FAIL_CLOSED_IF_PRESENT | Must be 0. Blanket retention/reset is unsafe without a scope/lifetime contract. |
| spell_damage_bonus | FAIL_CLOSED_IF_PRESENT | Must be 0; Kalec grants this only to spells, not Bookkeeper. |
| enchantments | FAIL_CLOSED_IF_PRESENT | Must be empty. Official retention rule is known, but string entries do not define effect ownership/expiry/rebinding. Reject rather than discard them. |
| counters | FAIL_CLOSED_IF_PRESENT | Must be empty, including keys with value 0. No copy/reset policy for untyped counters. |
| frozen | FAIL_CLOSED_IF_PRESENT | Must be false. |
| freeze_expire_owner_turn | FAIL_CLOSED_IF_PRESENT | Must be 0 even if frozen=false; inconsistent stale expiry is not admitted. |
| silenced | FAIL_CLOSED_IF_PRESENT | Must be false. Do not synthesize a working unsilenced Deathrattle from a silenced source. |
| divine_shield | FAIL_CLOSED_IF_PRESENT | Must be false; granted/consumed/intrinsic Shield distinction is outside this subset. |
| taunt | FAIL_CLOSED_IF_PRESENT | Must be false; effects/provenance are not inferred from a boolean. |
| lifesteal | FAIL_CLOSED_IF_PRESENT | Must be false. |
| immune | FAIL_CLOSED_IF_PRESENT | Must be false. |
| stealth | FAIL_CLOSED_IF_PRESENT | Must be false. |
| rush | FAIL_CLOSED_IF_PRESENT | Must be false. Charge/Rush copy is outside the Bookkeeper subset. |
| rush_only | FAIL_CLOSED_IF_PRESENT | Must be false. |
| shatter_original_card_id | FAIL_CLOSED_IF_PRESENT | Must be empty. |
| shatter_partner_entity_id | FAIL_CLOSED_IF_PRESENT | Must be -1. Never duplicate/rebind linked hand identities speculatively. |
| shatter_fragment | FAIL_CLOSED_IF_PRESENT | Must be None. |
| shatter_consumed | FAIL_CLOSED_IF_PRESENT | Must be false. |
| prepare_locked_turn | FAIL_CLOSED_IF_PRESENT | Must be -1. Prepare cost/lock state is not a copy policy. |
| durability | FAIL_CLOSED_IF_PRESENT | Must be 0; weapons are excluded. |
| current_durability | FAIL_CLOSED_IF_PRESENT | Must be 0. |
| entity_id | NEW_IDENTITY | Allocate a unique engine handle only when the summon succeeds. Never duplicate the source handle. |
| activation_sequence | NEW_IDENTITY | Fresh monotonic summon activation. Never inherit old trigger/death ordering identity. |
| owner | RECOMPUTE | The summoning player. v1 source guard requires original owner=controller=that player; control-change cases excluded. |
| controller | RECOMPUTE | The summoning player, independently assigned. |
| zone | RECOMPUTE | Board. Source must still be in Board when resolved. No hand/graveyard fallback. |
| zone_position | RECOMPUTE | Append immediately right of the rightmost admitted source; update positions through normal zone helpers. |
| can_attack | RESET | false: fresh ordinary non-Rush/non-Charge summon. Source must itself have no acquired attack eligibility. |
| has_attacked_this_turn | RESET | false: new summon has not attacked. A previously attacking source is outside this on-play subset. |
| provenance | RECOMPUTE | INSTANCE_COPY_V1 (or a typed equivalent). Do not copy DECK/DISCOVERED origin as if this entity were drawn. Diagnostic ancestry, if desired, must not enter policy features. |

Damage state has **no separate CardInstance member**: it is derived from max_health-health. Its policy is FAIL_CLOSED_IF_PRESENT when this difference is nonzero; negative/inconsistent health also fails. Admitted zero damage transfers as health/max_health, with no healing/reset operation. Any future new member requires an explicit reviewed policy before the schema admits it.

Implementation, if later authorized, constructs a fresh destination field by field. It must not perform a struct copy followed by cleanup. Guard the source before any operation can normalize away unsupported hand modifiers; resolve_play currently resets attack/health/max_health, so a board-only check after that reset is insufficient. A failed guard invalidates the branch, not just the copy effect. No RNG is required for copying/history.

## Exact timing contract: established partial order and unresolved edge

Required reviewed partial order:

1. Check the immediately preceding own-turn type history; current play must not make itself qualify.
2. Commit the hand play, retaining valid persistent effects under the forward zone rule; place the original into play.
3. Resolve the on-play Kindred self-copy once if the prior-turn condition qualifies. This summons a new entity; it is not another hand play and must not recursively activate Kindred.
4. The original and copy later use ordinary batch death processing and each has its own unsilenced Deathrattle.

The **proposed but unconfirmed** integration order is: original enters Board -> eligible pre-effect summon reactions -> Kindred snapshot/copy -> eligible after-effect summon/play reactions including Explosive Runes -> existing stabilization. This sequence must NOT be described as a fully established Hearthstone contract. The exact boundaries of summon reactions and death checks within that sequence remain unresolved, and the current engine has no complete pre-/after-summon reaction model.

In a guard-admitted quiet state (no interfering reactions, no pending deaths, no modifications), those alternatives give the same source identity/stats and copy result. That makes a limited isolated copy primitive feasible; it does not resolve an interacting state by asserting equivalence.

## Minimum reachable-state audit of the frozen deck

Manifest: configs/training_profiles/meta_training_20261002_v1.json, tricky_burn_mage: 17 roots / 30 slots, including two Bookkeepers.

### Direct roots: source at the immediate play boundary

- No direct root buffs a minion in hand. Kalec buffs spells; Prepare applies to Tricksy; Raincaller changes its own attack. Spell Damage sources alter spell damage, not Bookkeeper stats.
- Bookkeeper begins as an unmodified, undamaged 2/2 Elemental. A previous hand-played Violet Spellwing (ELEMENTAL/BEAST), Living Flame, Raincaller or another Bookkeeper can qualify. Vulcanos is also Elemental, but remains unimplemented; its full appendage interactions are not assumed away.
- Combat, Frostbolt, First Flame, Sleet, Fireball, Arcane Flow, Vulcanos end-turn damage, Secrets and hero power can affect Bookkeeper AFTER it is on the board. Those later states are not automatically part of an on-play self-copy snapshot; the copy operation is not invoked again just because that minion survives, attacks, is damaged or frozen. Thus v1 does not need general copy of every later board state to implement the quiet on-play case.
- No direct root provides Bookkeeper a counter, Prepare/Shatter link, Taunt, Lifesteal, Shield, Immune or Stealth before its play. This conclusion covers direct roots only, not dynamically generated cards or arbitrary opponents.

### Reachable interaction that blocks a full timing verdict

Tricksy can select CORE_LOOT_101 Explosive Runes from its unchanged six-member pinned Mage Secret pool. In a frozen-deck mirror, the opponent can therefore hold Runes when a qualifying Bookkeeper is played. Its pinned text specifies damage AFTER the opponent plays a minion. If Kindred resolves first, an undamaged copy can survive the original being killed; if an earlier damage/death boundary wins, the source/copy outcome can differ. The official keyword/copy sources do not settle this edge. No support-based pool narrowing or treating Runes as impossible is permitted.

The other five reviewed pool members are CORE_BAR_812, CORE_EX1_287, CORE_EX1_289, END_024 and JAIL_315. Their modeled triggers concern attacks, spells or turn end rather than the Bookkeeper play snapshot. This does not certify their complete closures or arbitrary generated Secrets.

### Dynamic expansion prevents a whole-deck vanilla-source claim

Winterspring Whelp can Discover a 1-cost spell from any class. Recomputed metadata candidates from current standard_current_enUS.json, using collectible / SPELL / cost=1 / non-neutral class-or-classes, give 75 IDs with sorted-LF SHA-256 2ca5fd3fdfe84afa03c5d5aa435e3619eb9813e3ad329881faab8cb1085f2d32. This is a **candidate set**, not a resolved runtime Discover manifest. The old report's 77 count/hash is not reused as proof: there are 77 cost-1 spells before the class exclusion, including neutral TIME_EVENT_999 and TLC_EVENT_400; exact historical hash/predicate equivalence has not been established.

Candidates include TIME_447 Power Word: Barrier (minions in hand gain Health) and CORE_CS2_004 Power Word: Shield (board Health buff). Thus a Whelp outcome can produce a non-base Bookkeeper in hand; broad future copy correctness cannot be reduced to the direct 17 roots. CORE_GIL_836 and other Discover cards introduce further generated minions/reactions. Whelp membership and recursive outcomes remain unresolved; neither absence of current implementation nor a runtime branch not yet sampled excludes them from rules reachability.

### Precise proposed admission guard

- Call only for a successful hand-played, same-owner/controller supported non-Rush/non-Charge minion with the reviewed Kindred operation and qualifying previous-own-turn type intersection; source remains its original live Board entity.
- Guard the original hand instance BEFORE any play-time stat normalization, then guard the live source at copy resolution. Require base attack/max_health, full positive health and every FAIL_CLOSED field default from the table; no unsupported intrinsic mechanics/auras.
- No control change, source transformation, re-entry, previous attack or acquired attack permission. Source is rightmost; no pending choices, unresolved triggers/deaths or unmodeled summon/play reactions that can affect this operation.
- Until the Runes edge is independently established, fail closed if an opposing reactive source can affect this minion play. Inspect authoritative Secret/event contracts, not player-visible identity. An unknown relevant source is a blocker. Do not omit a legal play to turn an invalid branch into a valid episode.
- At capacity 7 before the hand play, playing this minion is illegal. At capacity 6, the original occupies the last slot and the copy has no slot. At capacity 0..5, one copy can be summoned. No artificial burn/death/entity allocation for failure. Interfering reactions remain gated even when capacity might change their consequences.
- Reject reachable Whelp-generated modifications under this v1 guard; preserve complete outcome selection and invalidate unsupported branches. Do not declare the frozen deck closed or training-eligible from this quiet-state boundary.

This guard admits a small isolated behavioral subset without altering CardInstance. It is a proposed honest PARTIAL simulation boundary, not permission to relabel all reachable deck semantics as verified. Full frozen-deck admission cannot pass while a reachable legal interaction is gated.

## Minimal evidence needed and implementation decision

The next missing input is a reproducible current/pinned rules observation for **previous-turn Elemental -> qualifying Bookkeeper into opposing Explosive Runes**, with source/copy entity identities, order, damage/deaths, hand/deck changes and copy existence. A genuine Hearthstone Power.log/replay or explicit official timing clarification can establish this; a ManaEngine/Rosetta synthetic scenario cannot independently establish the expected result. Record client/version and whether the board had 0 or 5 friendly minions; no new engine scheduler is needed merely to capture the evidence.

For a more permissive future modifier contract, separately observe a hand-buffed Bookkeeper and original/copy states. Arbitrary counters, Freeze, silence and aura expiry may stay excluded from v1; no broad copy architecture is demanded now.

**MORE_RULES_EVIDENCE_REQUIRED** for a finalized Bookkeeper contract: the source-field subset is narrow and implementable, but the exact Kindred/Runes/death edge requested by this review is still not established. Safe implementation of the whole requested reviewed consumer cannot be asserted yet. A quiet-state PARTIAL primitive could be implemented only under explicit revised scope; no such implementation was started.

Production code, declarations, observation schema, canonical evidence and registry are unchanged. No tests/build/CI were run or claimed as new rules evidence in this analysis-only checkpoint. Training/search and further cards remain outside scope.
