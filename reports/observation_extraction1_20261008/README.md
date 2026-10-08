# OBSERVATION-EXTRACTION-1 — hero state extraction

**Result: `COMPLETE`.** The Power.log → `GameState` pipeline now keeps the hero's directly observed maximum Health, the hero's explicit Frozen state and the Hero Power's exhausted status, and says "unknown" (`None`) wherever the log does not state them. Nothing is inferred from the hero class, a card's printed values, a missing tag, the Hero Power cost or the available Mana. Gameplay logic, the native engine, model features and checkpoints are unchanged.

Base: `b5b3021786d11dd361058a33efc72663dee8dfce` (the task's baseline; the session's worktree started one commit earlier, so the branch was created at the baseline). Branch: `claude/observation-extraction-1-hero-state`. Not merged. Hosted CI and the final SHA are in section 9.

Everything in this directory is sanitized aggregate counts: no game IDs, handles, player names, opponent hand identities or trajectories. Per-position outputs of the verification run stay in the git-ignored `data/processed_obs1/`.

## 1. Implemented fields

| Field | Meaning | `None` means | Source |
|---|---|---|---|
| `PlayerObservation.hero_max_health: int \| None` (new, last field) | the hero entity's `HEALTH` tag; `hero_health` stays current Health (`HEALTH - DAMAGE`, floored at 0) | `HEALTH` missing, non-integer, bool or `< 1` in the log, or a state from before the field existed | `visible_state._observed_max_health` |
| `hero_frozen` (existed, never filled) | explicit `FROZEN` tag: `1` True, `0` False | no `FROZEN` tag, or a value other than 0/1 | `visible_state._explicit_flag` |
| `hero_power_ready` (existed) | the Hero Power is **not exhausted** (exhausted/used status only; not Mana, target or legality) | see section 4 | `visible_state._hero_power_ready_from_tags`, `live/visibility._option_hero_power_ready` |
| `hero_freeze_turns_remaining` | unchanged: always `None` from Power.log | the log carries no freeze duration (section 4) | — |

`PlayerObservation` validation: `hero_max_health` must be `None` or a positive `int` (bool, float, string, 0 and negatives are rejected, not clamped), and `hero_health` may not exceed a known `hero_max_health` (rejected, not clamped). 40 and higher are valid.

Hero Power **identity** is untouched: `hero_power` is still the card of the (first) `HERO_POWER` entity in play, never derived from the class.

## 2. Verified Power.log tag semantics

Surveyed over the 36 raw `.log` files in `E:\ManaMind\data\raw\collected` (read-only): **28,700 hero observations** (both seats, at every top-level block boundary), by a scratch script that reads raw entity tags through hslog and the project exporter, independent of the new extractor.

**Hero Health.**
- `HEALTH` is present on every hero observation (28,700/28,700). Its values are only 30 and 40; 40 occurs in 9 of the 36 games and changes during a game (the same hero card is seen at 30 and later at 40). So `HEALTH` is the **maximum**, and it is not fixed by the hero card or class.
- `DAMAGE` is logged separately: present on 20,428 observations, absent on 8,272 (undamaged). Current Health = `HEALTH - DAMAGE`.
- `DAMAGE >= HEALTH` occurs on 78 observations: 66 with the hero already in the graveyard (`LOSING`/`LOST`) and 12 in the instant between lethal damage and death. Current Health floors at 0 (existing behaviour); the maximum is not touched.

**Hero Frozen.**
- The `FROZEN` tag exists on only 347 of 28,700 hero observations, in 3 games: 78 with value 1 and 269 with value 0. In the other 28,353 observations the tag is absent.
- Thawing is logged as an explicit `FROZEN` change to 0 (two games show 1 → 0 once it was the frozen player's own turn). An explicit 0 also appears once without a preceding 1.
- In all three games the frozen hero was SELF's (checked against the importer's independent SELF inference); the opponent hero shows only one explicit 0.

**Hero Power exhausted status.**
- Exactly one `HERO_POWER` entity is in play for each side at every observation (28,700/28,700).
- The Hero Power's `EXHAUSTED` tag is present on 19,008 observations (10,157 × 1, 8,851 × 0) and absent on 9,692. `HEROPOWER_ACTIVATIONS_THIS_TURN` on the power is **identical** to it on all 28,700 (absent/absent 9,692, 1/1 10,157, 0/0 8,851).
- The activation-count modifier tags (`HEROPOWER_ADDITIONAL_ACTIVATIONS`, `HEROPOWER_UNLIMITED_USES`, `HERO_POWER_DISABLED`) never occur on the power, the hero or the player in this corpus.
- The options message states exhaustion explicitly. For the 3,632 options messages that mention SELF's or the opponent's Hero Power:
  - `error=NONE` (usable now): 784, tag `EXHAUSTED` was 0 or absent in all 784, never 1;
  - `REQ_NOT_EXHAUSTED_HERO_POWER`: 562, tag was 1 in all 562;
  - `REQ_ENOUGH_MANA`: 401 (225 with the tag absent, 176 with 0), never 1; `REQ_HAND_NOT_FULL`: 69, tag 0;
  - `REQ_YOUR_TURN`: 1,816 (opponent's turn; no information).
- **Replaced powers:** 46 Hero Power identity changes in 31 of 36 games (35 + 4 + 2 of the 46 into the Imbue power `EDR_449p`; the rest into `END_000p` or `CATA_190p`). At the next block boundary the new power carries **no** `EXHAUSTED` tag in 46 of 46 cases, so a fresh replacement is "unknown" until the tag is written or the server states the status.

hslog keeps option `error` values as plain strings (`'REQ_NOT_EXHAUSTED_HERO_POWER'`), not enums.

## 3. Real-log evidence and gaps

Harness: [`verify_real_logs.py`](verify_real_logs.py) re-extracts the raw logs with the new code into a new ignored directory and compares them with the datasets the previous code produced. Output: [`real_log_verification.json`](real_log_verification.json). Inputs (all read-only): 36 raw logs, the historical policy dataset (32 games / 1,227 decisions), the 12 recorded live sessions, and the newest canonical policy dataset written by the previous code (`refresh_20261008`).

| Check | Result |
|---|---|
| Policy re-extraction | 32 games / 1,227 SELF decisions (4 logs rejected as `GAME_RESET`, same as before) |
| Same decisions, actions, chosen action and final result as the previous dataset | **1,227 of 1,227** identical |
| States that changed other than the three fields below | **0** (`unexpected_changes: {}`), for the policy comparison and for the 635 replayed live snapshots |
| Live replay determinism (12 recorded games, replayed twice) | 12 of 12 identical hashes |
| Previous canonical dataset (1,227 rows, no `hero_max_health`) under the new strict validator | 1,227 of 1,227 valid |
| Chosen-action rows with a Hero Power action (124) | `hero_power_ready` is True in 124 of 124 (never False) |

Observed values in the 1,227 policy decisions (SELF / OPPONENT):

| | SELF | OPPONENT |
|---|---:|---:|
| `hero_max_health` 30 / 40 / unknown | 1,227 / 0 / 0 | 771 / 456 / 0 |
| hero damaged / undamaged | 567 / 660 | 644 / 583 |
| `hero_frozen` True / False / None | 4 / 15 / 1,208 | 0 / 0 / 1,227 |
| `hero_power_ready` True / False / None | 693 / 390 / 144 | 386 / 568 / 273 |

Changes against the previous extraction of the same decisions (policy): `hero_max_health` absent → 30 in 1,998 and → 40 in 456 seat-observations; `hero_frozen` None → False in 15 and → True in 4 (all SELF); `hero_power_ready` None → True in 137 (all SELF, settled by the server's options message). In the offline Value path (2,912 positions) the same extractor gives max Health 30 / 40 and explicit Frozen for 86 positions; its `hero_power_ready` gaps are unchanged because the offline importer has no options message.

Coverage in this corpus: ordinary 30-Health heroes, 40-Health heroes (9 games; in the policy decisions the 40-Health hero is always the opponent's, in the Value path a SELF hero also reaches 40), damaged and undamaged heroes, explicit Frozen True/False (SELF), SELF and OPPONENT ownership, known and unknown readiness, and Imbued/replaced powers (46 replacements).

**Gaps, stated as not verified against a real match:** explicit Frozen for the opponent hero at a SELF decision (0 cases); a Hero Power with extra activations, unlimited uses or a disabled flag (0 cases; guarded, see below); two Hero Powers in play at a block boundary (0 cases); a 40-Health SELF hero at a labelled policy decision (0 cases). These rules are covered by synthetic tests only, which are labelled as such in `tests/test_hero_state_extraction.py`.

## 4. Known and unknown behaviour

**`hero_max_health`** is `None` only when `HEALTH` is missing or unusable; in the real corpus it was never missing. It is never 30 by default.

**`hero_frozen`** is True/False only from an explicit `FROZEN` tag. **A missing tag is unknown, not False**, as instructed. In the corpus that leaves 98.8% of hero observations (28,353/28,700) unknown. The `FROZEN` tag is only written once a hero is first frozen, and the stream is otherwise delta-based, so a missing tag is *probably* a never-frozen hero, but nothing in the log states it and the project rule is not to assume it. Whether to adopt a "never-set means False" protocol rule is a separate decision (section 8).

**`hero_freeze_turns_remaining`** stays `None`. The log carries a boolean only. When the hero thaws depends on whether the freeze happened before or after the hero attacked and on whose turn it is; reconstructing a duration would be a rules model, not an observation, and only two thaw events exist in the corpus.

**`hero_power_ready`** (exhausted status, True = not exhausted):

1. The power's explicit `EXHAUSTED` tag decides: 0 → True, 1 → False, absent → unknown. Mana, cost, class and the absence of the tag are never used.
2. The extractor returns `None` instead when `HEROPOWER_ACTIVATIONS_THIS_TURN` disagrees with `EXHAUSTED`, when `HEROPOWER_ADDITIONAL_ACTIVATIONS`, `HEROPOWER_UNLIMITED_USES` or `HERO_POWER_DISABLED` is non-zero on the power or the player (none occurs in the corpus, so those rules are unverified), or when the side does not have exactly one Hero Power in play.
3. For SELF **decisions** the live path also uses the server's own options message: a validated option for the Hero Power (`error=NONE`) means not exhausted, `REQ_NOT_EXHAUSTED_HERO_POWER` means exhausted. It only fills an unknown value; if it contradicts the tag the result is `None`. Other errors (`REQ_ENOUGH_MANA`, `REQ_HAND_NOT_FULL`, `REQ_YOUR_TURN`) are ignored. This resolved 137 of the 281 unknown SELF values in the policy decisions (48.8%). The opponent has no options message, so its flag is tag-only.
4. Identity and readiness are independent: an Imbued power (`EDR_449p`) or a replaced/skin power (`HERO_09dbp`) keeps its own card ID and gets the readiness of its own entity. No rules are attached to any power ID, and nothing is aliased.
5. For the non-active side the flag is the stored exhausted status (an opponent power used last turn stays exhausted until their next turn), the same meaning the native engine's `hero_power_ready` has.

## 5. Old and new serialization compatibility

- `game_state_from_dict` reads a missing `hero_max_health` as `None` (never 30); an explicit `null` is also `None`; invalid types and values are rejected.
- `state_to_dict` (policy rows, live snapshots, every `state_hash`) writes `hero_max_health` **only when it is known**. A state whose maximum is unknown therefore serializes to exactly the dictionary and hash it had before the field existed, and the strict policy validator (`state_to_dict(game_state_from_dict(row)) == row`) still accepts earlier rows: the newest canonical dataset written by the previous code (1,227 rows) validates unchanged. An explicit `null` is rejected as non-canonical (tested). Writers that use `dataclasses.asdict` directly (Value examples, trajectory fingerprints) emit `null` for an unknown maximum and load back to the same state.
- The very first historical policy dataset (`processed_policy_real/collected`) already failed the strict validator **before** this change, because it predates `healing_bonus`. That is the reason the canonical rebuild exists; it is not caused here.
- `SNAPSHOT_SCHEMA` stays `manamind.live.snapshot/1`: the envelope is unchanged and the new state key is optional and additive. Recordings made before this change do not replay to their recorded `state_hash` values (the replayed states now carry the new fields); `scripts/live_replay.py <recording>` on an old recording reports a mismatch by construction. Replay of the same recording under the new code is deterministic (12 of 12).
- `STATE_ENCODING_SCHEMA_VERSION` stays 16. `hero_max_health` is not an encoder or Policy v2 feature: encoded tensors and feature names are identical for any maximum (tested). **Input values of two existing features do change** for newly extracted data: `hero_frozen` (and Policy v2's `hero_frozen`/`hero_frozen_known`) and `hero_power_ready` are now ±1 instead of 0 where the log states them (policy decisions: 19 and 137 of 1,227 rows). Checkpoints still load; models trained on the old values have not seen these inputs.
- ManaEngine: the native observation exports no hero maximum Health (`ObservedPlayer` has no such field), so the adapter leaves the shared field `None`. `experiments/manaengine/tests/test_hero_max_health_contract.py` fails if the native export ever gains the value, so the adapter and the analyzer are updated together. No native source, ABI or rules changed; no native rebuild was needed.

## 6. State-import readiness diagnostics

`state_import_readiness.py` (`ANALYZER_VERSION` `state-import-0/1` → `state-import-0/2`; the historical report was **not** regenerated):

- Removed the unconditional `HERO_MAX_HEALTH_NOT_REPRESENTED`.
- `HERO_MAX_HEALTH_UNKNOWN` (UNKNOWN, source, observation extraction): the maximum is `None` or absent, including every state from earlier extractors.
- Known and valid: no blocker; the position reports `known.hero_max_health` per seat as `KNOWN_SUPPORTED_NATIVE`.
- `HERO_MAX_HEALTH_UNSUPPORTED_NATIVE` (UNSUPPORTED_MECHANIC, native, engine primitive): observed maximum other than the native fixed 30, including a damaged hero below 30 (`HERO_HEALTH_EXCEEDS_NATIVE_MAX`, which needs current Health above 30, is kept and counts a subset).
- Inconsistent Health (current above maximum, or a maximum that is not a positive integer): `INTEGRITY_ENTITY_RANGE` (and `INTEGRITY_STATE_REJECTED`, because `GameState` rejects it); never reported as a supported or unsupported maximum.
- `HERO_FREEZE_UNKNOWN` now fires for an unknown Frozen state or for a frozen hero without a duration; an explicitly unfrozen hero needs no duration. `HERO_POWER_READINESS_UNKNOWN`'s description now names the evidence that was tried.
- `FIELD_PROVENANCE` updated (`hero_max_health`, `hero_frozen`, `hero_power_ready`); the test that every `PlayerObservation` field has provenance caught the new field.

## 7. Quantitative change in observational blockers

Same analyzer (`state-import-0/2`), same seed and sampling, run on the previous extraction and on the new extraction of the same 32 games (policy) / 12 games (live replays) / 36 matches (Value). Output of both runs stays in `data/processed_obs1/` (ignored); the commands are in section 10.

| Policy decisions, 1,227 positions / 32 games | previous extraction | new extraction |
|---|---:|---:|
| `HERO_MAX_HEALTH_UNKNOWN` | 1,227 (32 games) | **0** |
| `HERO_MAX_HEALTH_UNSUPPORTED_NATIVE` (a typed native gap, previously hidden behind "unknown") | — | 456 (8 games) |
| `HERO_HEALTH_EXCEEDS_NATIVE_MAX` | 342 (8) | 342 (8) |
| `HERO_FREEZE_UNKNOWN` | 1,227 (32) | 1,227 (32) |
| `HERO_POWER_READINESS_UNKNOWN` | 281 (32) | **144** (32), −48.8% |
| Hero Power subsystem, visible fields sufficient | 77.1% | 88.3% |
| Hero subsystem, visible fields sufficient | 0% | 0% |
| `OBSERVATION_EXTRACTION` blocker codes observed | 15 | 14 |

Live replays (635 positions / 12 games): `HERO_POWER_READINESS_UNKNOWN` 123 → 54, Hero Power subsystem sufficient 80.6% → 91.5%, `HERO_MAX_HEALTH_UNKNOWN` 635 → 0. Value examples (1,348 SELF positions): max Health 1,348 → 0 unknown; readiness unchanged (287), as expected without options.

Every position is still blocked: hero maximum Health was one of the 12 universal blockers, so removing it does not change the headline "0 of 1,227 hydratable". Hero Divine Shield, healing bonus, turn counters, minion-type history, player effects and hidden information are untouched, and `HERO_FREEZE_UNKNOWN` remains in all 32 games because the opponent's Frozen state is never explicit at a SELF decision and SELF's is explicit in 19 rows only.

## 8. Remaining unresolved cases

1. **Missing `FROZEN` tag** (98.8% of hero observations): left unknown by instruction. A protocol-level "never-set tag is False" rule would make nearly all of them known, but is not adopted here. It needs a deliberate decision and, ideally, an independent check.
2. **Freeze duration**: not in the log; needs a rules model of thaw timing.
3. **Hero Power readiness still unknown**: SELF 144 of 1,227 decisions (tag absent and the server's error is not an exhaustion statement, e.g. `REQ_ENOUGH_MANA` on a power whose tag was never written, 225 such option messages); OPPONENT 273 (tag only); every fresh replacement power (46 of 46 had no tag at first sight). `REQ_ENOUGH_MANA` coincides with "not exhausted" in 401 of 401 messages, but the server's check order is not documented and this is not used.
4. **Extra activations, unlimited uses, disabled powers**: no corpus evidence; guarded to unknown.
5. **Native 40-Health behaviour and hero Divine Shield**: not implemented (out of scope); the analyzer now reports the 40-Health gap with its true maximum.
6. **Recordings made earlier** do not reproduce their stored hashes under the new extractor (section 5).
7. **Corpus limits** are those of ENGINE-STATE-IMPORT-0: one player, 32 independent games; SELF is never frozen at an opponent-turn decision, and no 40-Health SELF hero reaches a labelled policy decision.

## 9. Tests and hosted CI

Local (Windows, `E:\ManaMind\.venv`, pinned RosettaStone submodule checked out):

- `ruff check src tests scripts`: passed. `check_generic_card_branches.py`: pass. Failure-site audit `check`: 0 problems. `check_generated_artifacts.py` (run twice): 36 pinned outputs reproduced. `git diff --check`: clean.
- `pytest tests experiments/manaengine/tests`: **776 passed, 1 skipped** (native tests ran against an existing `build-release` of the identical `b5b3021` native sources, because this change touches no native file; no new native evidence is claimed).
- New: `tests/test_hero_state_extraction.py` (80 tests: current 20/30 and 35/40, missing/invalid maximum, overkill, Frozen true/false/unknown for both seats, Hero Power tri-state, mana independence, Imbued/replaced/two-power cases, historical and exact round trip, canonical hash, encoder invariance, schema checks, offline-importer end-to-end for both perspectives, live session with every option error, conflict handling, privacy canaries, determinism, historical policy-row validation); updated `tests/test_state_import_readiness.py` (new blockers, four outcomes, freeze cases, provenance); `experiments/manaengine/tests/test_hero_max_health_contract.py`.
- Existing real-Policy import, dataset, live session, tail, replay and recommendation tests pass unchanged.

Hosted CI: *pending at the time of writing; recorded in the delivery message and the follow-up commit below.*

## 10. Dataset identities and whether a canonical Policy rebuild is needed

**Yes, if the new fields should be in the training data; no for validity.** Datasets written by the previous code (including the newest canonical `refresh_20261008`) remain loadable and valid, but they lack `hero_max_health`, explicit Frozen and the options-based readiness, and they were built from a source revision whose importer fingerprint this change alters. Do not mix old and new rows in one dataset, and do not split a match between them.

Exactly what changes in a state built from the same raw match:

| State path | Changes when | In the 1,227 policy decisions |
|---|---|---|
| `self_player.hero_max_health`, `opponent.hero_max_health` | a key appears whenever `HEALTH` is valid | all 2,454 seat-observations |
| `self_player.hero_frozen` / `opponent.hero_frozen` | None → True/False on an explicit `FROZEN` tag | 19 / 0 rows (Value path: 79 / 7 positions) |
| `self_player.hero_power_ready` | None → True/False from the tag or, live path only, the options message | 137 rows |
| `opponent.hero_power_ready` | only if the tag contradicts the activation counter or a modifier applies | 0 rows |
| every other state field, action, label, result | — | unchanged (0 differences) |

Identities that change: each policy row's `state` and `provenance.state_hash`; any dataset or content fingerprint built from them (including the importer-source fingerprint of ML-DATA-REFRESH-1, which covers the files changed here); Value `match_fingerprint` and `_examples_fingerprint` (they hash `asdict(state)`, which now has the `hero_max_health` key); live `state_hash` values and recordings' replay hashes; the state hashes the EVIDENCE walker computes (it uses `to_visible_state`); `observation_source_sha256` in `data/cards/standard_registry_20261001_enUS.json` and `reports/standard_registry_20261001/summary.json` (regenerated; registry evidence was already stale, 0 current). Unchanged: `game_id`, `decision_id`, selection and options line numbers, legal actions, labels, the state encoding schema, vocabularies and checkpoints.

**Integration order (not performed here):** do not merge this branch before the data-refresh order is reviewed. Merging this branch first and then running ML-DATA-REFRESH-1's canonical rebuild once on the final source revision avoids a second rebuild; if the refresh lands first, its dataset stays valid but should be rebuilt after this merge if the new fields matter. I did not run any rebuild, and touched no raw log, dataset, checkpoint, Codex branch or worktree, `work/ui-overlay-shell` or `codex/ml2a-policy-v2`.

## 11. Reproduce

```powershell
$env:PYTHONPATH = "src"; $env:PYTHONUTF8 = "1"
python reports/observation_extraction1_20261008/verify_real_logs.py `
  --raw-dir <data>/raw/collected --old-policy-dir <data>/processed_policy_real/collected `
  --canonical-baseline-dir <data>/processed_policy_real/refresh_20261008 --live-dir <data>/raw/live `
  --workdir data/processed_obs1/run1 --summary reports/observation_extraction1_20261008/real_log_verification.json
python scripts/state_import_readiness.py --policy-dir <data>/processed_policy_real/collected --live-dir <data>/raw/live `
  --value-dir <data>/processed_real --output-dir data/processed_obs1/run1/analysis_old_data/positions `
  --report-dir data/processed_obs1/run1/analysis_old_data/report
python scripts/state_import_readiness.py --policy-dir data/processed_obs1/run1/policy --live-dir data/processed_obs1/run1/live `
  --value-dir data/processed_obs1/run1/value --output-dir data/processed_obs1/run1/analysis_new_data/positions `
  --report-dir data/processed_obs1/run1/analysis_new_data/report
```

The harness refuses a non-empty `--workdir` and never writes into its inputs.
