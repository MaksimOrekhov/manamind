# ManaEngine prototype — reuse audit and architecture review

Date: 2026-10-03
Branch: `codex/manaengine-prototype`
Base: ManaMind `0b27fec85b288996535c543b2e633c85ce73d68c` (`main`)
RosettaStone gitlink: `f34da0d3fcb5ad312f7e2acf634d0536b044d29a` (`codex/manamind-engine`)

## Status

**Prototype completed on the isolated branch.** The user explicitly approved the internal `EngineState` boundary, the bounded FIFO trigger/death/deathrattle cycle, typed pending choice, deep-copy clone, deterministic RNG, and the Tier A/B evidence rule. The implementation remains an experiment; no Rosetta source, profile, declarations, canonical registry, evidence, datasets, checkpoints, or training behavior was changed.

The user set a hard cap of 12 active Codex work hours for the whole experiment. Do not extend it. Count active task execution time, excluding calendar gaps and waiting for the user. Checkpoints: ~3h reuse inventory + backend boundary + buildable ManaEngine + basic game/player/zones/turn/mana/actions; ~6h first 5–10 parity roots + combat/damage/death/trigger + generic choice continuation + at least one terminal match; ~10h, if feasible, 15–25 roots + deterministic replay/RNG + clone/branch + Python adapter + core benchmarks; 12h hard stop with the comparative report. If no terminal match exists by ~6h or completing it requires major ManaMind redesign, stop implementation early and report.

## Starting tree and reproducibility

- Existing checkout stays on `main`; its local-only documents remain untouched.
- Prototype checkout is an isolated managed worktree on `codex/manaengine-prototype`, based exactly on the pinned main commit above.
- Local Windows checks on the base: Ruff passed; `scripts/check_generated_artifacts.py` passed and reproduced 36 pinned outputs; Python tests passed **80/80** with pytest's `--basetemp` redirected into the workspace. The default pytest temp location is outside the permitted sandbox and caused setup permission errors, not test failures.
- GitHub combined-status lookup returned no individual statuses, so this audit does not claim a fresh remote CI result. The prior task's report says CI for this same main commit was green.
- Existing ignored Rosetta build directories and local audit/proposal documents were preserved.

## Reuse inventory

| Area | Classification | Current asset and boundary |
|---|---|---|
| `CardFeatures`, entity values and visible `GameState` | `REUSE_WITH_ADAPTER` | Frozen Python observation domain can remain the public projection. It omits authoritative deck order, RNG, pending event work, choice continuation, and other hidden simulator state; it cannot safely be the complete simulator state without schema/meaning changes. |
| Catalog and vocabulary | `REUSE_UNCHANGED` | Stable card metadata/identity input for observations and model encoding. Engine-internal card instances still need their own state representation and identity/lifecycle. |
| `GameState`/entity encoders, batching, Value Network, policy API | `REUSE_UNCHANGED` behind projection | Can score prototype observations if projection preserves existing contracts. Model inputs must remain player-visible; internal IDs, hidden order and RNG must not leak into features. |
| Legal action descriptors and `Policy` API | `REUSE_WITH_ADAPTER` | Preserve the existing action boundary where action fields have matching semantics. Engine actions need an adapter; entity handles remain execution-only. Choice windows need a distinct, explicit continuation contract. |
| Power.log import, datasets, split, checkpoints | `REUSE_UNCHANGED` for stored formats | No schema changes or new generated data are needed for the prototype. Do not reinterpret checkpoints or write over datasets. A prototype backend may emit compatible observations for diagnostics only. |
| Standard profile, canonical registry, dependency metadata | `REUSE_UNCHANGED` as selection/evidence inputs | Read current verified-scoped roots dynamically. They are not runtime rules or a license to mutate profile/evidence. |
| Capability declarations/generators | `ROSETTA_SPECIFIC` initially | These define Rosetta-oriented behavior and emit Rosetta source. A prototype may map only a reviewed subset through an adapter if that is demonstrably small; no second DSL/interpreter. Otherwise use typed C++ builders and report reuse limits. |
| Rosetta adapter and native bridge | `ROSETTA_SPECIFIC` | Reference backend and parity participant. Keep usable and unchanged; make no Rosetta semantic cleanup part of this experiment. |
| Proposed backend/session interface | `EXPERIMENTAL_NEW` | A thin boundary could expose reset/create, observation, legal actions/apply, clone/checkpoint/restore, deterministic seed, choice status/options, terminal/result. Its ownership and lifecycle semantics must be decided before implementation. |

## Accepted prototype architecture and bounded semantics

The user explicitly approved option A: a private authoritative C++ `EngineState`, projected to the existing player-visible ManaMind `GameState`. The visible observation and legal action representation stay at the adapter boundary; hidden deck order, RNG, pending events and continuation remain internal. No mutable internal state will be added to `GameState`.

Prototype processing contract, explicitly not a complete Hearthstone specification:

1. resolve queued triggers FIFO;
2. mark and remove deaths;
3. enqueue and resolve resulting deathrattles FIFO;
4. repeat trigger/death/deathrattle passes until no work remains.

A pending choice is a typed state value with owner, complete runtime-derived options and continuation payload. Resolving a choice clears the pending state and resumes its typed continuation. Session clone deep-copies all internal values including RNG state and pending events/choice. RNG uses a fixed, serializable seed/state. Document and test ordering; deviations from this narrow cycle are limitations, not an invitation to build a general event rewrite.

### Evidence tiers and candidate roots

The pinned Meta Training Profile has exactly 18 roots with `meta_profile_verification=VERIFIED_SCOPED_CURRENT`; canonical registry evidence marks 3 of these current. These 18 are the complete Tier A + Tier B parity selection for the prototype. Tier A is the three current canonical roots:

- `CORE_DRG_107` — Violet Spellwing
- `CORE_SW_072` — Rustrot Viper
- `CORE_SW_108` — First Flame

Tier B contains the remaining 15 roots with current focused Meta Profile evidence:

- `CATA_475` Scalebreaker Bulwark; `CATA_999` Earthen Drake
- `CORE_BT_416` Raging Felscreamer
- `CORE_CS2_024` Frostbolt; `CORE_CS2_029` Fireball; `CORE_CS2_062` Hellfire; `CORE_CS2_072` Backstab
- `CORE_EX1_129` Fan of Knives; `CORE_EX1_145` Preparation; `CORE_ICC_055` Drain Soul
- `END_007` Press the Advantage
- `JAIL_327` Reinforcement Aura; `JAIL_516` Scarlet Recruiter; `JAIL_872` Spider Rider
- `TIME_218` Static Shock

Tier assignment must be generated from the selected Meta card matrix, its package evidence files and canonical Standard registry; the list above documents the audited result, not a hard-coded selector. These are scoped semantic anchors only, not full deck closure or training evidence. `JAIL_327`/`JAIL_516` candidate minions must be derived from the actual live deck state using the complete declared cost predicate; never pre-filter by ManaEngine implementation support. If an outcome cannot be modeled, report it as unsupported rather than shrinking the pool.

The selected roots cover targeted and board damage, draw, generated cards, summon, cost modification, attack and end-turn triggers, minion combat and Battlecry. No current Tier A/B root has a reviewed choice effect. Therefore demonstrate generic typed choice continuation and runtime-derived options in a separate clearly marked prototype-only scenario. It contributes zero Tier A/B parity roots and zero card-confidence claims. Tier C roots can appear only in exploratory smoke and are excluded from final parity scoring.

### Checkpoints and scope guard

- ~3 active hours: reuse inventory and backend boundary complete; ManaEngine builds; basic game/player/zones/turn/mana/actions work.
- ~6h: first 5–10 Tier A/B parity roots; combat/damage/death/triggers; generic choice continuation; one terminal match. If no terminal match exists or a major ManaMind redesign is needed, stop and prepare an early-stop report.
- ~10h (if feasible): up to 15–25 roots; deterministic replay/RNG, clone/branch, Python adapter and core performance benchmarks.
- **12 active hours: hard stop** for the whole experiment. Finish at a safe point and produce the comparison. Never extend the budget independently.
## Outcome

- Implemented 18 selected roots: all 3 Tier A plus 15 Tier B roots with current scoped Meta Profile evidence. Tier C was not used for parity.
- Added an isolated C++20 backend, a Python adapter returning the existing visible `GameState`, typed choices, deterministic clone/RNG, dynamic deck filters and an end-to-end prototype match.
- Focused Rosetta suite: 19 cases / 150 assertions passed on the pinned source revision. Direct adapter parity passed for opening state and the state after Violet Spellwing, including the legal-action set.
- ManaEngine native suite: 10 scenario groups / 53 assertions passed; adapter test passed; Ruff passed. The unchanged main checkout Python suite passed 80/80. Running the suite through a junction-mounted worktree produced 77/80 because three existing owner-path tests compare canonical paths; those failures are environmental and are not counted as a passing prototype suite.
- Ten benchmarked pass-only full games reached terminal state in both backends. A separate native fixture also reaches terminal using card plays and combat. These are prototype mechanics checks, not deck-completeness evidence.
- Elapsed active task time at completion: approximately 1 h 30 min, below the 12 h hard cap. See [the comparative report](../../reports/manaengine_prototype_20261003/FINAL_REPORT.md) and [completion record](../../reports/manaengine_prototype_20261003/COMPLETION_RECORD.md) for detail.

The work stays on `codex/manaengine-prototype`; it does not alter production backend selection, Standard admission, registry/evidence status or training.
