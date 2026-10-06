# EVIDENCE-0B — Unsupported-card evidence extractor: completion report

**Verdict: `EVIDENCE0B_EXTRACTOR_READY`** (pre-merge follow-up in section 4a: verdict `EVIDENCE0B_PREMERGE_READY`)

Date 2026-10-06. Python only. No ManaEngine, ML, policy, live, registry, card-declaration, config or overlay file was changed; no support status is written anywhere. Operating guide: [docs/EVIDENCE_PIPELINE.md](../../docs/EVIDENCE_PIPELINE.md).

## 1. Provenance

| Item | Value |
|---|---|
| Base | `origin/main` = `33fc46d3dd6fd3d44f654ff1ee4da29df0211ce1` ("docs(evidence): design real-log mechanic discovery"). At the end of the task `origin/main` had advanced to `6c7159b` (ML-1C: `configs/real_policy_ml1c.json`, training/metrics modules, `scripts/train_real_policy.py`, docs/report/test); none of those paths overlap this change. |
| Branch | `work/evidence0b-unsupported-card-extractor` (local, not merged, not pushed). |
| Parsers | `hslog` 1.20.0, `hearthstone` 9.21.1. |
| Extractor version | `evidence-0b.1`. |
| Files added | `src/manamind/evidence/` (13 modules), `scripts/extract_evidence.py`, `docs/EVIDENCE_PIPELINE.md`, `tests/evidence_fixtures.py`, `tests/test_evidence_{extractor,pipeline,boundary}.py`, this report. |

## 2. Architecture

One pass per completed game section, one fresh `hslog` parser per game (the collector rule), the existing `PacketExporter` applying every packet exactly once in pre-order so "before" values are what the client had at that moment.

| Module | Role |
|---|---|
| `walker.py` | Walks the packet tree, **descending into `Block` and `SubSpell`** (SubSpell is transparent: its packets belong to the enclosing block). Produces one *window* per root block with *units* (nested blocks), typed *events* with entity views captured at event time, the last `Options` snapshot, and public before/after states (`to_visible_state(..., opponent_identity_policy="none", hand_order="zone_position")`, stored as hashes and a coarse delta). |
| `entities.py` | Entity views, the `Redactor` (default-deny visibility; hidden opponent identities become `card_id: null`). |
| `attribution.py` | `CREATOR_TAG` (following enchantment-of-enchantment chains) > `LAST_AFFECTED_BY_SAME_UNIT` > `UNIT_OWNER` > `UNATTRIBUTED`; root `PLAY`/`ATTACK` own packets are not credited to the source (R1); relative to a subject, anything attributed elsewhere is `NESTED_ONLY`. |
| `facts.py` | Typed facts only: block/target/cost, damage and healing packets (META paired with the tag changes it caused in the same unit), zone moves, deaths, creations, transforms, reveals, enchantment attach/remove, stat/keyword/control deltas, choices, server `TARGET_LEGALITY`, step context. |
| `inferences.py` | Derived statements with non-empty `inputs`, assumptions and a weakest-input visibility: `DEATH_BY_DAMAGE`, `DESTROY_WITHOUT_DAMAGE`, `DIVINE_SHIELD_ABSORBED`, `STAT_CHANGE_[UN]EXPLAINED…`, `BATTLECRY_FROM_OWN_POWER_BLOCK`, `REPEATED_TRIGGER_COUNT`. |
| `confounders.py` | `FOREIGN_ENCHANTMENT_ACTIVE`, `FOREIGN_UNIT_WITH_EFFECTS_IN_WINDOW`, `STALE_LAST_AFFECTED_BY`, `MISSING_CREATOR_TAG`, `MULTIPLE_OWNER_UNITS`, `AURA_RECALC_OUTSIDE_BLOCK`, `MODE_OR_BUILD_OUTSIDE_SCOPE`, each with the claim kinds it can affect. |
| `observation.py` | Subjects (played card, hero power, Location, attacker, and any unit owner with semantic effects), one observation per (window, subject), `attribution_summary`, fixed `evidence_limits`. |
| `support.py` | `SupportInventory` (exported inventory, or `DECLARATION_PROXY` from `card_abilities.json`; basis is mandatory in every record), registry scope. |
| `extract.py` / `pipeline.py` | Game gate and SELF resolution, then the multi-game run, deterministic output, privacy scan. |
| `schema.py` / `privacy.py` | Structural validator (a fact never has `inputs`, an inference always does, `model_input_allowed` is constant `false`); scan of the output against identifiers read from the input. |

Gates (skip with a fixed reason code, never text): not Ranked Standard (`UNSUPPORTED_MODE`, or tagged `OTHER_MODE_SECONDARY` with `--include-secondary`), incomplete, mid-game start, `GAME_RESET`, SELF unverified/disagreeing.

SELF is resolved by the project's hand-identity rule and **must** be confirmed by the server's own validated options; disagreement or no confirmation skips the game. The options message can arrive after the opponent's first play, so the cross-check keeps scanning past it (tested with both player orders).

## 3. Deviations from EVIDENCE-0A (all conservative; none changes an architectural conclusion)

1. **`line_in_game` → `packet_ordinal`.** hslog packets carry no source line, so facts point to the pre-order ordinal of the packet in the game's tree and the window to `root_packet_ordinal`. No raw text either way.
2. **Hidden identities are redacted, not stored.** 0A allowed `OFFLINE_ONLY_HIDDEN` payloads in the offline lane; the extractor emits `card_id: null`, `card_type: null`, keeps the visibility label, and adds `privacy.hidden_fact_count`. This is the minimum the privacy brief asks for and loses no claim 0A needs (outcome-only claims rest on public outcomes).
3. **`UNKNOWN_TAG_IDS_IN_WINDOW` is not emitted as a confounder.** Measured on the corpus: unknown ids changed in 98 % of subject windows, and still on 77 % of the entities a subject acts on (client bookkeeping), so it would mark nearly everything. The ids stay in `provenance.unknown_tag_ids_in_window`; the enum value remains in the schema.
4. **`LAST_AFFECTED_BY` is accepted anywhere inside the same unit, not only before the effect.** The client logs it *after* the damage/stat packet (observed on the real corpus); a value not set inside the unit is still never used and is reported as stale.
5. **R1 also guards root `ATTACK` blocks** (their own damage/retaliation packets are `UNATTRIBUTED`).
6. **Schema additions:** `CONTROL_CHANGE` fact kind, triage `CONTROL_UNCOMPARED` for control samples (no engine expectation exists, so `KNOWN_EXPECTED` would be false), `attribution_summary` (`tier`, `ambiguous`, `confounded_claim_kinds`), `evidence_limits`, `facts_truncated`, `via_creator_chain`, `privacy.hidden_fact_count`, nullable state hashes before the first turn.
7. **Not implemented, by design of this task:** aggregation, review queue, claims and tiers; condition predicates (`CONDITION_EVALUATED_FROM_BEFORE_STATE`, `HIDDEN_CONDITION_IMPLIED_BY_OUTCOME`, `CANDIDATE_SET_FROM_BEFORE_STATE`, `SPELL_DAMAGE_OR_MODIFIER_PRESENT`) because they need an independently reviewed predicate, not a guess from the log; full public states (hashes + delta only).

## 4. Real validation (read-only, aggregates only)

Inputs: `data/raw/collected`, `data/raw/Power.log`, `D:\Games\Hearthstone\Logs`; nothing was written there. Output went to the session scratchpad and is not committed.

**Corpus.** 40 distinct complete games (as in 0A): 25 Ranked Standard, 15 other modes. Processed 21; skipped 4 (`GAME_RESET`, a deliberate gate shared with the policy importer) and 15 non-primary.

**Structural parity with 0A on the 25 Ranked Standard games** (all games, resets included): root blocks 9,303 / PLAY 1,450 / TRIGGER 7,192 / ATTACK 454 / DEATHS 166 / DECK_ACTION 35 / GAME_RESET 6 — **all identical to the audit**; PLAY windows with a foreign TRIGGER child 89.7 % (audit 89 %); every enchantment creation carries both `CREATOR` and `ATTACHED` (100 %, as audited). Enchantment creations: **1,102** after the pre-merge fix in section 4a (the first version reported 921 against the audit's 1,171).

**Extraction output (21 processed games, 7,528 windows).**

| Measure | Value |
|---|---:|
| Observations / distinct subject cards | 2,153 / 423 |
| Unsupported-subject observations / control samples | 2,088 / 65 |
| Roles | played card 806, enchantment source 349, attacker 328, hero power 183, trigger 149, deathrattle 95, Location 91, turn-phase 87, control 65 |
| Attribution tier | creator-or-same-unit 1,400 · unit-owner-only 409 · no attributed effects 344 |
| Observations flagged ambiguous (conservative) | 933 (43 %); 1,062 have no confounder at all |
| Facts by basis | unit-owner 11,306 · nested-only 5,103 · unattributed 4,383 · creator-tag 1,755 · last-affected-by-same-unit 1,401 |
| Confounders | foreign enchantment 967 · foreign unit 722 · stale last-affected-by 417 · missing creator 135 · multiple own units 94 · aura recalculation 5 |
| Server legality facts (selected plays only) | 1,023: 794 accepted; rejections `REQ_MINION_TARGET` 182, `REQ_HERO_OR_MINION_TARGET` 28, `REQ_CAN_BE_TARGETED_BY_SPELLS` 12, others 7 |
| Inferences | stat change explained 1,165 / unexplained 294 · death by damage 469 · destroy without damage 182 · battlecry-from-own-power 353 · repeated trigger 54 |
| Observations containing redacted hidden facts | 645 |
| Support basis | `DECLARATION_PROXY` (2,079 no declaration, 9 declared unsupported) |

### 4a. Pre-merge follow-up: the enchantment-creation discrepancy (921 vs 1,171)

Counted independently from the packet tree of the same 25 Ranked Standard games (all in-block, `SubSpell` included, resets included):

| Definition | Count |
|---|---:|
| `FULL_ENTITY` whose own tags say `ENCHANTMENT` | 12 |
| `FULL_ENTITY` whose end-of-game type is `ENCHANTMENT`, in blocks (394 directly, 675 inside `SubSpell`) | 1,069 (+7 outside any block) |
| of those, entities completed by a `SHOW_ENTITY` | 1,067 of 1,076 |
| Distinct enchantment entities alive at game end | 1,057 |
| Extractor v1 (type read at the end of the creating window) | 921 |
| Extractor after the fix | 1,102 |

**Cause: a real loss in v1, now fixed.** The client frequently logs `FULL_ENTITY` with an empty card id inside a block and sends the `SHOW_ENTITY` that carries `CARDTYPE`, `CREATOR` and `ATTACHED` in a **later root block** (about 150 enchantments in the non-reset games alone). v1 snapshotted entities at window end, so those creations were typed unknown and had no creator. Ruled out: `SubSpell` traversal (675 of the creations are inside `SubSpell` and were counted), deduplication (only 19 reused handles, all in `GAME_RESET` games), root/unit boundaries, observation filtering (the count is taken from raw creation events before any subject filter), and `GAME_RESET` exclusion (the measurement includes reset games; extraction still skips them).

**Fix** (`Walker._enrich_late_creations`): creations still missing card id or type at window end take card id, type, `CREATOR` and `ATTACHED` from the end-of-game entity, while zone and controller stay as seen at window end so visibility is decided by what was public *then*. Measured effect on the 21 processed games: creator-tag attributions 1,458 → 1,755, missing-creator confounders 240 → 135, redacted-hidden observations 497 → 645; the independent hidden-identity check still finds 0 leaks. Regression test: `test_creation_completed_by_a_later_root_block_is_not_lost` (fails without the fix).

**Residual.** 1,102 now exceeds every packet-level count I can construct (1,069 in blocks; the extra ~33 are entities that were enchantments at window end but were reset or retyped later in `GAME_RESET` games, which extraction skips). The audit's 1,171 is **not reproduced** by any definition tried (FULL_ENTITY with final type, SHOW_ENTITY with `ENCHANTMENT` type = 1,094 in blocks + 7 outside, entities alive at end, creations with a creator); it is about 6 % above the extractor and 10 % above the nearest independent packet count, and its counting rule is not stated in 0A. No evidence indicates that the extractor still drops observable creations, but this number was not matched and the audit figure should not be reused as a target. Not covered: identity enrichment of non-creation `SHOW_ENTITY` reveals that arrive after their window.

**Privacy.** The run's own scan checked the output against 142 identifiers (names, BattleTags, account fragments) taken from the input: **0 leaks**. An independent check recomputed, per game, the opponent-side identities that never became public (never in PLAY/GRAVEYARD and never SELF-controlled): 50 such identities (40 distinct ids) across the 32 games SELF could be resolved for, **none appears in that game's output**. A first version of that check flagged ids that had been public earlier in the game; the corrected definition is the one above.

## 5. Tests

`tests/test_evidence_extractor.py` (22), `test_evidence_pipeline.py` (9), `test_evidence_boundary.py` (3); synthetic logs only. Covered: SubSpell creation; foreign nested triggers and the empty-watcher count; CREATOR beating block owner in both directions and enchantment chains; same-unit `LAST_AFFECTED_BY` versus a stale value; foreign enchantment rewriting an effect; unattributed root packets and ambiguity; no-op windows with no negative claim; RNG outcomes as single draws; inferences as non-facts; supported/unsupported filtering with the control-sample cap; server legality evidence; opponent plays; hidden-information canaries (opponent hand/deck/secret, `OVERRIDE_HISTORY`, show-then-hide); SELF in both player orders, opponent-first, disagreement and no cross-check; unknown tag ids and numeric trigger keywords; client build and mode (`OTHER_MODE_SECONDARY`); incomplete games; determinism, dedup, refusal to overwrite, version-keyed ids; privacy canary in every output file, stdout/stderr and exception paths; leak ⇒ run fails and output removed; static import boundary and no-write-path checks; schema rejection cases. Six deliberate mutations (drop SubSpell, ignore CREATOR, expose everything, drop the root guard, ignore same-unit last-affected-by, drop NESTED_ONLY) each fail at least one test.

Verification: `ruff check .` clean; full `pytest` 412 passed, 1 skipped (requires the RosettaStone submodule checked out in the worktree); `git diff --check` clean; `scripts/check_generated_artifacts.py` exits 0 and leaves the tree unchanged.

## 6. Known attribution limitations

* `UNIT_OWNER` inside a non-root unit means "this block's source", which is structural, not proven cause; consumers must use the basis, never the unit alone.
* Stat deltas on other entities are not credited to anyone (`UNATTRIBUTED`); an enchantment lifecycle only explains them as an inference. 294 stay unexplained.
* `META DAMAGE`/`HEALING` is paired with the next tag changes on its target inside the same unit; an unmatched `DAMAGE` change appears as a plain `STAT_DELTA`.
* Simultaneous or chained triggers keep their log order only; the firing event is not recorded by the client.
* Opponent quests/secrets sitting in the `SECRET` zone stay hidden, so they are never subjects (counted in `subjects_skipped_hidden_identity`).
* Every `SHOW_ENTITY` after an `OVERRIDE_HISTORY` in the same unit is treated as hidden for non-SELF entities (default deny; can hide a legitimately visible reveal).
* Legality evidence covers only the latest `Options` message before each SELF play, not every decision point (the 0A demand measure needs a separate pass).
* Choice facts are capped at `SELF_PRIVATE` (candidates can be the opponent's deck contents).
* `GAME_RESET` games (4 of 25) are skipped, so their cards are absent.
* The support state is a declaration proxy; it can mis-state support in both directions (engine-native cards without a declaration look unsupported). Under it, enchantment tokens and hero powers count as unsupported subjects.
* Ambiguity is deliberately over-reported at the observation level; the claim-level filter is `confounded_claim_kinds`.

## 7. What is captured reliably now

Root-window structure with unit owners and relation to the subject; direct damage/healing packets with target, amount, tag deltas, shield pops; summons, generated cards and enchantments with `CREATOR`/`ATTACHED` (including those inside `SubSpell`); transforms; deaths and zone moves; choice offers and picks; server-validated target legality with the server's own error codes; per-fact visibility and redaction; explicit foreign-effect and modifier confounders; build, mode and parser provenance; deterministic, re-runnable, name-free bundles.

## 8. Next bounded task

**EVIDENCE-0C — card aggregates and review dossiers (Python only, offline).** Consume `observations.jsonl` (all `rules_scope` kept apart) and produce per-card aggregates with typed claims, games as the unit of independence and the 0A tier scale (`T0`–`T3`, `CONTRADICTED`, fixed `never_claimed` list), using only facts that are non-`NESTED_ONLY`/non-`UNATTRIBUTED` and whose claim kind is not in `confounded_claim_kinds`; descriptive context counts (never "cannot"); legality requirement codes seen; outcome sets with unseen-mass as information only; plus a per-card review dossier. Prerequisites to settle first: an exported engine support inventory (replace the proxy) and a decision on admitting `GAME_RESET` games. It must still not write rules, manifests, registry status, fixtures or engine code.
