# ManaMind

ManaMind is a research project for a Hearthstone assistant. Its first milestone is a small value network that estimates the chance that a chosen player wins from a visible game position.

## Clone the repository

Clone with submodules so the pinned RosettaStone source is present:

```powershell
git clone --recurse-submodules https://github.com/MaksimOrekhov/manamind.git
```

ManaMind pins RosettaStone at upstream revision `e10749b5f0c08d3a6135bce317cb11d1738846ad` and keeps local engine changes as a patch. Apply it once after cloning:

```powershell
git -C .\vendor\RosettaStone apply .\..\..\integrations\rosettastone\patches\rosettastone-mana-mind.patch
```

The ManaMind Python package and its tests do not require building RosettaStone. Simulator builds additionally require the C++ dependencies documented in [the integration guide](docs/ROSETTASTONE_INTEGRATION.md).

## Current foundation

The initial domain types live in `src/manamind/domain`. `GameState` describes the position from the player's point of view (`self` and `opponent`). It stores the player's hand and only explicitly known opponent cards; it has no field for hidden opponent hand contents or deck order. `BoardEntity` keeps current stats separate from the card's catalog features.

The current foundation includes the game-state schema, local card catalog, fixed-width state encoder, PyTorch value network, synthetic data generator, grouped train/validation/test splits, training loop, versioned checkpoints, and inference CLI. Synthetic training only verifies that the pipeline works; it does not produce a Hearthstone-playing model.

## Card catalog and state encoding

`CardCatalog.from_json(...)` reads a HearthstoneJSON-style list. `CardVocabulary` assigns deterministic indices and reserves separate padding and unknown-card tokens. Missing catalog properties are filled from the visible card record when available.

`StateEncoder` returns an `EncodedGameState`: one fixed-width global feature vector, SELF/OPPONENT class indices, and separate variable-length encoded zones for hand, boards, known opponent cards, weapons, and hero powers. Numeric values use signed `log1p` scaling (clipped at 10,000); presence masks distinguish missing card stats from an actual zero. Board order and current entity stats are retained.

Run the sample encoder from WebStorm or the project terminal:

```powershell
python .\encode_example.py
```

The sample uses a tiny included catalog. For real card metadata, pass your local `cards.json` path to `CardCatalog.from_json`.

## Value Network

`ValueNetwork` shares one card/entity encoder across zones, pools each variable-length zone with masked mean and max pooling, combines those vectors with global game features, and returns a logit. `predict_win_probabilities` applies sigmoid and handles one or many states. The runnable `model_example.py` demonstrates the forward path on the configured GPU when available. Its output is random until the model is trained.

## Synthetic training run

The synthetic generator makes simple positions from random health, mana, hands, and boards. It assigns a win/loss by sampling from a small hand-written formula based on the visible advantage. This is only a way to check that the training pipeline learns a signal; it is not a Hearthstone rules engine and the resulting model is not suitable for recommending moves.

Generate saved JSON Lines splits:

```powershell
python .\generate_synthetic.py --samples 2048
```

Generate the splits, train the model, report held-out test metrics, and run one example prediction:

```powershell
python .\train_value.py --samples 2048 --epochs 20
```

The script writes `data/processed/train.jsonl`, `validation.jsonl`, and `test.jsonl`. It saves the best validation checkpoint to `checkpoints/value_v1_s4.pt`. To make a quick demonstration run, lower the sample count and epoch count, for example `python .\train_value.py --samples 256 --epochs 3 --batch-size 32`.

After training, load that checkpoint for a separate prediction:

```powershell
python .\predict_state.py .\data\samples\example_state.json
```

The checkpoint stores its vocabulary, card catalog snapshot, encoder schema, feature names, and normalization settings. Predictions use the catalog snapshot that trained the model, so inference remains repeatable. Optionally pass `--cards .\path\to\cards.json` to add metadata for additional IDs. Unknown IDs are reported.

The current encoder schema is v6. It includes separate minion and Location zones, Location durability/cooldown state, ordered hand positions, hero-power readiness, and separate current cost/attack/health/durability for hand and weapon instances. Older value checkpoints are rejected because their feature meanings predate these changes. Save training output to a new checkpoint filename instead of overwriting historical checkpoints.

## First self-play policy

`train_selfplay.py` is a separate experimental action policy. At each RosettaStone decision, it scores only the currently legal actions using the player-visible global state, visible board summaries, ordered embeddings of the viewed player's own hand, card identity, hand position, and semantic action features. It samples one legal action, plays both seats with the same policy, then performs a REINFORCE update from the terminal win/loss result. The Value Network checkpoint is separate and is not used by this first policy.

The bundled `data/samples/rosettastone_test_decks.json` contains simple legal decks built from cards currently registered in the simulator. Use these only for pipeline smoke runs; they are not competitive Standard lists.

The audited Mother Drake Warlock list is available in `data/samples/mother_drake_warlock_selfplay.json`. Its card scenarios, the Bat Mask + Deios + Annihilation combo, and the full-board Location legality check pass. The first 48-game mirror pilot used seed `20260927` and six policy updates. The final checkpoint is `checkpoints/policy_mother_drake_pilot_20260927.pt`; cycle 1 is preserved as `checkpoints/policy_mother_drake_cycle1_20260927.pt`.

On five held-out seeds, the final policy beat the fixed heuristic in 18 of 20 matches (baseline control: 6–4). In a direct comparison on another five seeds, cycle 6 beat cycle 1 in 20 of 20 matches, with each checkpoint playing both seats and both deck orders. Reports are in `reports/policy_mother_drake_vs_baseline_after48games_20260928.json` and `reports/policy_mother_drake_cycle6_vs_cycle1_20260928.json`. These results show improvement inside this exact simulation setup; they do not establish Hearthstone strength. The heuristic opponent is weak, the sample remains small, and the ban list and full Standard card pool are not audited.

Run a small self-play training session from the project root:

```powershell
.\.venv\Scripts\python.exe .\train_selfplay.py --games-per-cycle 8 --cycles 5
```

This uses the sample decks in `data/samples/rosettastone_test_decks.json`, the pinned RosettaStone card pool, and writes `checkpoints/policy_selfplay_v1.pt`. Training refuses to replace an existing checkpoint; add `--resume` to continue it. Use `--decks`, `--checkpoint`, `--seed`, `--games-per-cycle`, and `--cycles` to change the run.

This is a learning-mechanics prototype, not a strong Hearthstone player. The simulator now supports the selected Mother Drake list, but the current ban list and full Standard card pool are not audited. The policy gets terminal rewards, so learning can be noisy; compare versions over held-out matches and stronger opponents before making strength claims.

The broader September 2026 deck pool is catalogued in `data/samples/standard_meta_deck_pool_20260928.json`. It has five real lists across Warlock, Warrior, Druid, and Priest. `scripts/audit_standard_meta_coverage.py` writes a per-card and per-mechanic matrix. Including existing Warlock support, 64 of 74 unique cards are registered or need no text rules; 10 still need support. Fyrakk the Blazing (`FIR_959`) now grants Fire spell immunity and casts random Fire spells at enemy targets up to 15 total mana, covered by focused C++ scenarios. Only the two Warlock lists pass the full card-rules gate. Warptooth (`JAIL_421`) tracks distinct friendly characters damaged during the current turn and summons itself from hand or deck after the fourth; a focused scenario covers both zones and duplicate damage. The current rules group registers and scenario-checks Spiderling's turn-only hero Attack aura, Carrier Whelp's random low-cost Dragon generation, Prescient Slitherdrake's three-mana discount while another Dragon is held, Spider Rider's draw after a hero attack, Kindred discounts for playing a Dragon minion or Holy spell on the previous turn, Undeath Sentence replaying a friendly minion's Deathrattle from the graveyard, and Naralex reducing the first Dragon's cost each turn. Cannonmaster generating a Cannoneer with a random end-of-turn shot, Hook n' Heave discovering a Pirate and summoning two Cannoneers, Chainbreaker Hogger duplicating Legendary cards at game start, Ysera increasing both players' max Mana, Brood Keeper equipping Nightmare Slicer when a Dragon is held, and Holy Embrace healing its hero and generating targeted Dark Embrace; and Waveshaping choosing a card from the deck. Mother Duck summons three 1/1 Rush Ducklings, and Twilight Influence exposes and executes both Choose One branches, as does Secret Ingredient with its hero Attack or random-card options. Ritual of Life discovers only 3-cost minions and summons the choice as a 2/3 copy. Torch deals 8 damage to a damaged minion and returns to hand when it overkills; the focused scenario checks the copy-to-hand behavior. Acceleration Aura grants temporary Mana at the start of the next three turns; its scenario also checks the updated expiration order for temporary Mana. Felwood Treant tracks 4 Mana spent while held, and Merithra tracks 25 before reducing generated Dragons to 1; these totals include card, Hero Power, and Tradeable payments. Staff of Trickery discovers a Druid card after a hero attack and discounts the choice by attack value captured before exhaustion. Amirdrassil summons a 1-cost minion, grants Armor, draws, and refreshes progressively more Mana on each use. Infest the Scullery counts successful hero attacks across the match and summons two random minions whose Cost is 3 plus that count; its scenario checks the two-attack, 5-Cost result. The bridge exposes card race in self-hand observations. The bridge reports derived hero Attack so aura changes are visible to the policy. Generic `ChoiceAction::HAND` Discover candidates are exposed as `CHOOSE_CARD`; special choice windows still need per-type support. Random and Discover pools can also offer cards outside these five lists, and the coverage matrix does not certify those generated cards. Do not train on the full pool until Warrior, Druid, and Priest coverage is implemented and their matches complete. The self-play trainer accepts a deck-pool config and cycles through every distinct deck pairing; the evaluator runs each pairing separately with both seats and both deck orders. Run one pooled training and final evaluation after all lists pass coverage.

Evaluate a saved policy on seeds separate from training. The evaluator plays the policy greedily from both seats against the same fixed baseline and also runs baseline-vs-baseline control games to expose seat/deck bias:

```powershell
.\.venv\Scripts\python.exe .\evaluate_policy.py --checkpoint .\checkpoints\policy_selfplay_v1.pt --pairs 10 --seed 10001 --report .\reports\policy_eval.json
```

`--pairs 10` runs 40 policy-vs-opponent matches (both model seats and both deck orders for each seed) plus 20 baseline-control matches. The report includes outcomes by seat and deck order, a Wilson interval over decisive matches, and the exact seeds/results. A small or easy opponent sample is only a smoke evaluation; repeat with more seeds and stronger fixed opponents before judging improvement.

To compare two policy checkpoints directly, pass `--opponent-checkpoint`:

```powershell
.\.venv\Scripts\python.exe .\evaluate_policy.py --checkpoint .\checkpoints\policy_selfplay_v1.pt --opponent-checkpoint .\checkpoints\older_policy.pt --pairs 20 --seed 20001
```

To train from already saved JSONL splits, each record must have `schema_version`, `game_id`, `sample_id`, `state`, and `target`. Splits are grouped by `game_id` to keep every position from a match together:

```powershell
python .\train_value.py --dataset-dir .\data\processed --cards .\data\cards.json --epochs 20
```

Each `GameState` requires `turn_number`, `active_player` (`SELF` or `OPPONENT`), and both player observations. Player observations require `hero_health`. Draw targets may be 0.5: they affect loss and calibration metrics, while accuracy and ROC AUC use decisive wins and losses only.

Run the current automated checks with:

```powershell
python -m pytest -q
```

## Environment

The project targets Python 3.12. On Windows, create and activate the virtual environment from the project directory:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

For an NVIDIA GPU, install the CUDA 13.0 PyTorch build, then install the project and development tools:

```powershell
python -m pip install "torch==2.14.0+cu130" numpy pytest ruff --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple
python -m pip install -e .
```

The CUDA-enabled PyTorch package includes the CUDA runtime it needs; a separate CUDA Toolkit installation is not required for normal training and inference. Verify GPU access with:

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

CPU-only machines can install the standard PyTorch wheel instead. Keep CPU inference available in code even when training on CUDA.

## Project map

- `src/manamind/domain` — simulator-independent game and card types
- `src/manamind/cards` — local card catalog and unknown-card vocabulary
- `src/manamind/encoding` — conversion of game states into padded tensors
- `src/manamind/models` — PyTorch value network with pooled card zones
- `src/manamind/integrations/rosettastone/policy.py` — legal-action policy and semantic state/action features
- `train_selfplay.py` — terminal-outcome self-play training loop
- `src/manamind/training` — synthetic data, grouped splitting, metrics, checkpoints, and training
- `src/manamind/inference` — batch prediction and unknown-card reporting
- `configs` — model and training defaults
- `data/samples` — small example inputs

The target is the win probability of the perspective player: 1 for a win, 0 for a loss, and 0.5 for a draw.

Shaladrassil (`EDR_846`) generates the five classic Dream cards, or the five Corrupted versions if a higher-cost card was played while it was held. Focused C++ scenarios verify both branches and all five generated-card effects.

### Pinned Standard profile and source checks

`configs/standard_profile.json` selects the dated metadata archive, scope, bans, roots, generator catalog, engine overlay and evidence inputs. Rebuild shared snapshots with `python scripts/build_standard_profile.py`, then run the generators and `python scripts/build_standard_registry.py`. Each tool accepts `--profile PATH`; generators also accept `MANAMIND_STANDARD_PROFILE`. Updating a patch requires a new reviewed profile/scope/archive, not editing Python dates.

Run `python scripts/check_generated_artifacts.py` to rebuild all pinned outputs and reject drift or duplicate generated ownership. GitHub Actions runs this check, Ruff correctness diagnostics and Python tests on Linux and Windows with recursive submodule checkout. Native checks are separate; no model training runs in CI.

Scoped verification files use schema v2 with explicit source/profile identities, binary checksums and successful native/bridge results. Canonical registry generation does not inspect ignored build products. Old schema-v1 evidence remains historical and stale until its scenarios are rerun. Native/bridge producers check the intended local binaries; a registry evidence record alone does not inspect the process currently running.

On the configured Windows native workspace, run `python scripts/build_native_identity.py` before the focused `verify_*.py` producers. Rebuild this identity after source/profile changes. `python scripts/verify_instance_observations.py` compares actual native hand/weapon instance observations with the Power.log import path.

Card metadata (`cost`, `attack`, `health`, `durability`) is distinct from optional `current_cost`, `current_attack`, `current_health`, `current_durability`. Gameplay decisions use effective instance values. Encoder schema v6 adds current cost/durability channels and preserves modified hand attack/health. Older checkpoints are rejected; existing checkpoints and datasets are preserved.
