# Real policy representations

Both versions score the complete admitted legal menu with behavior-cloning
logits. The target is chosen_action_index; logits are neither action values nor
win probabilities. No simulation, search or online learning is involved.

## V1 and V2

PolicyNetwork, its feature order and default ML-1C config remain compatible with
`manamind.real_policy_baseline/1`. No weights are migrated. V2 has explicit
representation version 2 and file format `manamind.real_policy/2`. Real dataset
and semantic descriptor schemas remain 1; StateEncoder remains 16; the legacy
policy action schema constant remains 4.

V2 consumes global v1 features plus public player-class categories, and variable-
length entity tokens for heroes' public stats, ordered SELF hand, both public
boards, weapons, hero powers and visible active effects already in GameState.
Minions and Locations share actual board positions. Empty optional zones produce
no tokens; no entity is truncated.

Tokens combine shared card embeddings with existing EntityEncoder numeric,
presence, category, mechanic, state-flag and hand-semantic columns. Base metadata
and observed instance values remain separate. Role/side indicators and public
hero armor/status masks supplement these columns. Unknown IDs keep index 1 and
visible structured features. Index 0 is PAD/absent action identity.

Actions retain v1 columns and add current durability, presence masks, source/
target kinds and identity embeddings. Exact links gather source, target and
insertion neighbors. Hand indices are zero-based; board/insertion positions are
one-based. Links are local token indices, never Power.log handles. Raw public
identity and kind must match before vocabulary lookup: two unknown IDs cannot
validate an incorrect binding. Signed attack/health differences have presence
masks; these are numeric relationships, not simulated outcomes. END_TURN has no
source, target, neighbors or card identity.

One shared entity projection produces tokens. An action query uses descriptors,
source and target; attention selects visible context separately for each candidate.
A small scorer combines global/attended context, the query, source/target
interaction and insertion neighbors. Action reordering only reorders outputs.

The encoder rejects opponent-known-card identities, secret identities and pending
choices under the existing real-policy boundary. It receives only state/actions,
never outcomes, provenance, match/decision IDs or future events. Hero identity is
used only where a reviewed descriptor provides it. Missing history/effect text is
not invented. Inconsistent bindings reject a decision rather than prune its menu.

## Experimental v3 network (ML-POLICY-V3-1)

`PolicyNetworkV3` (`manamind.real_policy/3`, `src/manamind/models/policy_v3.py`) consumes **exactly the v2 input
tensors** (`encode_policy_v2`, input representation 2, same ordered state/entity/action columns and vocabulary), so
a v2/v3 comparison changes only the network. Dispatch: `representation_of(PolicyNetworkV3) == 3`,
`encode_policy_inputs(..., representation=3)` calls the v2 encoder. Additions over v2: one self-attention block over
the global state token plus all visible entity tokens (tokens are read in the context of the board), and one
permutation-equivariant block across the candidates of one menu (a score may depend on the actions actually
available). `model_config` owns `heads`, `entity_layers`, `menu_layers`; a v2 loader rejects the v3 schema and vice
versa; there is no migration. The Vue overlay still requires representation 2 and refuses v3 checkpoints; the
v3 checkpoint is an experiment artifact and is not wired into LIVE. See `reports/ml_policy_v3_1/README.md`.

## Checkpoint and experiment

The strict loader dispatches by format and checks ordered global/entity/action
names, roles/links, representation/source schemas, normalization, model dimensions/
dropout, catalog/vocabulary mapping, split/data/config identities and finite strict
weight shapes. Incompatibility fails closed. The saved encoder is reconstructed;
Value, smoke and self-play formats remain separate.

V2 training requires an explicit frozen v1 reference. Before fitting, data,
catalog and complete ML-1C frozen split/decision membership must match. Validation
alone selects the epoch; checkpoint save/reload precedes test scoring. Comparison
uses frozen v1 weights. This consumed test is a regression comparison set, not a
new untouched holdout; do not tune on it.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python scripts/train_real_policy.py <frozen-admitted-dataset> `
  --config configs/real_policy_ml2a.json `
  --baseline-checkpoint <accepted-ML1C-policy.pt> `
  --output data/processed_policy_ml2a/<new-run>
```

Private snapshots and checkpoints remain ignored. Existing outputs are refused.
See [the ML-2A report](../reports/ml/ML2A_POLICY_V2.md).

## Experimental LIVE selection

Training and LIVE share encode_policy_inputs. Existing callers of `PolicyRecommender` that omit a
digest retain the reviewed ML-1C fallback. The Windows LIVE-MVP-1 command explicitly selects the
frozen Policy v2 path and its independently recorded digest. There is no automatic promotion or
model reload:

```powershell
python scripts/replay_live_recommendations.py <private-recording> `
  --checkpoint <v2-policy.pt> --checkpoint-sha256 <verified-digest>
python scripts/run_manamind.py --checkpoint <v2-policy.pt> `
  --checkpoint-sha256 <verified-digest>
```

The digest pins identity, not quality. READY/SELF/mode/settlement/current snapshot,
complete menu, catalog and staleness gates stay identical for both architectures.
Collector/LIVE-0D are not redesigned. Raw slice.log retains its private, ignored
replay contract and must never be shared unsanitized.
