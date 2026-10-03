# Meta Training Profile v1 capability queue (updated after package 1)

Ranking uses target-deck reuse, existing RosettaStone support, dependency cost,
dynamic-pool complexity, correctness risk, declaration-only likelihood, and
Training Profile v1 usefulness. Candidates remain proposals until card text,
native definitions, dependencies and scenario expectations are reviewed.

| Rank | Candidate package | Reviewed profile candidates | Decks advanced | Existing primitives / likely shared work | Dependency and risk notes | Expected reuse / current view |
|---:|---|---|---:|---|---|---|
| Done | `targeted_spell_damage_hero_attack_v1` | `TIME_218` Static Shock; `END_007` Press the Advantage | 3 | Existing effect-composition declaration schema and `BTA_02pe` were independently checked. No shared renderer change. | Native family tests, bridge target/action parity, and explicit profile-scoped evidence pass. The roots do not complete their deck closures. | 2/2 declarations, 2 current profile-scoped roots; 0 training-eligible roots. See proposal completion record. |
| 1 | `cannoneer_trigger_and_token_family_v1` | `CAP_102`, `CAP_103`, `CAP_106`, `CAP_107`; related `CAP_104` only if its persistent Pirate modifier shares the reviewed contract | 2 | Existing Battlecry, summon, trigger and random-target primitives may be reusable; inspect the current `CustomTask` source owner and firing timing. | Several event links and end-of-turn/random target behavior; one source definition is custom. Do not merge `CAP_104` unless its semantics fit the same contract. | Up to 4 core consumers across both Warrior decks; material value, but substantially higher semantic and event-order risk. |
| 2 | `fabled_deck_seed_setup_v1` | `TIME_009`, `TIME_020`, `TIME_875` and six listed noncollectible seed candidates; later `JAIL_397`/Scarlet Bruiser only after separate contract review | 3–4 | Fabled deck composition/start-of-game seed handling may be shared across classes; exact current session and hidden-information boundaries are not audited. | Tokens are outside the pinned collectible catalog; exact seed membership, initial deck size, setup timing, DH session and Rogue opponent-deck handling need review. This may hit the session stop condition. | High cross-class leverage, but not selected until source ownership and session cost are known. |
| 3 | `low_cost_deck_minion_selection_v1` | `JAIL_327` Reinforcement Aura; `JAIL_516` Scarlet Recruiter; possible additional roots only after semantic review | 1 | Both mention minions from the deck with a low-cost predicate; selector may be reusable while activations differ. | Dynamic deck-state pool, depleted/empty deck behavior, duplicate copies and turn-end timing need exact expectations. `JAIL_516` currently has an unresolved generated-card pool candidate. | Two roots in one deck; potentially declaration-only shared selector, medium pool correctness cost. |
| 4 | `profile_discover_and_random_pools_by_predicate` | Current registry lists 41 distinct unresolved pool definitions reachable from profile roots; exact card families must be split by predicate, not implemented as one broad package. | 9+ | Existing Discover, random selection and deck/class/type filters can be reused only after predicate review. | Broadest correctness risk: exact pinned memberships, state-dependent filters and unsupported outcomes. Never narrow pools to implemented cards. | Potentially unlocks many episodes, but poor first-package ROI until shared predicates and memberships are measured. |

## Ranking notes

- The top candidate is a real two-root reusable contract already expressible in
  the current effect-composition schema. It appears in three of the frozen
  decks, including two classes.
- The next packages could affect more cards, but require custom event behavior,
  exact dynamic memberships or class/session setup. Their apparent card counts
  are not verified unlock estimates.
- Global Standard coverage is secondary. Unrelated candidates remain out of
  scope unless they are a reviewed dependency or a necessary independent
  control declaration for a universal contract.
