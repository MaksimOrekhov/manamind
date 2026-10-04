# ManaEngine Phase 4 — Tricky Burn Mage closure audit

Audit date: 2026-10-03  
ManaMind branch: codex/manaengine-first-deck  
Phase 3 checkpoint: eecc9fe9f187da5162037a4c052aca36896870d9  
Pinned RosettaStone gitlink: f34da0d3fcb5ad312f7e2acf634d0536b044d29a  
Frozen profile: configs/training_profiles/meta_training_20261002_v1.json

## Checkpoint — refreshed after Prepare and Mage Secret work

- Frozen deck: 30 slots, 17 unique roots.
- 6/17 roots currently have complete ManaEngine support declarations: CORE_SW_108, CORE_DRG_107, CORE_CS2_024, CORE_CS2_029, CATA_489, JAIL_321.
- 11/17 roots remain unsupported by the ManaEngine catalog.
- Mage class/hero power, turn/mana progression, draws, fatigue, hand burn, board limit, targeting, terminal result, deterministic RNG, clone, and a narrow typed Choice flow exist.
- Shatter hand pieces and generic Prepare actions are implemented and tested. Six pinned Mage Secrets, typed trigger windows, private identities/public counts, current-turn spell history, and the complete Tricksy Secret outcome pool are implemented in ManaEngine. Mulligan, Spell Damage, previous-turn Kindred history, and generic 30-card deck validation remain absent.
- The old registry reports two dynamic pool IDs. This audit found another dynamic dependency on JAIL_321: two random Mage Secrets.
- CATA_484 is the largest dependency risk: 77 current Standard collectible spell candidates, of which only First Flame has a closed ManaEngine outcome.
- Shatter and the minimal shared activation-sequence architecture are approved and implemented. Flames of Infinity uses the ordinary sequence; no FIRST/NORMAL/LAST priority classes exist.

## Frozen roots and ManaEngine-specific status

Status refers only to the Phase 3 ManaEngine catalog, not Rosetta registry status.

| Root | Slots | Status | Practical blocker / dependency |
|---|---:|---|---|
| CORE_SW_108 First Flame | 1 | CURRENT_MANAENGINE_SUPPORTED | Existing minion damage and generated Second Flame SW_108t. |
| CATA_485 Sleet Storm | 2 | NEEDS_SHARED_CAPABILITY | Spell Damage plus two damage operations, one involving a runtime-random enemy minion. |
| END_022 Time-Twisted Seer | 2 | NEEDS_SHARED_CAPABILITY | Spell Damage +2 while damaged; health-dependent aura rules. Dual-class Mage/Warrior. |
| CORE_DRG_107 Violet Spellwing | 2 | CURRENT_MANAENGINE_SUPPORTED | Existing Deathrattle creates EX1_277 Arcane Missiles. |
| CATA_484 Winterspring Whelp | 2 | DYNAMIC_DEPENDENCY | Discovers a 1-Cost spell from any class. Existing Choice renderer has a different Battlecry-minion predicate. |
| CORE_EX1_012 Bloodmage Thalnos | 1 | NEEDS_SHARED_CAPABILITY | Spell Damage +1 aura and Deathrattle draw. |
| CORE_CS2_024 Frostbolt | 2 | CURRENT_MANAENGINE_SUPPORTED | Existing targeted damage plus Freeze. |
| FIR_929 Living Flame | 2 | NEEDS_SHARED_CAPABILITY | Deathrattle draws a Fire spell from this deck: CORE_SW_108 ×1, CORE_CS2_029 ×2. |
| CATA_487 Raincaller | 2 | NEEDS_SHARED_CAPABILITY | First spell-damage event each turn grants +2 Attack. |
| TIME_855 Arcane Barrage | 2 | NEEDS_SHARED_CAPABILITY | 3 damage to selected enemy, then 2 to two other random enemy characters; needs distinct sampling and Spell Damage. |
| TLC_226 Conjured Bookkeeper | 2 | NEEDS_SHARED_CAPABILITY | Deathrattle draws a deck spell; Kindred summons a copy when an Elemental was played last turn. Seven unique spell IDs / 13 physical slots are eligible. The copy is fixed self-copy. |
| CATA_489 Arcane Flow | 2 | CURRENT_MANAENGINE_SUPPORTED | Typed linked fragment instances, opposite hand edges, solo/recombine behavior, semantic observation/action fields and both ordered effects are covered. |
| CATA_458 Archmage Kalec | 1 | NEEDS_SHARED_CAPABILITY | Battlecry grants Spell Damage +1 to spells in hand/deck; needs per-instance modifiers and draw rules. |
| CORE_CS2_029 Fireball | 2 | CURRENT_MANAENGINE_SUPPORTED | Existing targeted damage contract. |
| JAIL_321 Tricksy Improviser | 2 | CURRENT_MANAENGINE_SUPPORTED | Prepare, generic spell-cast history, and two independent random casts from the exact six-card Mage Secret pool are implemented. |
| CATA_488 Vulcanos | 1 | NEEDS_SHARED_CAPABILITY | Colossal +2 creates two appendages; end turn deals 3 to every other minion, including friendly. |
| CATA_452 Spellweaver's Brilliance | 2 | NEEDS_SHARED_CAPABILITY | Costs 1 less per damage actually dealt by spells this turn; summons a fixed 6/6 Dragon. |

## Dependency audit

Fixed edges:

- CORE_SW_108 → SW_108 Second Flame; CORE_DRG_107 → EX1_277 Arcane Missiles. Both outcomes are declared in ManaEngine.
- CATA_452 summons a fixed 6/6 Dragon. Its non-collectible ID is absent from the selected collectible catalog and must be resolved from pinned full definitions.
- CATA_488 creates two fixed Colossal appendages. Their non-collectible IDs must be resolved before implementation.
- TLC_226 creates another TLC_226 on Kindred. This is a fixed self-copy, not an external random pool.
- CATA_458 has an unreviewed registry candidate edge to CATA_458e. ManaEngine needs instance-level Spell Damage +1, not merely an edge.
- CORE_EX1_012 draws the next card from its own deck (no external card identity pool).
- FIR_929 draws from this deck's Fire subset: CORE_SW_108 ×1 and CORE_CS2_029 ×2.
- TLC_226 draws from this deck's spell subset: CORE_SW_108 ×1, CATA_485 ×2, CORE_CS2_024 ×2, TIME_855 ×2, CATA_489 ×2, CORE_CS2_029 ×2, CATA_452 ×2.

### CATA_484 — 1-Cost spell from any class

Pinned-catalog candidate predicate: collectible=true, type=SPELL, cost=1, and a non-neutral cardClass or dual-class classes entry. Result: **77 unique IDs**. SHA-256 of sorted IDs joined by LF: 1f1fa88099264bfe0e07fd971b7e75f73cce42040465f06cd514351dc38dedc0.

Two candidates have ManaEngine declarations: CORE_SW_108 and CORE_GIL_836. Only CORE_SW_108 has a closed outcome. CORE_GIL_836 is executable as a Battlecry-minion Discover, but its own 139-card outcome pool is not closed (only CORE_SW_072 is declared there). The other 75 candidates have no ManaEngine declaration.

These 77 IDs are the pinned-catalog candidate set, not a reviewed runtime pool manifest. Confirm exact eligibility of generated/non-collectible spells before admission; never filter by engine support. Overlapping text-family counts: 21 mention Discover, 11 random outcomes, 10 summon, 7 draw, 9 Quest, 3 Choose One, 2 Overload. The pool reaches nested choice/random mechanics and multi-turn state.

### JAIL_321 — two random Mage Secrets

The pinned collectible Standard catalog contains six Mage Secrets, none implemented in ManaEngine:

- CORE_BAR_812 Oasis Ally — summon when a friendly minion is attacked;
- CORE_EX1_287 Counterspell — counter an opponent spell;
- CORE_EX1_289 Ice Barrier — Armor when the hero is attacked;
- CORE_LOOT_101 Explosive Runes — damage a played minion and excess to its hero;
- END_024 Flames of Infinity — at enemy turn end, damage the highest-Health minion;
- JAIL_315 Mystic Misdirection — transform an attacking enemy minion.

ManaEngine stores active Secrets separately, exports both players' active counts, and exports identities only for the observing player's Secrets. The six typed windows are wired to the corresponding spell, attack, minion-play, and turn-end phases. End-turn board reactions and Secrets merge by a shared activation sequence while the existing FIFO trigger/death loop remains in place.

### TLC_226 heuristic resolution

The old POOL:TLC_226:generated_card entry resolves to a self-copy plus filtered draw from this deck. It is not an external random-card pool. The unresolved requirements are previous-turn Elemental history and copy/summon behavior.

## Session, actions, observation, and match gate

Existing: Mage class/hero power; opening hand and Coin; turn/mana progression; draw, fatigue, hand burn, board limit, combat, targeting; RNG, clone, terminal results; isolated EngineState adapted into the visible GameState; damage, Freeze, draw, death processing, narrow typed Choice; Shatter hand links and a distinct PrepareCard action with per-instance persistent discount and turn lock.

Missing or insufficient:

- Mulligan phase/API and deterministic policy.
- Exact 30-card deck validation.
- Spell Damage state, including static aura, damaged-only aura, and spell-instance modifiers.
- Previous-turn minion-type history plus current-turn cast/damage history.
- Colossal positions/appendages, exact token IDs, full outcome rules.
- Actual Tricky Burn Mage match. Current terminal test is a synthetic repeated Violet Spellwing deck.

Current actions are PlayCard, PrepareCard, Attack, HeroPower, EndTurn, ChooseCard. GameSession accepts arbitrary deck lengths, so deck-size validation is absent. Prepare spends all remaining mana and applies exactly `spent + 1` persistent discount. Eligibility for an already zero-cost Prepare card is unresolved: the prototype fails closed if the case arises.

## Reusable capability families

1. **Spell Damage and spell-event accounting** — END_022, CORE_EX1_012, CATA_458, CATA_487, with spell consumers CATA_485, TIME_855, CATA_452, CATA_489. Includes current/damaged-only auras, card-instance modifier, first-damage event, history, and cost formula.
2. **Filtered draw and Kindred history** — CORE_EX1_012, FIR_929, TLC_226. Reuse basic draw/death processing; add draw filters and previous-turn type history.
3. **Random enemy damage selection** — CATA_485, TIME_855, part of CATA_489. Reuse deterministic RNG; add candidate selection, distinct sampling, Spell Damage integration.
4. **Hand-state mechanics** — CATA_489 Shatter and JAIL_321 Prepare. Both now use instance-scoped typed state; Prepare is a separate action with per-instance persistent discount and a same-turn lock; Shatter changes card-instance count/order and exports partner position without exposing internal link IDs.
5. **Secret system** — JAIL_321 and six outcomes. Implemented with typed windows and an activation sequence shared with modeled end-turn board reactions. Tricksy samples the exact six-card pool independently for both casts and does not filter unsupported or already-active results.
6. **Colossal and turn-end board damage** — CATA_488, two appendages and symmetric other-minion damage.

The 77-outcome Discover closure is likely the largest declarative workload. Shatter and the Secret event windows are implemented; broad current-profile coverage remains far from deck readiness.

## Architecture decisions and implementation status

### Shatter — approved and implemented

- Each fragment is a real CardInstance with its real token ID. Partner entity IDs remain engine-internal; GameState and policy receive original card ID, fragment role, and partner hand position.
- Every hand-entry path uses the same Shatter capability. Fragments enter opposite hand ends, remain instance-linked across clone, become solo when their partner is played, and recombine only when linked fragments are adjacent.
- Family coverage includes draw/add-to-hand, two independent copies, intervening cards, each single fragment, recombination effects, hand capacity, clones, and semantic action/observation encoding.
- Prepare uses a distinct `PREPARE_CARD` action. It spends all remaining mana and applies exactly `spent + 1` persistent discount without capping the stored discount at the current cost. The card stays in its hand position and is locked for the rest of the turn. Its lock is exported into GameState and encoded with an explicit known mask. Eligibility for an already zero-cost card is unresolved; the simulator fails closed for that state.
- CATA_489 and JAIL_321 are supported in the Phase 4 ManaEngine catalog. The standard card JAIL_453's separate “when you Prepare” discount interaction remains outside this deck slice.

### Secret/event-order boundary — implemented prototype contract

The approved minimal extension assigns monotonically increasing activation sequence stamps to persistent reactive sources. End-turn board reactions and active Secrets are merged by that stamp; FIFO trigger/death processing is otherwise retained. Clone preserves stamps and the counter; a source re-entering its active zone receives a fresh stamp. Internal stamps are not included in GameState or Policy observations. This is prototype semantics and does not claim full Hearthstone event-order coverage beyond the reviewed scenarios.

## Phase 4 verification record (current checkpoint)

- Native Windows build: passed; ManaEngine native suite: 1/1 test passed, covering 25 scenario groups and 442 assertions after Secret support (the Prepare zero-cost case is now explicitly fail-closed).
- Python ManaEngine adapter: 8/8 tests passed via direct invocation. A full pytest completion has not been established for this experimental worktree; Rosetta-backed test collection is also limited because the worktree's RosettaStone submodule content is absent.
- Ruff: passed on modified Python files.
- CATA_489 and JAIL_321 ManaEngine support gained: +2 roots; two Shatter token dependencies and two Secret token definitions are available. No canonical Rosetta registry status changed.
- Secret verification covers all six outcomes, ordering/clone/re-entry, Tricksy cast history and full-pool sampling, and owner/opponent observation privacy. Observation schema is version 11; old checkpoints are rejected through the existing explicit schema-version check, with no implicit migration.
- No training or production-backend switch occurred. No macOS work was added.
