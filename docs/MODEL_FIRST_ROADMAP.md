# Model-first roadmap

This is the single source of current development priorities. Other documents (including ManaEngine documents, `docs/history/` and dated `reports/`) do not define next steps. Time estimates below are experiment guides, not promises of quality; a stage ends when its criterion is met or when the evidence says the idea does not work.

## Strategy

A local neural Policy ranks the legal actions of a player-visible position. It learns from real logs, controlled synthetic tactical cases and, later, observed action outcomes. The main use case is 1–2 of the user's decks in current Standard against varied opponents.

```text
Hearthstone / Power.log → player-visible GameState → card metadata + features (+ future text embeddings)
→ legal action representation → local Policy → action ranking → evaluation / live recommendations
```

Real logs feed training and evaluation datasets. Synthetic tactical cases feed controlled training and evaluation. Observed action outcomes are a future auxiliary signal. ManaEngine is an optional, frozen tactical verifier; full Standard simulator coverage is not required for any stage.

## Principles for every stage

- **Hypothesis and baseline first.** Write down what is expected to improve, over what baseline, and what result would refute it.
- **Short training.** Smallest model/data/epochs that can answer the question. A larger run needs a prior positive small result and the user's explicit go-ahead.
- **Honest comparison.** Identical data, identical match-level splits (`game_id`), fixed seeds, several seeds when differences are small.
- **Separate metrics.** Game quality, imitation accuracy and technical correctness are reported separately and never summed into one claim.
- **Held-out real control data** stays untouched by training and tuning.
- **No silent scope growth.** Do not start the next stage, self-play, mass card implementation, simulator expansion or a new architecture without an explicit task. A negative result is a valid result.
- **Contracts stay intact:** player-visible information only, no invented values for unknown data, explicit schemas, checkpoint compatibility, preserved historical artifacts.

## Stages

| # | Stage | Status |
|---|---|---|
| 1 | Evaluation Baseline (MODEL-FIRST-1) | Complete and accepted |
| 2 | Synthetic training on tactical decisions (MODEL-FIRST-2, 2B, 2C) | Complete; ambiguous results, shortcut learning and regressions found |
| 3A | Card representation and text safety pilots | Complete; INCONCLUSIVE |
| 3 | Compare ID / Structural / Text / Hybrid Policy | Planned; Text/Hybrid Policy not trained |
| 4 | Predicting observable consequences | PLANNED (experimental) |
| 5 | Independent check of practical quality | PLANNED |
| 6 | Live Shadow Mode | PLANNED |
| 7 | Long-term development if results are positive | PLANNED |

### 1. Evaluation Baseline

- **Goal:** a fixed, honest yardstick for Policy decisions before any new idea is tried.
- **Outcome:** reproducible evaluation runner and report for existing Policy v1/v2 and simple baselines (random legal, heuristic), with separate imitation, tactical and technical metrics.
- **Gate to next stage:** the baseline reproduces on a clean checkout and its numbers are accepted in review.
- **Data limits:** real logs are few matches; confidence intervals must be reported; no leakage between positions of one match.

### 2. Synthetic training on tactical decisions (MODEL-FIRST-2)

**Status (MODEL-FIRST-2 / 2B / 2C): complete.** The controlled results are ambiguous. The shortcut challenge exposed positional shortcuts, and the robustness follow-up found regressions. These synthetic results do not establish practical playing strength. The original reports preserve the stage-specific measurements and limitations.

- **Goal:** test whether the Policy can learn controlled tactical skills (lethal, trading, card-vs-mana choice, using hero power) from generated cases.
- **Outcome:** per-skill accuracy of the trained model versus the original Policy **and** versus a heuristic baseline, on held-out synthetic scenario families that did not take part in training.
- **Stage-2 success criterion (intermediate):** a measurable improvement over the original Policy on new, unseen synthetic families, with the comparison against the heuristic reported. This is controlled-skill evidence only and is **not** proof of playing strength.
- **Does not block the next step:** real independent validation is not required to close stage 2 or to start the next limited ML experiment (stage 3). Its absence only means no claim about real game quality is made.
- **Required before live acceptance (stage 5/6, not here):** confirmation on independent real data is mandatory before a model is accepted for live use. A synthetic-only gain never qualifies a model for live.
- **Data limits:** generators encode only rules written by hand and reviewed; cases must expose player-visible information only; held-out families must be defined before training. The frozen MODEL-FIRST-1 control scenarios and all of their families/templates are excluded from training and validation.

### 3. ID / Structural / Text / Hybrid Policy comparison

**MODEL-FIRST-3A status: complete, INCONCLUSIVE. CARD-TEXT-AUDIT-1 and MODEL-FIRST-3A-TEXT-SAFETY are complete.** The text adapter and overlap audit are experimental safeguards; no Text or Hybrid Policy has been trained, and no gameplay benefit from text has been established.

The next priority is a new independent corpus of real observations. Do not start a Text/Hybrid comparison until that corpus and its match-level evaluation split are available and reviewed.

- **Goal:** find out which card representation generalizes to unseen cards: identity embedding, structural features, card-text embedding, or a combination.
- **Outcome:** one table on identical data and splits, including a split with cards unseen in training.
- **Gate:** a representation wins on unseen-card positions without losing on seen ones; otherwise keep the current one.
- **Data limits:** text embeddings are not implemented today; adding them is a measured experiment, not an assumption.

### 4. Predicting observable consequences

- **Goal:** test whether auxiliary prediction of observed action results (board, health, hand changes visible in logs) improves the Policy.
- **Outcome:** ablation with and without the auxiliary head under the same budget.
- **Gate:** measurable Policy gain on the stage-1 metrics. No hidden information as a target.
- **Data limits:** only consequences visible in Power.log; no simulator-generated labels unless a separate task authorizes ManaEngine verification.

### 5. Independent check of practical quality

- **Goal:** confirm the gain on situations that no earlier stage used for training or tuning.
- **Outcome:** report on a fresh set of real matches or expert-reviewed positions from the user's decks.
- **Gate:** the gain holds on independent real data; this is the confirmation of real game quality and is required for live acceptance. Otherwise return to stage 2–4 with a new hypothesis.

### 6. Live Shadow Mode

- **Goal:** run the useful model next to a real game, read-only, and compare its ranking with what the player did.
- **Outcome:** recorded shadow rankings and agreement statistics; no actions are performed on the player's behalf.
- **Gate:** stable, privacy-preserving operation over a series of games.
- **Limits:** live trust gate and hidden-information boundary from [LIVE_BRIDGE.md](LIVE_BRIDGE.md) stay in force.

### 7. Long-term development

Only if stages 1–6 show positive results: wider decks, better opponent modeling, any search layer (which needs a reviewed information-set design), and optional ManaEngine verification for narrow tactical checks.

## Prohibited expansion

No stage authorizes by itself: self-play, mass card implementation, extending ManaEngine, reintroducing RosettaStone, new training on historical queues, or live action automation. Each needs a separate user task.
