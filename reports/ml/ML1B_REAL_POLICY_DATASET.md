# ML-1B — Real supervised action dataset

Base: `18e328a1365aa1c201924736376386f841c67b0e` (accepted LIVE-0B).
Branch: `work/ml1b-real-policy-dataset`. This task does not promote main.

## Schema and boundaries

Each JSONL row is exactly one admitted SELF MAIN_ACTION decision:

| Field | Contract |
|---|---|
| `schema_version` | 1, real policy dataset; separate from Value JSONL |
| `action_schema_version` | 1, semantic action descriptor |
| `game_id` | SHA-256 of the collector's CREATE_GAME header, before player names |
| `decision_id` | game_id plus server options-message ID; grouping/provenance only |
| `state` | LIVE-0B player-visible GameState, before selection |
| `legal_actions` | complete admitted MAIN_ACTION set, expanded by legal targets and placement |
| `chosen_action_index` | exactly one member, derived from SendOption, never match outcome |
| `final_result` | SELF win 1.0 / loss 0.0 / draw 0.5, retained as auxiliary supervision |
| `source` | `power_log_ranked_standard` |
| `provenance` | options line, selection line, canonical before-state hash; non-model data |

The model receives only state and legal actions. Match/decision IDs, result,
provenance, future events and raw handles are excluded by `encode_example`.
Action descriptors retain visible source/target card IDs, kind, side, current
stats, shared board position, SELF hand index and play insertion slot. Missing
stats remain null. Raw entity/option handles stay in the matching layer.

The importer independently checks each section's mode, completion, SELF and
result. Spectator input, reconnect starts, GAME_RESET, inconsistent metadata,
failed parsing/trust and unresolved result cannot be imported. It reads raw
logs without copying or changing them. Default policy outputs are ignored
`data/processed_policy_real/`, never `data/processed_real/`. Each game also has
an aggregate `.audit.json`; duplicate matches/files are refused.

## Exact action matching

1. Read a complete DebugPrintOptions message. The next line proves the message
   boundary offline; the actual LIVE client task-list settle gate must pass.
   Project state through LIVE SELF resolution and visibility, before processing
   subsequent state changes or selection.
2. Include server-validated roots/targets only. END_TURN with `error=INVALID`
   is included when active_player is SELF, including end-turn-only menus.
3. Map supported kinds: PLAY_CARD, ATTACK (hero/minion), HERO_POWER,
   ACTIVATE_LOCATION, END_TURN. Expand all valid entity targets. Minion/Location
   plays enumerate one-based insertion positions 1..public shared board size+1,
   under the existing seven-slot board contract; non-placement actions use 0.
4. Keep a private exact key `(option ID, sub-option ID, target entity handle,
   selected position)` for each semantic action. SendOption must match exactly
   one key. No localized-name or nearest-action matching is used.
5. Any intervening GameState message before SendOption supersedes the candidate.
   Two sends for one options epoch invalidate the label. Duplicate source
   variants are ambiguous even when another variant has an error: an
   unaffordable normal PLAY must not turn a valid Trade/Forge into PLAY_CARD.
   Known alternate hand powers and unestablished minion powers are excluded.
6. Every selected non-END_TURN action requires a subsequent public block with
   the same actor handle, before the next options message: ATTACK for an attack,
   PLAY for a card, hero power or Location activation. The raw entity descriptor
   is parsed by hslog for its handle. A HAND POWER that produces DECK_ACTION
   is not a PLAY_CARD label. Future blocks serve admission verification only;
   they never alter the before-state/actions passed to the model.
7. Skip the entire decision if any legal action cannot be represented completely.
   Sub-options use CHOICE_UNRESOLVED. Discover and mulligan are not admitted.

Stable reasons include AMBIGUOUS_SELECTION, TARGET_UNRESOLVED,
CHOICE_UNRESOLVED, OPTIONS_SUPERSEDED, PARSE_ERROR, SELF_AMBIGUOUS,
UNSUPPORTED_DECISION_KIND and NO_SELECTION. The audit validates count
consistency, canonical state/action fields, chosen membership and duplicate IDs.

## Real local validation (aggregate only)

30 input files were read, including two existing local LIVE recordings;
43 game sections were inspected. 21 unique completed Ranked Standard matches
were admitted (12 wins, 9 losses). Game-level exclusions: 8 duplicate copies,
10 ineligible-mode sections, 4 GAME_RESET sections.

| Decision fact | Count |
|---|---:|
| SELF decisions observed | 922 |
| Exactly labeled | 736 |
| Skipped | 186 |
| AMBIGUOUS_SELECTION | 134 |
| OPTIONS_SUPERSEDED | 50 |
| CHOICE_UNRESOLVED | 2 |
| Chosen targeted actions | 191 |

| Chosen kind | Count |
|---|---:|
| PLAY_CARD | 357 |
| ATTACK | 92 |
| HERO_POWER | 75 |
| ACTIVATE_LOCATION | 32 |
| END_TURN | 180 |

Legal-action counts: min 1, max 49, mean 11.4701; 63 admitted decisions have only
END_TURN available. Unknown-card ratio is
26.4412% of 29,004 public card-ID field occurrences across state and legal
action descriptors. This occurrence-weighted measure counts repeated source
IDs in action variants; it is not a percentage of unique cards or skipped labels.
Unknown IDs remain visible semantic IDs and map to the existing shared UNK
embedding, retaining structured features.

The accepted 43-snapshot LIVE-0B regression recording was accessible. 41/43
trusted decisions received exact labels; 2 were skipped AMBIGUOUS_SELECTION.
All 41 admitted before-state hashes equal their recorded LIVE hashes.
Final source guards re-extracted all 21 admitted matches without changing any
saved row. Earlier diagnostic datasets/checkpoints were preserved and marked
invalidated; the loader refuses those datasets.

## Privacy and compatibility

Privacy audit: PASS. LIVE projection excludes opponent HAND/DECK/SETASIDE/
SECRET identities, own deck/secrets and raw names/accounts. Tests cover
OVERRIDE_HISTORY/SHOW/HIDE canaries, unexpected hidden fields, raw handles in
actions, localized display-name changes, and privacy-safe CLI summaries.
No private log or dataset/checkpoint is tracked. Provenance can locate a
selected card's public before/after events in the original local log for a
future evidence extractor; no mechanic inference or after-state feature is added.

The existing PolicyNetwork and encoding functions were simulator-independent:
GameState, StateEncoder, NumPy and PyTorch, without bridge calls. They now live
in `manamind.models.policy`; the old RosettaStone module re-exports its public
API. The architecture is preserved. Policy checkpoint action schema 4 appends
play_position; schema 3 migration preserves existing columns/embeddings and
zeros the new column. Value StateEncoder schema 16 and Value dataset schema
remain unchanged; ML-1A data/checkpoints require no re-import or migration.

The inherited scorer is intentionally coarse: it embeds the action-bearing
card, not every target identity, and does not consume every retained action
descriptor (e.g. card durability). Missing action-stat distinctions are also
limited by its inherited features. These are model capacity limitations for
ML-1C, not ambiguity in the admitted human-action labels.

The observation source inventory includes the extracted policy implementation.
Pinned regeneration updates only registry/report
`snapshot.execution_identity.observation_source_sha256`; card support
classifications, membership, rule semantics and admission counts are unchanged.

## Bounded supervised smoke

CPU, seed 1, one update, 8 real train decisions. Exact chosen-index cross entropy
over only the legal-action set completed backward, optimizer update, new ignored
checkpoint save, and exact weight reload. Checkpoint owns weights/config,
catalog, vocabulary, feature names, normalization and state/action schemas.
Overwrite is refused; the smoke allows at most 32 training decisions.

Whole-match split: train 17 (10 wins/7 losses), validation 2 (1/1), test 2 (1/1).
The test matches were not used in the update. Held-out metrics over 63 decisions:

| Metric | One-update plumbing result |
|---|---:|
| Train loss (8 decisions) | 1.396494 |
| Test cross entropy | 1.731347 |
| Top-1 | 0.206349 |
| Top-3 on menus >=3 (47 decisions) | 0.319149 |
| Mean reciprocal rank | 0.403154 |

These results prove consumption/backward/checkpoint plumbing only. They are
neither a policy baseline nor evidence of Hearthstone strength.

## Validation and remaining limits

Full pytest, including new action-label, existing LIVE, collector/importer and
ML/policy tests: **379 passed, 1 skipped** (19.51 s). Ruff over src/tests/scripts,
train_selfplay.py and evaluate_policy.py: PASS. Pinned generated-artifact check:
PASS, all 36 outputs reproduced with unique ownership. git diff --check: PASS.
Private datasets/checkpoints remain git-ignored. The optional local LIVE tail test
is skipped because MANAMIND_HEARTHSTONE_LOGS is not configured for the test run.
Real logs were validated separately, read-only, as reported above.

There is no implementation blocker to this bounded MAIN_ACTION dataset.
Coverage blockers are alternate/ambiguous option variants, unsupported choices,
superseded messages and excluded reset/reconnect/mode sections. This local
corpus has only 21 matches and no draws; its tiny held-out partitions cannot
establish general playing strength. The inherited policy feature limits above
must be considered when designing the first baseline.

Next task, **ML-1C — First Real Policy Baseline Training**: explicitly authorize
a bounded behavior-cloning baseline, freeze whole-match splits/seeds and outcome
balance, define checkpoint compatibility, train/evaluate cross entropy/top-1/
top-3/MRR on independent matches, and audit the inherited action/state feature
limitations. Add independent real matches before making general quality claims.

After that, **LIVE-0C — FIRST_LIVE_RECOMMENDATION**: explicitly authorize loading
the reviewed policy at READY SELF snapshots, score the complete sanitized legal
set, and map the selected semantic action back to a current live handle for a
read-only recommendation. Preserve trust, stale-options and visibility guards;
do not add gameplay automation, simulator search or fallback in that milestone
without a separate reviewed contract.

Verdict: `ML1B_REAL_POLICY_DATASET_READY`.
