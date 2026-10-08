# ENGINE-STATE-IMPORT-0 — real-state readiness diagnostics

**Result: the diagnostic works, and it shows that no real position can be imported into ManaEngine today — 0 of 1,227 SELF decision positions in 32 real games.** The reasons are layered. Fixing the extractor alone, or the engine alone, clears nothing. This stage is read-only: it builds no native session, changes no rules, declares no card and admits nothing to training.

Everything in this directory is a sanitized aggregate (counts, percentages, blocker codes, card IDs seen in at least two games). No game IDs, handles, names, BattleTags, opponent hand identities or trajectories are present; a test scans the generated reports for them. Per-position diagnostics stay in the git-ignored `data/processed_state_import0/`.

Machine-readable results: [`coverage.json`](coverage.json) (all metrics, per corpus) and [`blockers.json`](blockers.json) (blocker catalog with proposed resolution, plus per-corpus rankings).

## 1. What was built

| Piece | Location |
|---|---|
| Capability view (which card IDs ManaEngine can execute, from declarations) | `src/manamind/integrations/manaengine/state_import_capability.py` |
| Position analyzer, blocker catalog, next-action relevance | `.../state_import_readiness.py` |
| Corpus readers, deterministic sampling, aggregation | `.../state_import_corpus.py` |
| CLI | `scripts/state_import_readiness.py` |
| Tests | `tests/test_state_import_readiness.py` (33), `experiments/manaengine/tests/test_state_import_capability_parity.py` (native parity, needs the build) |

**No second parser and no second support list.** The tool reads only artifacts the existing pipeline already produced and sanitized (policy decision records and live snapshots, both LIVE-0B projections, plus Value examples). Card support is computed from `card_abilities.json` with the same authoring guards `engine._load_definitions` applies (reviewed rules text, dependency closure). It does not load the native module, so it runs in Source CI; a native-build test asserts that its answer equals the real native catalog for all 1,218 records (checked locally: 0 differences).

**Seven blocker categories, never collapsed into one boolean.** `UNKNOWN`, `NOT_REPRESENTED`, `UNSUPPORTED_MECHANIC`, `UNSUPPORTED_CARD`, `RULE_UNRESOLVED`, `INCONSISTENT` (and `KNOWN` for what is available). Each of the 53 blocker codes (33 of them occur in the real corpus) also carries: the independent axis it belongs to (`SOURCE` = visible state/extractor, `NATIVE` = engine, `RULES`, `BOTH`), its nature (`OBSERVABLE` vs `INHERENTLY_HIDDEN`), and a proposed resolution (`IMPORT_CONTRACT`, `OBSERVATION_EXTRACTION`, `ENGINE_PRIMITIVE`, `CARD_DECLARATION`, `RULES_EVIDENCE`, `HIDDEN_INFORMATION_DESIGN`, `DEFER`). Each position reports separate verdicts for source completeness, hidden-information gaps, native capability, rules evidence, native hydration (always `BLOCKED_NO_FROM_STATE_CONSTRUCTOR`), the chosen action, and canonical training (always blocked).

**Blocker present vs blocker that stops the next action.** Every blocker has an applicability rule (whole position, entity, turn rotation, hero attack, draw/heal/spell-damage effect). For policy positions the chosen action is known, so each blocker is labelled `BLOCKS`, `NOT_INVOLVED` or `UNDETERMINED` for it. A blocker concerning an unsupported card is never `NOT_INVOLVED`: passive triggers of unsupported cards are unclassified (Phase 4K.1c), so non-involvement cannot be proven.

**Unknown stays unknown.** A raw snapshot is analyzed as a mapping, so an absent key is not silently a default. The existing extractor leaves many fields `None` or at a default; the analyzer reports them as unknown (`FIELD_PROVENANCE` in `coverage.json` records which). The Value-example source never extracted `secret_count`, so its stored `0` is reported as unknown too.

## 2. Real data actually available

All real data lives in the git-ignored directories of the main checkout (`E:\ManaMind\data`); none is in the worktree or the repository.

| Source | Content | Games | Records read | SELF decision positions |
|---|---|---:|---:|---:|
| `processed_policy_real/collected` (primary) | LIVE-sanitized states with legal actions and the chosen action | 32 | 1,227 | 1,227 |
| `raw/live/*/*/snapshots.jsonl` | live recordings of 12 of the same games | 12 | 635 | 635 |
| `processed_real` | Value examples, offline importer (entity-order hand, no secret counts) | 36 | 2,911 | 1,348 (rest are opponent-turn positions) |

The corpora overlap (all 12 live games are among the 32 policy games; 513 of 635 live state hashes also appear in the policy set), so their totals must not be added; the policy corpus is the independent unit. 38 raw match slices exist under `raw/collected`; the tool did not open them (three extractor facts below were spot-checked by hand-grepping one slice).

**Corpus limitation (important):** SELF is always a Priest or a Warrior; 968 of 1,227 positions (78.9%) hold the Imbue Hero Power, 205 hold an unreviewed Hero Power ID, and only 54 positions in 2 Warrior games hold a reviewed base power. Findings describe this player's decks, not the Standard pool.

**Sample.** 48 positions from all 32 games (max 2 per game), chosen by a seeded greedy balance over opponent class, SELF Hero Power, turn bucket, board size and chosen action (seed 20261008; independent of file order). Turns 1–41; 11 opponent classes; board buckets 0 / 1–2 / 3–4 / 5+ = 13 / 15 / 11 / 9; chosen actions: 11 End Turn, 10 play, 11 attack, 9 Hero Power, 7 Location activation. Full-corpus numbers below use all 1,227 positions; positions within a game are correlated, so game counts matter as much as position counts.

## 3. Findings

### 3.1 Headline

| | Sample (48 pos / 32 games) | Policy corpus (1,227 / 32) |
|---|---:|---:|
| Structurally valid, no `INCONSISTENT` | 100% | 100% |
| Visible fields sufficient *and* represented (all subsystems) | 0% | 0% |
| Native hydration possible today | 0% | 0% |
| Blocked by unsupported card | 100% | 100% |
| Blocked by unsupported mechanic | 54.2% | 81.5% |
| Needs state the native engine lacks (`NOT_REPRESENTED`, native/both) | 62.5% | 89.8% |
| `RULE_UNRESOLVED` | 81.3% | 52.0% |
| Affected by hidden information | 100% | 100% |
| SELF Hero Power not proven supported | 91.7% | 95.6% |
| Either seat's Hero Power not proven supported | 100% | 100% |
| Hero Power identity missing | 0% | 0% |
| Chosen action blocked by an action-specific blocker | 75.0% | 71.9% |
| Chosen action blocked only by whole-position blockers | 25.0% | 28.1% |

"Structurally valid" means the snapshot satisfies `GameState` invariants and board/order checks. It does not mean ManaEngine can simulate it.

### 3.2 Visible fields sufficient, by subsystem (policy corpus)

`Sufficient` = no observable-but-unknown, source-side not-represented or inconsistent blocker in that subsystem (hidden-by-design gaps are excluded).

Integrity 100% · Pending choice 100% · Weapon 100% · Hero Power 77.1% · Location 33.3% · Hand 29.7% · Secret 18.0% · Board 14.5% · Deck 0.2% · **Hero 0%** · **Game/turn 0%** · **Effects 0%**. (Sample: Hero Power 41.7%, Hand 66.7%, Board 27.1%.)

Hero, Game/turn and Effects are 0% because of fields the extractor never populates (below), not because the log lacks them. Pending choice and Weapon are 100% only in the sense that nothing is missing from what the extractor emits; the weapon's card can still be unsupported.

### 3.3 Top blockers

Counts are distinct positions and distinct games in the policy corpus (1,227 / 32). Categories overlap; **do not add them.** 12 of the 33 observed blocker codes occur in at least 99.5% of positions and therefore do not discriminate between positions.

**Universal (≥99.5% of positions, all 32 games):** `HERO_MAX_HEALTH_NOT_REPRESENTED`, `HEALING_BONUS_UNKNOWN`, `HERO_DIVINE_SHIELD_UNKNOWN`, `HERO_FREEZE_UNKNOWN`, `MINION_TYPE_HISTORY_UNKNOWN`, `TURN_COUNTERS_UNKNOWN`, `PLAYER_EFFECTS_NOT_EXTRACTED` (extractor/contract gaps, all observable), `OPPONENT_HAND_IDENTITIES_UNKNOWN`, `OPPONENT_DECK_COMPOSITION/ORDER_UNKNOWN`, `SELF_DECK_ORDER_UNKNOWN` (hidden) and `SELF_DECK_COMPOSITION_UNKNOWN` (needs a decklist input).

**Discriminating blockers, top 10 by distinct positions** (games in parentheses):

| # | Blocker | Category | Positions | Axis / proposed resolution |
|---:|---|---|---:|---|
| 1 | `UNSUPPORTED_CARD_SELF_HAND` | UNSUPPORTED_CARD | 1,217 (32) | NATIVE / CARD_DECLARATION |
| 2 | `UNSUPPORTED_CARD_NOT_IN_CATALOG` | UNSUPPORTED_CARD | 1,074 (32) | NATIVE / CARD_DECLARATION (tokens with no metadata) |
| 3 | `MINION_TARGETING_FLAGS_UNOBSERVED` | UNKNOWN | 1,047 (32) | SOURCE / OBSERVATION_EXTRACTION |
| 4 | `SELF_SECRET_IDENTITIES_UNKNOWN` | UNKNOWN | 1,006 (29) | SOURCE / OBSERVATION_EXTRACTION |
| 5 | `UNSUPPORTED_CARD_BOARD` | UNSUPPORTED_CARD | 987 (32) | NATIVE / CARD_DECLARATION |
| 6 | `HERO_POWER_IMBUE` | UNSUPPORTED_MECHANIC | 979 (27) | NATIVE / ENGINE_PRIMITIVE |
| 7 | `HAND_CARD_MODIFIER_PROVENANCE_NOT_REPRESENTED` | NOT_REPRESENTED | 863 (32) | BOTH / OBSERVATION_EXTRACTION |
| 8 | `LOCATION_ACTIVATION_STATE_UNKNOWN` | UNKNOWN | 818 (31) | SOURCE / OBSERVATION_EXTRACTION |
| 9 | `LOCATION_NOT_REPRESENTED_NATIVE` | NOT_REPRESENTED | 818 (31) | NATIVE / ENGINE_PRIMITIVE |
| 10 | `UNSUPPORTED_CARD_LOCATION` | UNSUPPORTED_CARD | 790 (28) | NATIVE / CARD_DECLARATION |

Next: `HERO_POWER_IDENTITY_UNREVIEWED` 638 (32) — RULE_UNRESOLVED, `MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED` 419 (32), `HERO_HEALTH_EXCEEDS_NATIVE_MAX` (hero above the native fixed 30 Health) 342 positions in 8 games, `OPPONENT_SECRET_IDENTITIES_UNKNOWN` 334 (11), `HERO_ATTACK_READINESS_NOT_REPRESENTED` 283 (18), `HERO_POWER_READINESS_UNKNOWN` 281 (32), `UNSUPPORTED_CARD_WEAPON` 77 (9), minion targeting restriction 73 (13), Windfury/Poisonous/Dormant minion 59 (9).

**Ranked by distinct games** the order is nearly flat: 20 of the 33 observed codes occur in all 32 games, including eight of the discriminating ones (`UNSUPPORTED_CARD_SELF_HAND`, `…NOT_IN_CATALOG`, `…BOARD`, `MINION_TARGETING_FLAGS_UNOBSERVED`, `HAND_CARD_MODIFIER_PROVENANCE_NOT_REPRESENTED`, `HERO_POWER_IDENTITY_UNREVIEWED`, `MINION_MODIFIER_PROVENANCE_NOT_REPRESENTED`, `HERO_POWER_READINESS_UNKNOWN`), followed by both Location blockers (31), `SELF_SECRET_IDENTITIES_UNKNOWN` (29), `UNSUPPORTED_CARD_LOCATION` (28), `HERO_POWER_IMBUE` (27). Hero Health above 30, opponent Secrets, hero attack readiness, weapons, targeting restrictions and Windfury/Poisonous/Dormant are minority-of-games problems (8–18 games). The sample's own ranking is in `blockers.json` (`primary_sample_ranking`).

Unsupported cards: 357 distinct card IDs appear in SELF hand/board/Locations and opposing public boards of the 32 games, against 113 supported card declarations. 225 of them occur in only one game and are not listed. The most frequent (≥2 games) are listed in `coverage.json`; the leaders are Location `CATA_301` (833 positions, 24 games), `TIME_890` and its tokens, `CORE_EX1_197`, `END_025`, `JAIL_913`, `CATA_308`.

### 3.4 Hero Power (proven vs unproven)

The current Hero Power ID is always present in these records and is never inferred from the class. It is **proven supported** only if that exact ID is a reviewed `HERO_POWER` declaration (`HERO_01bp`, `HERO_05bp`, `HERO_08bp`, `HERO_09bp`).

| Status | SELF positions | Opponent positions |
|---|---:|---:|
| Proven supported base | 54 (Warrior, 2 games) | 138 |
| Imbue power `EDR_449p` (documented Imbue lane) | 968 | 525 |
| Observed ID with no local metadata (SELF: `HERO_09dbp`, `HERO_01dbp`; opponents: 18 more IDs) | 205 | 564 |

Some of these IDs look like skins of base powers (a suffix letter, e.g. `HERO_09dbp`); others are other classes' base powers or older class-power IDs. Nothing in the repository proves the skin-like ones behave identically to the base power; the engine rejects them by design and the analyzer never aliases them. A reviewed alias manifest would be a `RULES_EVIDENCE` package and would turn 205 SELF and 564 opponent positions from `RULE_UNRESOLVED` into supported ones where the evidence holds.

A lead the tool does not use: the unpinned legacy RosettaStone `cards.json` (a submodule file, present only when the submodule is checked out) lists `HERO_09dbp`, `HERO_01dbp`, `HERO_05dbp`, `HERO_08fbp` and old class-power IDs such as `CS1h_001_H1` and `CS2_102_H1` with the same name, cost and text as the corresponding base power. That is textual evidence from an unpinned dump, not rules evidence, but it is the cheapest route to an alias manifest. To keep the diagnostic identical on every machine, "described by metadata" means the pinned snapshot, catalog and pinned dependency captures only.
Seven of eleven opponent classes (Death Knight, Demon Hunter, Druid, Paladin, Rogue, Shaman, Warlock) have no reviewed base power at all. Opponent-seat Hero Power blockers matter to the next action only at turn rotation, but the native engine reads both seats' power definitions on every legal-action enumeration and invariant check, so for hydration they are whole-position blockers.

### 3.5 Observational vs mechanical limitations

| Kind | Share of positions (policy) | What it means |
|---|---:|---|
| **Observational** — `SOURCE`/`BOTH` axis, resolvable by extraction/contract: 15 `OBSERVATION_EXTRACTION` codes + 1 `IMPORT_CONTRACT` code observed | 100% | Information exists in Power.log or a decklist but is not in `GameState`/the extractor. Never populated: hero max Health, hero freeze, healing bonus, spell/Demon discounts, cast counts, minion-type history, player enchantments, SELF Secret-zone identities, Location activation, Spell Damage amount, enchantment provenance. `None` because a tag is absent: hero Divine Shield, targeting flags, Hero Power readiness |
| **Hidden by design** — 5 codes, `HIDDEN_INFORMATION_DESIGN` | 100% | Opponent hand/deck/Secrets, SELF deck order. Needs the future information-set design; must not be guessed |
| **Mechanical, native** — `ENGINE_PRIMITIVE`, 6 codes observed | 90.6% | Location zone, Imbue, hero Health above 30, Windfury/Poisonous/Dormant, targeting restrictions, hero Divine Shield, Hero Power cost modifiers |
| **Mechanical, declarations** — `CARD_DECLARATION`, 5 codes observed | 100% | 357 card IDs without an executable, reviewed declaration |
| **Rules** — `RULES_EVIDENCE`, 1 code | 52.0% | Hero Power identities with unestablished semantics |

### 3.6 What resolving a blocker would leave (not additive)

Order of work below follows the dependency of the problems; each row cumulatively resolves everything up to it, for all non-hidden blockers:

| After resolving… | Positions with no remaining non-hidden blocker | Top remaining blockers |
|---|---:|---|
| `OBSERVATION_EXTRACTION` | 0 | SELF deck composition (1,224), unsupported cards, unreviewed Hero Powers |
| + `IMPORT_CONTRACT` | 0 | unsupported cards (1,217), not-in-catalog tokens (1,074), board cards (987), Imbue (979) |
| + `ENGINE_PRIMITIVE` | 0 | unsupported cards, Location cards (790), unreviewed Hero Powers (638) |
| + `CARD_DECLARATION` | 589 (48.0%) | `HERO_POWER_IDENTITY_UNREVIEWED` (638) |
| + `RULES_EVIDENCE` | 1,227 (100%) | — (hidden-information gaps remain by design) |

No single blocker is ever the only one left (`positions_where_it_is_the_only_non_hidden_blocker` is 0 for every code). Taken independently, the share of positions free of each class is: native missing state 10.2%, unsupported mechanic 18.5%, rule unresolved 48.0%, unsupported card 0%, observable unknown 0%. Gains from separate fixes overlap and cannot be summed; the real constraint is the combination.

### 3.7 Historical data stays readable

Value examples from DATA-0B, LIVE-0 snapshots and ML-1B policy records all parse (0 unreadable records among 4,773 read). A legacy-shaped state without Hero Power, Locations, healing bonus or effects (`data/samples/example_state.json`) is analyzed without error and reports those as unknown rather than as zero.

## 4. Why native hydration is impossible today

1. **No constructor.** `ManaEngineSession` and `GameSession` build only new games from two decks. There is no from-state entry point, so hydration is 0% regardless of the position.
2. **Visible state is not enough, and part of that is the extractor.** 15 observation-extraction blocker codes occur in the corpus, most of them in every position (fields `None` or defaulted by the current extractor); `hero_health` is current Health only (maximum Health is read and discarded); SELF Secret-zone identities are never emitted (and the zone also holds non-Secret spells — a SELF spell was seen moving hand→secret zone in a local slice).
3. **The native state cannot hold what real games contain.** No Location zone, Imbue, hero Health above 30, Windfury/Poisonous/Dormant, targeting restrictions, hero Divine Shield or Hero Power cost modifiers. Modified minions need enchantment provenance and lifetimes that neither `GameState` nor the native import path represent.
4. **Card coverage.** The engine has 113 supported card declarations (the task brief says 114; plus 4 base Hero Powers). 357 distinct card IDs in the 32 games are not executable, and the engine's active-hand gate throws on any unsupported SELF hand card, which is why that one blocker covers 99.2% of positions.
5. **Hidden information.** Opponent hand, deck, Secrets and SELF deck order are absent by rule. A native session needs concrete values; supplying them is the future information-set/determinization design, not an importer feature.

## 5. Smallest safe ENGINE-STATE-IMPORT-1 plan (proposal only; not started)

**Principle:** make the importer fail closed on the reasons above, prove the native constructor on states ManaEngine itself produced, and do not touch real positions until blockers can actually reach zero. The first stage must not claim to import a real game.

1. **Import contract (Python + C++ struct).** A versioned `NativeImportState` carrying exactly what `PlayerState`/`CardInstance` hold: per seat `player_class`, `hero_power_id`, `hero_health`, `hero_max_health`, `healing_bonus`, `armor`, `hero_attack`/temp attack, weapon, mana/overload, turn-local counters (`spells_cast_this_turn`, discounts, minion-type histories), `hero_attacked`, `hero_power_used_this_turn`, freeze state; zones with per-entity stats, keywords, `can_attack`/`has_attacked`, damage and persistent modifiers; turn number, active seat; no pending choice (rejected, not guessed). Hidden zones are **explicit inputs** with an `origin` field (`ENGINE_TEST_FIXTURE` only in this stage) — never defaulted.
2. **Validation before construction.** Reject unknown fields/versions; every field required (`None` = reject, never default); hero power must be a reviewed `HERO_POWER` declaration; every card supported; zone capacities and board geometry; stat ranges (current ≤ max, alive); hand/deck counts consistent with supplied zones; keywords limited to the native set; no evidence debt in input.
3. **Native strict constructor** `GameSession::from_import_state`, appended `FailureCode`s (`IMPORT_*`, all `UNSUPPORTED` or `ENGINE_DEFECT`), poison-free: a rejected input never yields a session. Append-only enums; follow the new-FailureCode checklist (ledger hashes, TestAccess, ABI rebuild of all consumers).
4. **Round-trip proof, not real positions.** Generate mid-game states by supported random play, export a *full-information* snapshot with a test-only native exporter, import it, and require identical observation, legal-action set, clone result and RNG-independent transcript. Negative tests: one per blocker code in this report (each must fail with its own typed reason), plus partial-field and version-skew inputs.
5. **Preflight bridge only.** `GameState → ImportRequest` is limited to running this stage's analyzer: any blocker ⇒ `ImportRefused(reasons)`. It never fills a gap. Expected result on the current corpus: 100% refused, which is the correct outcome.

Separate, parallel packages (each its own proposal): **IMPORT-1a observation extraction** of the never-populated/absent-tag fields (15 blocker codes) with tri-state semantics and real-log fixtures (hero max Health first; decide explicitly whether "tag absent" may mean false — the extractor currently refuses); **Location** and **Imbue** engine primitives (they dominate this corpus: 67% and 80% of positions); a **Hero Power alias manifest** with evidence; card declarations chosen by the capability-package process, not by this report. The information-set design for opponent/deck gaps stays Phase 4K.8.

**Failure boundaries:** unknown ⇒ refuse; unsupported ⇒ `UNSUPPORTED` typed; unresolved rules ⇒ `RULE_UNRESOLVED`; inconsistent input ⇒ refuse before native construction; engine invariant break after construction ⇒ `ENGINE_DEFECT`, never fallback.

**Evidence required to call IMPORT-1 done:** this analyzer's blocker catalog is the acceptance list; the round-trip suite and per-blocker negative suite pass in the intended configured build with the loaded bridge identity recorded; capability fingerprint and failure-ledger hashes updated; registry/evidence invalidation recorded for the changed native contract; no training admission, no live path.

## 6. Known limits and uncertainties

* **Corpus representativeness.** One player, two decks, one dominant Imbue Priest; 32 independent games. The rankings of codes tied to Imbue/Location/hero 40-Health reflect that deck. The 2 Warrior games are too few to conclude anything about base-power decks.
* **Declaration-level capability.** Verified equal to the native catalog on this build (1,218/1,218); it is not rules verification and says nothing about Standard-pool dependency closure.
* **Applicability rules are conservative heuristics** (entity involvement from the chosen action, draw/heal/Spell Damage from declarations). They do not model triggers; unsupported-card non-involvement is therefore reported as `UNDETERMINED`.
* **Hidden vs observable is a judgement.** SELF deck composition is classed observable (a decklist input) and its order hidden. The two Secret-zone and absent-tag items are classed observable but their resolution needs a reviewed protocol decision.
* **Imbue identity** comes from the repository's own EVIDENCE-0A report, not from this stage's analysis. Skin-like IDs are not assumed to equal their base powers.
* **Board slot numbering** accepts contiguous 0- or 1-based slots (real data is 1-based).
* **Task brief mismatch:** 113 supported card definitions + 4 Hero Powers were found, not 114.
* Hosted CI status is recorded in the final delivery message, not here.

## 7. Reproduce

```powershell
$env:PYTHONPATH = "src"; $env:PYTHONUTF8 = "1"
python scripts/state_import_readiness.py `
  --policy-dir <data>/processed_policy_real/collected --live-dir <data>/raw/live --value-dir <data>/processed_real `
  --sample-size 48 --seed 20261008 `
  --output-dir data/processed_state_import0/run1 --report-dir reports/manaengine_state_import0_20261008
python scripts/state_import_readiness.py --state-json <one state/snapshot/policy record>.json   # single position
```

Running twice produces byte-identical `coverage.json` and `blockers.json`. Inputs are opened read-only and existing output paths are refused unless `--overwrite` is given.
