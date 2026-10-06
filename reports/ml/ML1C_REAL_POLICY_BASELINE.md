# ML-1C — First real supervised PolicyNetwork baseline

Base: `33fc46d3dd6fd3d44f654ff1ee4da29df0211ce1` (fetched `origin/main`).
Branch: `work/ml1c-real-policy-baseline`; isolated worktree, no automatic merge.
Date: 2026-10-06. The policy learns a measurable held-out human-action signal;
this experiment does not assess Hearthstone playing strength.

## Data and frozen split

Used the non-invalidated local ML-1B `ml1b_admitted_846b6c5d` through current
`audit_dataset`/`load_examples`: 736 admitted SELF decisions, 21 completed
Ranked Standard matches, 922 observed decisions, 186 skipped, privacy PASS.
Aggregate facts match ML-1B; three older invalidated datasets were excluded.
No re-import or simulator examples were needed. The runner copies and audits
an unchanged private snapshot before fitting.

| Split | Whole matches | Decisions | Wins / losses |
|---|---:|---:|---:|
| Train | 17 | 591 | 10 / 7 |
| Validation | 2 | 85 | 1 / 1 |
| Test | 2 | 60 | 1 / 1 |

Seed-42 ML-1B outcome-stratified hash split, with the two previously published
seed-1 smoke-test matches forced into train. Any replacement uses a same-outcome
train match in seed-42 hash order, without considering performance. All match
and decision membership is frozen locally before training; no match crosses
splits. Input reordering changes neither membership nor optimization order.

- Dataset identity (canonical validated rows):
  `2b20c3b0fd48c34031dfbb8cf516cda9679ce53fee21843e0fc8613609f0b598`.
- Split identity:
  `4e96ec57ecdf26ac95d754c23b2ea88d354a27cb9f363ee91cecd8e44d85229b`.

Audit/hashing/outcome grouping establish membership. Test labels first contribute
to metrics after the validation-selected checkpoint is saved and reloaded.
One real configuration, one final test evaluation, no subsequent tuning. This
test set is now consumed; future model choices need a fresh independent holdout.

## Training and results

PolicyNetwork is unchanged: ordered SELF-hand and action-bearing card embeddings,
visible global/board-total features, current action descriptors, two 128-wide
Tanh layers, 124,577 parameters. Exact chosen_action_index cross entropy over
complete legal menus is the sole supervision. Outcome/provenance/handles/hidden
information never enter inputs; unknown IDs retain shared UNK behavior.

`configs/real_policy_ml1c.json`: CPU, one Torch thread, deterministic algorithms,
Python/NumPy/Torch seed 42, AdamW lr 0.001, weight decay 0.001, batch 32 equally
weighted decisions, gradient norm clip 1, maximum 60 epochs, patience 8,
validation CE improvement threshold 0.0001. This single moderate-rate schedule
allows learning while validation stopping, decay and clipping bound overfitting;
no self-play settings, architecture redesign or hyperparameter search.
Validation selected **epoch 6**; training stopped at **epoch 14**.
Runtime: Python 3.12.10, NumPy 2.5.3, Torch 2.14.0+cu130, CPU execution.
Reproducibility is scoped to this recorded runtime/CPU, not arbitrary hosts.

Uniform random assigns 1/N to every legal action. Its CE/top-k/MRR are analytic
expectations, not an arbitrary menu-order tie ranking. It establishes signal
above chance, not superiority to a strong game heuristic. Learned ranks use
stable descending logits.

| Split / scorer | CE ↓ | Top-1 | Top-3 | MRR |
|---|---:|---:|---:|---:|
| Train / learned | 1.178686 | 0.631134 | 0.767591 | 0.745578 |
| Train / uniform | 1.940877 | 0.245560 | 0.371810 | 0.424029 |
| Validation / learned | 1.882948 | 0.470588 | 0.575342 | 0.592275 |
| Validation / uniform | 2.415581 | 0.190385 | 0.233538 | 0.328721 |
| Test / learned | 1.789960 | 0.466667 | 0.571429 | 0.593777 |
| Test / uniform | 2.154141 | 0.163269 | 0.364080 | 0.351712 |

Top-3 uses menus >=3: train 469, validation 73, test 56 decisions. Other metrics
include all decisions. Excluding two singleton test menus, top-1 is 26/58 =
**44.83%**, versus **13.44%** uniform. Test match results are 19/41 and 9/19
correct, CE 1.804039 and 1.759579. Correlated decisions do not constitute 60
independent matches; two holdout matches cannot support a robust quality claim.

## Observable limitations

- **Overfitting:** train CE at epochs 1/6/14 is 1.759743/1.178686/0.549119;
  validation CE is 2.047363/1.882948/2.071979. The saved epoch-6 weights correctly
  retain the validation choice rather than the final training weights.
- **Data/class concentration:** 18 SELF Priest matches, 3 Warrior; train is
  14/3, all four held-out matches are Priest. No held-out Warrior or other SELF
  class evidence exists. Private full decks are not reconstructed; visible-hand
  overlap diagnostics do not establish archetypes. Limited breadth and observed
  overfitting are the clearest constraints; causal contributions cannot be ranked.
- **Targets/actions:** 20 of 32 test errors are PLAY_CARD (11/31 correct).
  Targeted decisions are 2/14 exact versus 26/46 without a target. Of those
  14 targeted rows, 6 choose the correct source/action root: four then miss the
  exact target/placement, eight choose a different root. Placement rows are
  7/14 exact, 9/14 correct roots. These overlapping subsets are not additive.
  Validation also struggles with targeted actions (2/22 exact).
- **Feature limits:** target identity is not embedded, board entities are
  aggregated, and some retained fields/missing-value distinctions are unused.
  Nevertheless all 736 chosen actions are distinct from other menu members in
  their encoded action row plus action-card index. Exact encoding collisions
  do not explain these errors. This experiment cannot separate insufficient
  data from feature limits or prove a target-embedding redesign would help.
- **Unknown cards:** public-ID occurrence ratio remains 26.44%. Test chosen
  non-END_TURN UNK actions are 4/8 correct versus 24/52 otherwise; UNK-in-hand
  rows are 19/39 versus 9/21 without UNK. Tiny confounded subsets do not show
  unknown identities dominating errors.
- **Labels:** exact ML-1B admission is preserved; no nearest-action relabeling,
  outcome substitution or legal-menu pruning. Human action optimality and the
  quality of importer-excluded decisions are not measured.

The current architecture is sufficient for an **experimental read-only LIVE-0C
integration** on current admitted action kinds. It is not proven to be a useful
or strong general adviser. Scores describe behavior selection, not calibrated
win probabilities; preserve the weak-baseline status in the recommendation UI.

## Checkpoint and reproduction

Ignored artifact in this worktree:
`data/processed_policy_ml1c/baseline_seed42_v1/policy.pt`; no default promotion.

| Identity | Value |
|---|---|
| File SHA-256 | `5a5e3435c0dcda5ce69bcd0a48dc8521fb3696e2a7794e268b894efbf7e3e95e` |
| Format | `manamind.real_policy_baseline/1` |
| Schemas | state 16; policy action 4; dataset 1; semantic descriptor 1 |
| Catalog SHA-256 | `3dfae0cb5fe312af22c2a16e01eba1286c073f89ea020808fbbf1778067870d9` |
| Vocabulary SHA-256 | `5d54256a24edce79df217ee13852eb6f0f4132213ad3abc09fd75c2fa36301a1` |

The checkpoint owns config/weights, exact catalog/vocabulary (1,185 identities
plus PAD/UNK), ordered feature names, normalization/schemas, selected epoch,
split membership/hashes, seed/config, data identity and source/runtime provenance.
`load_policy_checkpoint` loads weights-only, checks compatibility, hashes,
catalog/vocabulary mapping and disjoint splits, and strictly loads finite weights
with matching shapes. Smoke/Value/legacy formats and migrations are rejected.
It reconstructs the saved encoder without external catalog changes. Weight and
validation-logit round trips are exact; unknown IDs map to UNK.

Reproduce from the frozen private snapshot into a **new ignored path**:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
E:/ManaMind/.venv/Scripts/python.exe scripts/train_real_policy.py `
  data/processed_policy_ml1c/baseline_seed42_v1/dataset `
  --config configs/real_policy_ml1c.json `
  --output data/processed_policy_ml1c/reproduction_seed42_new
```

Existing outputs are refused. Local frozen_experiment.json, dataset, audit,
history.json, metrics.json, diagnostics.json and policy.pt remain ignored;
this tracked report contains aggregates and cryptographic identities only.

## Validation and exact next task

Relevant policy/data/training tests: **54 passed**. Full pytest: **400 passed,
1 skipped**. Ruff, generator identity guard, typed-failure source inventory,
36 pinned outputs/ownership and git diff --check: PASS. Independent new tests
cover analytic metrics, frozen membership, repeated fixture-run weight equality,
test scoring only after checkpoint selection, UNK preservation, overwrite refusal,
invalidated data and incompatible/tampered checkpoints. Fixtures verify plumbing;
all quality numbers above use admitted real examples. No native build is needed.

**LIVE-0C — FIRST_LIVE_RECOMMENDATION:** load this explicit checkpoint through
the strict loader; use identical encoders at trusted READY SELF MAIN_ACTION
snapshots, score the complete sanitized menu, and display experimental top-1/
top-3 recommendations. Map semantics to current handles for description only.
Preserve snapshot identity, settled-task-list, stale-options, SELF, privacy and
unsupported-choice guards; reject incompatible schemas/incomplete menus. Validate
offline on recorded LIVE decisions: checkpoint/logit parity, UNK, target/placement
descriptions and recommendation invalidation when options change. Then perform
an explicitly authorized read-only live smoke. No clicks, online learning,
simulation, search, MCTS or Q fallback. New independent varied matches are required
before further model selection or broader recommendation-quality claims.

Verdict: `ML1C_REAL_POLICY_BASELINE_WEAK_BUT_VALID`.
