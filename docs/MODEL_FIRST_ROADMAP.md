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
| 3 | Compare ID / Structural / Text / Hybrid Policy | ML-PILOT-1 complete, INCONCLUSIVE on development test; independent check pending |
| 4 | Predicting observable consequences | PLANNED (experimental) |
| 5 | Independent check of practical quality | PLANNED |
| 6 | Live Shadow Mode | MVP implemented; technically PLAYTEST VERIFIED; Policy v2 quality not validated |
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

**MODEL-FIRST-3A status: complete, INCONCLUSIVE. CARD-TEXT-AUDIT-1 and MODEL-FIRST-3A-TEXT-SAFETY are complete. ML-PILOT-1 is complete, INCONCLUSIVE.** A limited Hybrid Policy was trained on real data under the explicit ML-PILOT-1 task. It did not establish a reliable imitation gain or gameplay benefit from text; the experimental checkpoint remains separate from LIVE. See [the pilot report](../reports/ml_pilot_1/README.md).

The LIVE-MVP has been checked in real Ranked Standard games and is **PLAYTEST VERIFIED** for technical operation. Policy v2 remains a frozen baseline; its recommendation quality is not validated. The immediate priority is independent real-game verification and evaluation of recommendation quality. The 16 matches in ML-PILOT-1 are a development test already examined in DATA-CHECKPOINT-1; they cannot serve as an independent control for another model cycle. Do not begin another ML version until an independent evaluation set and match-level split are prepared and reviewed.

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

**LIVE-MVP-1:** the Windows always-on-top Tkinter panel uses the unified LIVE runner, pinned Policy
v2 checkpoint, existing collector and trust/invalidation gates. It remains read-only. Real Ranked
Standard playtests confirmed that recommendations appear during the player's turn and refresh after
actions; its technical operation is **PLAYTEST VERIFIED**. Policy v2 recommendation quality is not
validated and must be evaluated separately.

- **Goal:** run the useful model next to a real game, read-only, and compare its ranking with what the player did.
- **Outcome:** recorded shadow rankings and agreement statistics; no actions are performed on the player's behalf.
- **Gate:** stable, privacy-preserving operation over a series of games.
- **Limits:** live trust gate and hidden-information boundary from [LIVE_BRIDGE.md](LIVE_BRIDGE.md) stay in force.

### 7. Long-term development

Only if stages 1–6 show positive results: wider decks, better opponent modeling, any search layer (which needs a reviewed information-set design), and optional ManaEngine verification for narrow tactical checks.

## Prohibited expansion

No stage authorizes by itself: self-play, mass card implementation, extending ManaEngine, reintroducing RosettaStone, new training on historical queues, or live action automation. Each needs a separate user task.
