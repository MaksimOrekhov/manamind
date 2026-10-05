# TIME_855 Arcane Barrage — rules evidence and executable-contract audit (Phase 4I)

Read-only audit at `7adee963d1f9c2e997bac230171480d7ec4ad71f`. Local, uncommitted. No production code touched.

**Revision 2 (review corrections):** (1) the evidence constraint is recorded whenever TIME_855 reaches its extra-target instruction, including zero candidates, and is renamed `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED`; (2) the topology claim is narrowed to observational equivalence of successful admitted outcomes, not trace equivalence; (3) the synthetic control fixture is stated to prove genericity only, not Multi-Shot-family rules; BB03/BB17 and the implementation section were updated to match.

**Revision 3 (final consistency pass):** (1) `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` now covers **only** targeting (enemy-hero membership, distinctness, insufficient-candidate behavior including n = 0 and n = 1); T2 topology is no longer part of it, G1 alone removes it, and G2 is required only before a board-changing or damage-dealing `ReactionKind` is admitted; no second topology constraint is added now. (2) BB10 replaced by a primitive-level mortality fixture. (3) BB12 wording corrected for the T2 primary-step mutation.

## 0. Method and limits

- Web access was available. `WebFetch` returns a *summary produced by a small model*, so every quote below was re-fetched with a
  "quote verbatim / do not infer" prompt where it matters; one summary claim (see E3) turned out to be the summarizer's inference and
  is discarded.
- Not reachable: Fandom (HTTP 402), hsguru (403), the Blizzard card-library page (client-rendered shell), YouTube and Reddit content
  (search returns only card pages; videos were not watched). **No current-client replay, Power.log or inspectable gameplay of TIME_855
  was found.** Public sources for Barrage itself prove the card text only.
- Pinned text (local data, SHA256 `c767c303…`): "Deal $3 damage to an enemy **and** $2 damage to two other random ones."
  The task brief says "then"; the pinned text says "and". That matters because the rulebook treats "and"/"then" identically for steps.
- RosettaStone behavior was not used as rules evidence.

## 1. EXECUTIVE VERDICT: **ARCANE_BARRAGE_BOUNDED_WITH_EVIDENCE_DEBT**

1. Barrage-specific evidence is the card text and nothing else. Every sequencing answer is an inference from analogous cards and from the
   independent research rulebook. No source is a current-client replay.
2. **T1, T2 and T3 are observationally equivalent for successful, currently admitted gameplay outcomes and their distributions.** The
   admitted `ReactionKind` families (generation into a hand, TakesDamage v1; Raincaller attack gain) cannot change the Barrage candidate
   set, the target identities, enemy health before selection, or the caster's Spell Damage. This is **not** a claim of complete
   execution-trace equivalence: the topologies can differ in diagnostic and failure-path RNG sequencing (the position of each draw in the
   stream) and in where an unsupported reaction fails and what state the poisoned branch retains. Topology becomes observable in
   successful outcomes only once a board-changing or damage-dealing reaction family is admitted (G2 below). Because the topologies are
   outcome-equivalent for admitted reactions, topology uncertainty needs **no EvidenceConstraint now**; it is tracked by the T2 reference
   choice and by the `ReactionKind` tripwire (section 7).
3. Three **distribution-critical** items do not depend on topology and rest on text plus analogy: the enemy hero is in the extras pool;
   the two extras are distinct; with too few candidates the spell resolves with fewer extras (no repeat, no retarget). They justify one
   evidence constraint, `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED`, until a client check (G1 below, one game) removes it. The
   zero-candidate rule (`k = min(2,n)`, `n = 0` gives no packet and no RNG draw) is itself unverified, so the constraint cannot depend on
   an extra actually being selected: it is recorded whenever the extra-target instruction executes, for n = 0, n = 1 and n >= 2. It covers
   **only** targeting; it does not cover topology.
4. No DamageGroup architecture change and no scheduler is needed.

The earlier `ARCANE_BARRAGE_REVIEW.md` is right that Barrage is not a scheduler problem and that "other" excludes the selected entity. It
missed the Swipe precedent, the Multi-Shot family evidence, the rulebook's "steps" rule, the observational-equivalence argument, and that the
pinned pool already holds independent consumers of the same selection shape.

## 2. EVIDENCE TABLE

| ID | Source (all fetched 2026-10-05) | Date/build | Proves | Does NOT prove | Confidence |
|---|---|---|---|---|---|
| E1 | Pinned snapshot `data/cards/standard_current_enUS.json`, TIME_855 | pinned 2026-10-01 | exact text, Mage Arcane spell, cost 3, no mechanics/tags | any sequencing, pool, distinctness | text: high |
| E2 | [Arcane Barrage, hearthstone.wiki.gg](https://hearthstone.wiki.gg/wiki/Arcane_Barrage) | release patch 34.0.0.229984 (2025-10-28) | text, set, Card ID; page has no notes on Spell Damage, bugs or edge cases | everything behavioral | text: high; behavior: none |
| E3 | [Arcane Barrage, HearthstoneTopDecks](https://www.hearthstonetopdecks.com/cards/arcane-barrage/) | n/a | text only. A first summary said the card "cannot be played with fewer than three enemies"; a second fetch confirmed **the page contains no such sentence**. Discard | any playability claim | text: high |
| E4 | [Advanced rulebook, hearthstone.wiki.gg](https://hearthstone.wiki.gg/wiki/Advanced_rulebook) (independent research, not official) | historical, undated | (a) nested Phases share one outermost Phase; Death Creation only after it ends; (b) multi-step spells let triggers occur between steps "regardless of whether the card's text uses 'and' or 'then'" (cites Blizzard, Light of the Naaru, Mortal Coil, Holy Nova; Swipe was a step-wise card until patch 2.7.0.9166); (c) simultaneous events are queued by order of play, then their triggers by order of play; (d) Rule 5: negative triggers ignore mortally wounded/pending-destroy characters, AoE counts them | which of Barrage's instructions are one step; random-selection timing (page silent on "random"); Spell Damage timing | medium (model, not replay) |
| E5 | [Damage, hearthstone.wiki.gg](https://hearthstone.wiki.gg/wiki/Damage) | historical | per-card order: Multi-Shot, Forked Lightning, Cleave "deal damage in random order" by creating all Damage Events, then resolving them in the same order; Swipe: targeted character first, then others in reverse play order; Arcane Missiles/Avenging Wrath etc. create and resolve each missile individually; Spell Damage applied before missiles are shot | Barrage (not listed) | medium |
| E6 | [Swipe, hearthstone.wiki.gg](https://hearthstone.wiki.gg/wiki/Swipe) | patch 2.7.0.9166 (2015) | "X to a target and Y to others" was changed to deal all damage before any on-damage trigger; Spell Damage +1 gives 5 and 2 | that Blizzard scripts Barrage the same way (Swipe's others are deterministic) | medium (nearest structural analog) |
| E7 | [Multi-Shot](https://hearthstone.wiki.gg/wiki/Multi-Shot), [Cleave](https://hearthstone.wiki.gg/wiki/Cleave), [Forked Lightning](https://hearthstone.wiki.gg/wiki/Forked_Lightning) | patch 14.6.0.31761 (2019-07-01) | two random targets are both damaged before triggers are queued; castable with one viable target; Forked Lightning with one enemy minion: that minion "takes 2 damage" (once) | same-target repeats are never stated outright; Barrage | medium |
| E8 | [Patch 14.6 news, HearthPwn](https://www.hearthpwn.com/news/6772-patch-14-6-now-live-card-art-updates-dalaran-heist) | 2019-07-01 | verbatim patch note: Dark Bargain, Cleave, Multi-Shot and Forked Lightning "can now be casted even if there is only one viable target" | hit count of that one target | medium-high (publisher text relayed) |
| E9 | [Forum thread, Blizzard US](https://us.forums.blizzard.com/en/hearthstone/t/multi-shot-forked-lightning-cleave-got-buffed/9657) | 2019 | one player report: Multi-Shot against a single minion dealt 3 once; players, not staff | official confirmation | low (anecdote) |
| E10 | [Arcane Missiles](https://hearthstone.wiki.gg/wiki/Arcane_Missiles) | historical | each missile resolves, with triggers, before the next; mortally wounded characters are not selected; pool reassessed per missile; heroes can be hit by the non-targeted random effect; Immune/Stealth minions can be selected; Spell Damage adds missiles | Barrage is not a missile spell | medium |
| E11 | [Target](https://hearthstone.wiki.gg/wiki/Target) | historical | "enemies" without "minions" includes the enemy hero; Stealth/Immune can be hit by random or untargeted effects | whether "other random ones" pools include the hero (text-level inference only) | medium |
| E12 | [Spell Damage](https://hearthstone.wiki.gg/wiki/Spell_Damage) | historical | Spell Damage holds "the most up-to-date value"; most spells add the full bonus to each target (Swipe example); silent on conditional sources changing mid-resolution | evaluation point for Barrage | medium |
| E13 | Patch notes [36.6.3](https://hearthstone.blizzard.com/en-us/news/24303864) (2026-10-01), 34.2.2, 36.4.2 | 2025-2026 | no mention of Arcane Barrage | absence of bugs | low |
| E14 | Pinned pool scan (local) | 2026-10-01 | independent consumers of "N random distinct enemies": `FIR_909` (3 enemies), `TIME_441` (2 enemies), `CATA_498` and `CORE_CATA_007` (2 enemy minions), `TIME_611` (Freeze 2 enemy minions). `TIME_001`/Missiles are the with-replacement sequential family | rules for any of them | high (data) |
| E15 | Bursting Shot and Aeon Rend wiki pages | n/a | pages carry no mechanics notes (hero inclusion, distinctness absent) | any | n/a |
| E16 | `reports/manaengine_damage_group_20261005/ARCANE_BARRAGE_REVIEW.md` | repo | prior challenge list, three topologies | evidence | design only |

## 3. SEMANTIC DECISION TABLE

| # | Question | Status | Chosen rule | Evidence / note |
|---|---|---|---|---|
| 1 | Does the selected hit complete its reactions before extras are chosen? | UNRESOLVED (topology); equivalent for successful admitted outcomes | reference contract T2: primary single packet completes with reactions first | for: E4(b) steps rule; against: E6 (Swipe precedent one event set). Admitted reactions cannot change anything the extras read; failure-path sequencing may still differ. No EvidenceConstraint: G2 is required before a topology-visible `ReactionKind` is admitted |
| 2 | Extras: up front, after primary, or one at a time? | UNRESOLVED between primary and extras; **pair together: DECIDED_WITH_DEBT** | extras are sampled as one pair after the primary completes (T2) | E5/E7: the two random targets of the Multi-Shot family are fixed and damaged together before triggers; no source supports one-at-a-time for a pair; E10 is the with-replacement missile family |
| 3 | Distinct entities? | **DECIDED_WITH_DEBT: distinct** | the two extras are different entities; none equals the selected entity | E7 (Forked Lightning with one target: one hit of 2), E8, E9; the word "other" |
| 4 | Candidate pool | **DECIDED_WITH_DEBT** | enemy hero plus enemy minions, minus the selected entity by identity; mortally wounded (`health<=0`) excluded; Stealth/Immune/Divine Shield included; entities created by earlier reactions: unreachable today, fail closed if a reaction family that can change the board is ever admitted | hero: E11 + E10 + text ("enemy" without "minion"); mortal: E4(d), E10; no Barrage replay |
| 5 | Too few candidates | **DECIDED_WITH_DEBT** | selected enemy always legal; extras = min(2, n); no skipped slot, no repeat, no retarget; n = 0 draws no RNG and emits no packet | E7, E8, E9 by analogy. The zero-extras case (selected hero, no minions) has no direct analog; the `n = 0` rule is itself unverified and is covered by the constraint |
| 6 | Reaction barrier (selected reaction before extras; first extra reaction vs second selection) | UNRESOLVED; equivalent for successful admitted outcomes | as #1; T3's extra-after-extra dependence has no support for a pair (E7) | experiment G2 (needed before admitting a board-changing or damage-dealing `ReactionKind`, not for the targeting constraint) |
| 7 | Deaths between packets | **DECIDED (model-level)** | no removal between packets; mortal entities stay until the outer boundary | E4(a); same evidence class as `MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED` |
| 8 | Spell Damage | amount **DECIDED**; evaluation point UNRESOLVED but not outcome-relevant for admitted gameplay | primary 3 + current Spell Damage; each extra 2 + current Spell Damage; evaluate once per instruction (CURRENT_AT_STEP), never `MISSILE_TOTAL` | E5, E6, E12. Barrage damages enemies only, so it cannot change the caster's Spell Damage in any admitted state; conditional-source experiment (E5) matters only after damage-dealing reactions are admitted |
| 9 | Divine Shield / Immune | **DECIDED** | selectable; prevented packet consumes its slot, emits no event, advances the spell, does not change selection | E10 (Immune selectable, takes no damage), engine contract for shields |
| 10 | Reborn / transform / summon identity | **DECIDED by construction** | exclusion is by entity ID captured at selection; Reborn returns only at the outer boundary with a new ID; mid-spell transform/removal fails closed | no re-insertion is possible because the pool is built once per instruction |
| 11 | RNG contract | **DECIDED (simulator-owned)** | partial Fisher-Yates over a stable candidate order: draw i uses `bounded_random(n-i)`; `k = min(2,n)` draws; selection order is event order; no reroll; empty set draws nothing | consistent with E5 "random order" and distinct sampling; not Blizzard's PRNG |

## 4. TOPOLOGY VERDICT

| | Evidence for | Evidence against | Unresolved | DamageGroupLocalV1 can represent? |
|---|---|---|---|---|
| **T1** preselected apply-all (3/2/2 in one group) | E6 Swipe precedent (target plus others as one event set); E7 pair simultaneity | E4(b): triggers can occur between steps even with "and"; Swipe's others are deterministic | whether Barrage is scripted as one effect | **Yes, no architecture change.** `DamagePacketIntent.amount` is per packet. Hero among targets forces `ScalarOnly` (existing guard: a generation consumer in a hero-containing group is rejected); heroes cannot use `MinionEntrySequence` |
| **T2** primary, then extras as one group | E4(b) steps rule; E7 pair simultaneity; natural "targeted effect, then Multi-Shot-like effect" | E6 suggests one effect | whether primary's triggers precede the pair's selection | **Yes.** `deal_damage` for the primary, then selection, then `run_damage_group` (ApplyAll) for the pair; local continuation in `resolve_effects` (Sleet Storm precedent) |
| **T3** fully sequential | E10 missile precedent for sequential random fire | E7 says random pairs are damaged together; Barrage's text has no "missiles"/"split" | everything | **Yes.** Three `deal_damage` calls with live selection between, exactly like Missiles |
| **T4** extras selected before the primary's reactions but damaged after, or pair in random event order | covered by E5's "random order" | none | order is exchangeable for same-controller extras | Equivalent to T1/T2 in distribution; no extra machinery |

**Chosen reference: T2.** It is the best-supported composition (steps rule plus family evidence). For successful admitted outcomes it is
equivalent in distribution to T1 and T3; it remains a reference topology, not a verified one, until client evidence exists.

Why the topologies are outcome-equivalent today (verified against HEAD): `ReactionKind` has two members. `SelfTakesDamageV1` draws one RNG value and adds a card to the
consumer's hand. `FirstSpellDamageAttackV1` adds Attack to the caster's own Raincaller. Neither reads or writes the enemy board, enemy health
or the caster's Spell Damage, and the pool size and selection bounds do not depend on earlier draws. Death is outer-boundary in every
topology, so the selected entity's lethality cannot re-enter the pool.

What is **not** claimed: trace equivalence. The topologies differ in (a) the position of each generation draw relative to the selection draws
in the RNG stream (the same seed gives different generated cards, though the distribution is the same); (b) where an unsupported or failing
reaction (hand full, unresolved pool, lethal TakesDamage consumer) stops the cast, and therefore which packets are already applied in the
poisoned branch; (c) trace ordering of DAMAGE and reaction rows. These are diagnostic and failure-path differences only. They do not change which entities are damaged or what is generated in distribution, so they
are not recorded as an EvidenceConstraint.

## 5. MINIMAL CLIENT EXPERIMENTS (only unresolved items)

All use a current client with Power.log capture. Each distinguishes several hypotheses at once.

**G1 — pool, distinctness, insufficient targets (covers E1, E8). Sufficient by itself to remove `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED`.**
SETUP: opponent has exactly one minion `M` (any, at least 4 Health, no Divine Shield) plus their hero. ACTION: cast Barrage on `M`.
OBSERVABLE: damage tags. Hero takes 2 and `M` takes 3 only: hero is in the pool, extras are distinct, insufficient pool resolves with fewer
extras (one packet, no repeat). `M` takes 5: same-target repeat. Hero takes 0 and `M` takes 3: hero not in the pool. Variant G1b: cast on
the **hero** with exactly one enemy minion: minion takes 2 once, hero takes 3 and nothing else (E8; also the zero-extra case when the minion
is absent).

**G2 — topology and reaction barrier (covers E3, E4). Not required to remove the targeting constraint; required before admitting any new board-changing or damage-dealing `ReactionKind` that makes topology observable.**
SETUP: opponent has Imp Gang Boss (summons a 1/1 Imp when damaged) as the target `X`, one plain 5-Health minion `P`, and their hero.
ACTION: cast Barrage on `X`. OBSERVABLE (single cast, ordering of log blocks): all three DAMAGE tag changes before the summon trigger block means
T1; trigger block between the primary's damage and the extras' damage with both extras' damage before the next trigger means T2. Repeat casts to
see whether the summoned Imp ever takes 2: never under T1, possible under T2/T3. Add a second Imp Gang Boss as an extra to separate T2 from T3
(first extra's trigger before the second extra's damage means T3).

**G3 — shield and Reborn (covers E6, E7), optional.**
SETUP: two extras candidates with Divine Shield, a Reborn minion as the selected target at lethal damage. OBSERVABLE: a shielded extra keeps its
slot (pops, no damage, no retarget); the returned Reborn copy is never damaged by the extras.

E5 (conditional Spell Damage changing after the primary): **not needed now.** Barrage cannot damage the caster's side, and no admitted reaction
damages it. Defer until a damage-dealing reaction family exists; then use any enemy minion that damages friendly minions when damaged to flip a
friendly "Spell Damage while damaged" source, and check extras' amounts.

Three games decide everything that is currently decidable; only G1 gates the existing constraint.

## 6. GENERIC PRIMITIVE DECISION: DistinctRandomTargetsV1

**Verdict: NOT YET as a Barrage-specific addition; YES as a bounded reviewed selection operation for the Multi-Shot family, built together
with one non-Barrage synthetic control declaration.** The family evidence (E5, E7, E8, E9) is stronger than Barrage's own, and the pinned
pool holds independent consumers (E14). Barrage then composes an explicit primary effect with the primitive plus an identity exclusion. Do not ship it
to hide Barrage's topology debt; ship it because "k distinct random enemies" is a coherent family.

Smallest typed contract:

| Field | Value |
|---|---|
| candidate selector | `EnemyCharacters` (hero first, then enemy board left to right) or `EnemyMinions`; selector decides hero inclusion, never inferred |
| count | `k` in 1..3 |
| identity exclusions | explicit set of entity IDs captured earlier in the same instruction list (Barrage: the selected target) |
| distinctness | always without replacement; with-replacement sequential fire (Missiles, `TIME_001`) is a different operation |
| timing | snapshot at operation start, after all earlier steps and their reactions complete; not re-sampled while the group runs |
| mortality | exclude `health<=0`; include Stealth, Immune, Divine Shield; never narrow to implemented outcomes |
| insufficient candidates | take `min(k,n)`; no skip, repeat or retarget; `n = 0` draws nothing and emits nothing |
| ordering | selection order is event order (partial Fisher-Yates, `bounded_random(n-i)`, no reroll) |
| RNG | exactly `min(k,n)` draws; simulator-owned |
| continuation | packets form one ApplyAll group after one `evaluate_spell_damage` (CURRENT_AT_STEP); follow-ups (draw, Freeze, death-dependent effects) run only after group completion |

Per-consumer admission stays separate: `CORE_CATA_007` needs a death-dependent follow-up, `CATA_498` a per-turn upgrade, `TIME_441` the Rewind
keyword; none is claimed or promoted by this audit.

Scope of the synthetic control: a test-only fixture (k = 3, minions only) proves that the operation is generic, that no TIME_855 card-ID
branch is required, and that renderer/catalog plumbing is reusable. It provides **no independent Hearthstone rules evidence** for the
Multi-Shot family. `FIR_909`, `TIME_441`, `CATA_498`, `CORE_CATA_007` and `TIME_611` each require their own consumer-specific rules
admission later; nothing in this report promotes any of them.

## 7. IMPLEMENTATION SHAPE (no code)

Smallest package on current DamageGroupLocalV1 (T2 reference):

1. **Declaration surface.** One appended `TargetSelector` value for the random-distinct enemy selector and two typed `EffectStep` fields
   (`random_count`, `exclude_previous_target`); catalog validation: count bounds, selector only on Damage, exclusion only when an earlier
   explicit target exists. TIME_855 becomes a two-effect composition: explicit enemy-character damage 3, then random-distinct damage 2 with
   count 2 and exclusion. No card-ID branch.
2. **Engine.** In the existing Damage case of `resolve_effects`: build the candidate list, run the partial Fisher-Yates with
   `bounded_random`, then emit packets through `run_damage_group` (ApplyAll). Reuse `MinionEntrySequence` when no hero was drawn and
   `ScalarOnly` otherwise, which fails closed for a generation consumer beside a hero (conservative, no DamageGroup change). The primary
   uses the existing single-packet path, so its reactions finish first. Amounts come from two `evaluate_spell_damage` calls.
3. **Evidence debt.** One new `EvidenceConstraint`, `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` (native
   `ArcaneBarrageTargetingContractUnverified`), registered in `EVIDENCE_CONSTRAINT_IDS`. Scope is the complete targeting contract, not
   successful extra selection: it is recorded **whenever TIME_855 reaches and executes its extra-target instruction**, for `n = 0`, `n = 1`
   and `n >= 2` candidates alike (so also when the selected hero leaves no minion and no packet or RNG draw occurs). It covers enemy-hero
   membership in the `EnemyCharacters` extras, distinctness (without replacement) and insufficient-candidate behavior (`k = min(2,n)`;
   `n = 0` and `n = 1` included; `n = 0` gives zero packets and zero draws). It does **not** cover topology: T1/T2/T3 are
   distribution-equivalent for admitted reactions, so no second (topology) constraint is added now. It blocks canonical training
   admission through the existing admission gate and does **not** invalidate or poison the simulation branch. G1 alone removes it.
   Registering it changes `observation_source_sha256` again; regenerate the pinned outputs.
4. **Topology tripwire.** A native test that fails when `ReactionKind` gains a member, forcing a review (G2, and the conditional Spell
   Damage experiment) before any board-changing or damage-dealing reaction is admitted. T2 stays the bounded reference topology until
   then. This tripwire, not an EvidenceConstraint, is the topology control. No code gate beyond that is needed.
5. **No architecture change.** A local continuation in `resolve_effects` suffices (Sleet Storm precedent). Nested DamageGroups are not
   required by T1, T2 or T3. No scheduler.

Optional later change, not required: a `DamageEventOrder` value that accepts heroes and keeps selection order, which would let a
generation consumer coexist with a hero extra.

## 8. TEST MATRIX (native, before any support promotion)

| ID | Scenario | Expectation |
|---|---|---|
| BB01 | enemy hero + one minion `M`, cast on `M` (n = 1) | `M` 3 once, hero 2, one extra, constraint present |
| BB02 | cast on enemy hero, one enemy minion | hero 3, minion 2 once, no repeat |
| BB03 | cast on hero, no enemy minions (n = 0) | hero 3 only, no extra packet, no RNG consumed; **`ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` still present**; branch valid |
| BB04 | hero + 3 minions, cast on minion, many seeds (n >= 2) | two distinct extras never equal the target; hero reachable; both extra slots filled; constraint present |
| BB05 | seed sweep distribution | extras uniform over hero + other minions (counts within a stated tolerance) |
| BB06 | `+2` static Spell Damage | primary 5, each extra 4; two DAMAGE_BOUNDARY traces, no MISSILE_TOTAL |
| BB07 | Divine Shield extra, Immune extra | slot consumed, shield popped, no damage, selection unchanged, no event |
| BB08 | lethal primary on a Reborn minion | returned copy is a new entity, never damaged by the extras, appears only after the outer boundary |
| BB09 | Reborn/lethal extra | mortal entity stays in Play until the outer boundary; Reborn at the outer boundary |
| BB10 | **primitive-level synthetic fixture** (contract coverage, not a normal Barrage gameplay state): `DistinctRandomTargetsV1` called directly with a candidate set that holds an already mortally wounded enemy entity (`health <= 0`) plus living candidates | the mortal entity is never selected, is not counted in `n`, and consumes no draw; the primary-lethal case is not used because the primary is already excluded by identity |
| BB11 | TakesDamage consumer as primary, as extra (reviewed pool) | reactions complete in a stable order; RNG advances by the sampler path; same results from a clone |
| BB12 | generation consumer + hero extra | rejected before the mutations of the extras damage group (existing guard); the primary-step mutation has already executed under T2 and is retained diagnostically because the action becomes poisoned. Separate from the constraint |
| BB13 | Raincaller present | attack gain once; extras still selected |
| BB14 | unresolved Fire pool during extras | all mutations retained, first reason kept, no reroll |
| BB15 | RNG replay | independently replayed `bounded_random` draws predict exactly the extras and their order |
| BB16 | `ReactionKind` tripwire | fails if the enum gains a member, forcing a G2/topology review before any board-changing or damage-dealing reaction is admitted; no topology constraint exists |
| BB17 | constraint scope | `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` (targeting only: hero membership, distinctness, insufficient-candidate behavior) present after every executed Barrage extra-target instruction for n = 0, n = 1 and n >= 2 (also in the zero-RNG case); no second constraint for topology; absent in a session where Barrage was never cast or the spell was countered before its effect; branch stays valid; canonical admission blocked; not raised by other spells |
| BB18 | adapter | real Mage session cast; poisoned-state accessors still refused |
| BB19 | synthetic control declaration | test-only fixture (k = 3, minions only) uses the same code path with no TIME_855 card-ID branch and no renderer changes; asserts genericity only, not Hearthstone rules, and promotes no real card |

## 9. FINAL ANSWERS

- **A. Can TIME_855 be implemented correctly now?** **YES_WITH_EVIDENCE_DEBT.** Correct for successful outcomes under the admitted reaction set; the
  constraint `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED` covers hero-in-pool, distinctness and insufficient-candidate behavior (n = 0 and
  n = 1 included), recorded whenever the extra-target instruction executes. T2 is the bounded reference topology and carries no constraint
  (outcome-equivalent for admitted reactions; `ReactionKind` tripwire plus G2 before any topology-visible reaction).
- **B. DamageGroup architecture changes?** **NO.**
- **C. Global scheduler?** **NO.** No counterexample found: T1, T2 and T3 are all representable with the existing group and local
  continuation.
- **D. Model:** **GPT-6.1 Sol Medium.** The semantics are fixed above and DamageGroupLocalV1 is stable, so the work is a bounded change:
  one selector, two typed fields, one selection routine, one evidence constraint with registry regeneration, and the test matrix.
  It is not declaration-only (Luna High would be too light: new engine code, RNG contract, fingerprint regeneration). It does not need
  Sol High: no new architecture, no phase or lifetime redesign.
- **E. Smallest unlocking evidence:** one Power.log of **G1**: opponent with one minion and a hero, Barrage on the minion. Hero takes 2 and
  the minion only 3 settles hero-in-pool, distinctness and insufficient-target behavior at once and removes
  `ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED`. G2 is not needed for that; it is needed only before a topology-visible `ReactionKind`
  is admitted.
