# RosettaStone integration status

## Current checkpoint

RosettaStone is checked out at `vendor/RosettaStone`, revision `e10749b`. Its upstream `pyRosetta` module builds and imports in ManaMind's Python 3.12.10 virtual environment. Upstream exposes card and deck utilities, but does not expose gameplay objects. ManaMind therefore has a separate pybind11 module at `integrations/rosettastone/` linked to the upstream C++ `RosettaStone.lib`.

The bridge currently runs a deterministic sample match (Warlock vs. Paladin) and exports a player-visible snapshot. `src/manamind/integrations/rosettastone/rosettastone.py` loads that native module and converts the snapshot through the existing `game_state_from_dict` adapter into ManaMind's `GameState`.

## What was verified

- Upstream RosettaStone built its Python module for CPython 3.12 on Windows.
- The separate ManaMind C++ bridge compiled and linked against the engine.
- A sample game reaches `MAIN_ACTION`, then the bridge plays a known 1-mana fixture minion through RosettaStone `PlayCardTask`; the resulting state parses as `GameState`.
- Snapshot includes our hand identities, minions with current stats/status, both heroes/resources, and opponent hand size. It leaves `opponent_known_cards` empty and does not include opponent hand or deck identities.
- The emitted GameState also ran through the current checkpoint and inference path on CUDA (P(SELF wins)=0.489). The four fixture card IDs were unknown to that synthetic checkpoint vocabulary, so this is only an integration smoke check, not a meaningful estimate of game strength.
- Smoke result for the current fixture: turn 1, SELF active, one 2/1 Murloc Raider on our board, 3 cards left in our hand, 5 in the opponent hand, 5 in each deck, and 0 available mana after the play.

This is a wiring milestone, not proof that all game rules, cards, or live observations are supported. The pinned RosettaStone revision's `STANDARD_CARD_SETS` list stops at Return of the Lich King (2022); its Standard validator reflects that old engine snapshot, not the current Hearthstone Standard rotation. The sample decks are for exercising this engine and are not current-format recommendations. The sample-match helper still executes one hard-coded fixture play. The `inspect_decks` API accepts 30-card ID lists and enumerates a limited set of legal actions. `SimulatorSession` keeps a match alive, applies supported actions, advances the engine, exports the next observation, and reports the final result. A simple seeded baseline can now play complete matches and save player-visible positions with terminal win/loss/draw labels in the existing JSONL schema. Deck validation now checks size, unknown/non-collectible cards, class restrictions, pinned card-set membership, and copy limits. The upstream card pool lacks a current ban list and has an outdated Standard set list; most card-choice/Discover windows still stop a rollout, while M.O.T.H.E.R.'s hand-card choice is supported. Treat these files as baseline-simulator data, not as demonstrated model strength.

## Current Standard pool migration

The Python card catalog is current, and RosettaStone now has a separate metadata overlay for that catalog. The Standard manifest supports exact card-ID exceptions for early-access cards: `BE_036` is temporarily Standard-legal before its full set releases. Do not put the unreleased `BE` set in `standard_sets` just to include this one card. Generate or refresh the data and overlay with:

```powershell
.\.venv\Scripts\python.exe .\scripts\sync_rosettastone_standard_metadata.py
.\.venv\Scripts\python.exe .\scripts\audit_rosettastone_card_pool.py
```

Upcoming-set metadata is kept in a separate preview file and never enters the Standard overlay or training data automatically. Refresh the currently published/revealed cards from set `BE` with:

```powershell
.\.venv\Scripts\python.exe .\scripts\update_card_preview_catalog.py --set BE
```

The preview catalog is metadata only. It can help audit upcoming card text, but the cards still need simulator rules and scenario checks before use in games or training.

At the 2026-09-27 catalog snapshot, the catalog has 1,188 collectible Standard cards, including the single `BE_036` early-access exception. Before the overlay, only 114 IDs were present in the pinned RosettaStone `Resources/cards.json`; none of the six non-Core sets in the current manifest were present there. The audit finds 105 current IDs registered with `cards.emplace(...)` in old CardSets sources, all from Core. This source scan is a heuristic and does not establish that effects are correct or complete.

The native loader merges `Resources/cards.standard_current.json` into the old resource at startup; the historical resource and its non-collectible entries remain intact. RosettaStone's `CardSet` enum and `STANDARD_CARD_SETS` were updated to recognize the current manifest. Metadata availability still does not implement printed effects or add new non-collectible tokens. `validate_deck` and the simple-deck candidate list now reject text-bearing cards unless RosettaStone has an explicit `CardDef`; textless cards can pass because their behavior is represented by base metadata. This is a conservative gate, not proof of correctness: each `CardDef` still needs a focused scenario check. A user-authorized pilot is now restricted to the audited Mother Drake deck; do not generalize its labels to the full Standard pool or Value Network training while the ban list and broader effects remain unaudited.

### First current-card rule scenario

The first focused archetype is the September 2026 Standard **Mother Drake Warlock** list. Its published list includes Earthen Drake, Chrono-Lord Deios, Bat Mask, and M.O.T.H.E.R. ([Vicious Syndicate list, published September 23, 2026](https://www.vicioussyndicate.com/decks/mother-drake-warlock/)). **CATA_999 Earthen Drake** deals 4 damage to the enemy hero at the end of its controller's turn. **BE_036 M.O.T.H.E.R.** lets the player choose a card in hand, reducing that card's cost by 5 and neighboring cards by 4, 3, 2, and 1 as the reductions move outward. Its hand-choice path is registered in `CoreCardsGen.cpp`, handled by `Actions/Choose.cpp`, and exposed to the Python simulator as `CHOOSE_CARD`; scenario verification is in `scripts/verify_mother_scenario.py`.

Run the deterministic one-card scenario after rebuilding the native library and bridge:

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_current_standard_scenarios.py
```

It builds deterministic scenarios for the four Deios effect categories. The existing Earthen Drake scenarios check end-of-turn trigger doubling and verify that an opponent's Deios does not double the friendly Drake's trigger. `scripts/verify_deios_scenario.py` checks that Fire Elemental deals 8 damage under Deios, Imp Gang Stooge adds four Imps when its Deathrattle is doubled, and Life Tap draws two cards and deals 4 damage. Deios doubles friendly Battlecries and Deathrattles through player auras, checks for an active friendly Deios when a Hero Power resolves, and doubles friendly end-of-turn triggers in `Trigger.cpp`.

These scenarios cover representative paths for each Deios effect. They do not certify every interaction between Deios and every current card. The controlled Mother Drake pilot is limited to that specific list until the broader rules and card-coverage gate is satisfied.

The audit of the full published Mother Drake Warlock list and the remaining unsupported cards is in [MOTHER_DRAKE_WARLOCK_COVERAGE.md](MOTHER_DRAKE_WARLOCK_COVERAGE.md).

While building the scenario, the bridge was found to report the hero's base maximum health instead of current health. `player_observation` now uses `Hero::GetHealth()`, so damage is visible in simulator snapshots and model inputs. Death Knight cards remain a later slice: this RosettaStone revision has no default Death Knight hero or hero-power mapping in `Cards::GetHeroCard` / `GetDefaultHeroPower`, so a Death Knight game currently fails during setup even though deck validation recognizes its class and cards.

## Run the sample from the project root

In WebStorm's terminal, with the ManaMind virtual environment active:

```powershell
.\.venv\Scripts\python.exe -m manamind.integrations.rosettastone.rosettastone
```

The CMake build directory already contains the configured bridge target. If bridge C++ source changes, rebuild it from the project root in a Visual Studio x64 developer environment:

```powershell
cmake --build .\integrations\rosettastone\build --target mana_rosetta_bridge --config Release --parallel 4
```

`mana_rosetta_bridge*.pyd` is emitted to `integrations/rosettastone/build/python`. The Python adapter finds it there. The upstream library and dependencies are under `vendor/` and build directories; those generated files should not be hand-edited.

`Game`'s destructor is defined in the RosettaStone library instead of inline in the header. The simulator creates `Game` in that library and owns it through the separate Python bridge; keeping destruction in the same binary module avoids a reproducible Windows access violation when a Python session is released.


## Self-play policy prototype

`train_selfplay.py` adds a separate Policy Network. The native bridge attaches semantic features to each enumerated legal action (action/card type, card stats, hand position, and source/target combat stats); card identity is mapped through the saved card vocabulary, while transient entity IDs are retained only for applying actions and are not fed to the model. The policy embeds the player's ordered hand and each action's card identity. Opponent hand identities and deck order remain hidden. Policy checkpoints save their catalog and vocabulary; compatible older policy checkpoints can resume with a fresh optimizer state.

Each seat uses the same stochastic policy. After a terminal result, decisions made by the winner receive reward `+1`, the loser's decisions receive `-1`, and draws receive `0`; one REINFORCE update is made after each game batch. Deck seats alternate by seed. Example run:

```powershell
.\.venv\Scripts\python.exe .\train_selfplay.py --games-per-cycle 8 --cycles 5
```

The default output is `checkpoints/policy_selfplay_v1.pt`; pass `--resume` to continue it. The policy is separate from the Value Network and currently learns only from terminal outcomes. This is a minimal RL wiring milestone: it does not yet prove improvement, supports only the M.O.T.H.E.R. choice among card-choice/Discover windows, and does not represent the full current Standard pool. Older compatible policy checkpoints migrate named action weights and receive zero-initialized weights for new action features such as Location activation and Tradeable; their optimizer state is restarted on resume. Compare checkpoints against fixed opponents over held-out seeds before treating any win rate as meaningful.

Evaluate on separate seeds, with the policy on each seat and baseline-vs-baseline control matches:

```powershell
.\.venv\Scripts\python.exe .\evaluate_policy.py --checkpoint .\checkpoints\policy_selfplay_v1.pt --pairs 10 --seed 10001 --report .\reports\policy_eval.json
```

For every held-out seed, the evaluator runs both policy seats and both deck orders. The JSON report includes results by seat/deck order, a decisive-game Wilson interval, baseline-vs-baseline control, seeds, and limitations. To compare two checkpoints directly, also pass `--opponent-checkpoint <older-or-initial-policy.pt>`. The trainer stores the next simulator seed and random generator states in its checkpoint so `--resume` can continue without reusing the prior training seeds.

## Deck and action API

`inspect_decks(player1_deck, player2_deck, player1_class="WARLOCK", player2_class="PALADIN")` accepts exactly 30 known RosettaStone card IDs per deck. Shuffling is disabled to make the opening hand reproducible; Player 1 starts. It returns `(GameState, actions)` for inspection only.

`validate_deck(deck, player_class="WARLOCK", format="STANDARD")` returns a tuple of validation messages; an empty tuple means valid according to the pinned engine metadata. It checks 30 cards, known and collectible IDs, class compatibility, the selected card-set pool, and copy limits (counted by DBF ID). `validate_decks(...)` checks both sides. `make_simple_test_deck(player_class=..., format=...)` builds a low-cost minion test deck from that pool.

`SimulatorSession(player1_deck, player2_deck, player1_class="WARLOCK", player2_class="PALADIN", format="STANDARD")` creates a deterministic opening by default and holds the live RosettaStone game. It validates both decks before starting, including the rules-coverage admission gate. Set `shuffle=True`, `random_start=True`, and `random_seed=N` for a reproducible shuffled match with a seeded random starting player. Use `observation(perspective="ACTIVE")`, `legal_actions()`, and `apply_action(action)` to advance it. Pass an action returned by the current `legal_actions()` call; stale or illegal actions raise `ValueError`. `apply_action` returns the next active player's `GameState`. The `is_complete`, `needs_choice`, and `result` properties report terminal/choice status and the winner (`PLAYER1_WIN`, `PLAYER2_WIN`, `DRAW`, or `None` while active).

Current action records use these forms:

- `PLAY_CARD`: `hand_index`, `card_id`, `field_position` (`-1` means append), and `target_entity_id` (`None` when no target is needed).
- `ATTACK`: `attacker_entity_id` and `target_entity_id`, filtered by RosettaStone attack rules such as Taunt and checked with the engine’s final target validator.
- `HERO_POWER`: `target_entity_id` when the power can currently be used.
- `CHOOSE_CARD`: `choice_entity_id` and visible card features while resolving M.O.T.H.E.R.'s Battlecry.
- `ACTIVATE_LOCATION`: `source_entity_id`, card identity, and `target_entity_id` when its effect chooses a Character.
- `TRADE_CARD`: `hand_index` and `card_id` for a Tradeable card when the player has 1 mana and the deck is not empty.
- `END_TURN`.

Supported actions currently include basic card plays, attacks, hero powers, targeted and untargeted Location activation, Tradeable card exchanges, and ending the turn. The bridge checks current legal options again before applying an action, then advances the simulator to the next main-action window. Card identity stays in the viewed player's SELF hand only. With `perspective="PLAYER1"` or `"PLAYER2"`, that player sees their own hand; the other hand and both deck orders remain hidden. `ACTIVE` means the player whose turn is active.

The baseline generator in `manamind.integrations.rosettastone.rollout` plays the cheapest available minion only while its board has a free slot, then takes the first legal attack, otherwise ends the turn. For M.O.T.H.E.R. it selects the most expensive hand card. The bridge omits minion plays when the board is full and advertises only attack targets accepted by the engine’s final target validator. A visible no-progress guard stops a rollout if an action fails to change the observed game state. It records a pre-action position for both player perspectives and labels each with that perspective’s terminal outcome. It can shuffle decks and randomize who starts reproducibly from a seed. Unsupported Discover/card-choice windows stop the rollout; it does not silently label an incomplete game. The bridge still omits mechanics/actions, the validator has no current ban list, and this deliberately weak policy creates biased data. The duplicate-card fixture used in smoke checks is not a legal deck or a meaningful training source.

## Current Standard multi-deck preparation

`data/samples/standard_meta_deck_pool_20260928.json` holds five selected published lists across four classes. `scripts/audit_standard_meta_coverage.py` inventories every used card ID, its catalog mechanics, and whether a `CardDef` registration exists. The current matrix is `docs/STANDARD_META_COVERAGE_20260928.md` with card-level data in `reports/standard_meta_coverage_20260928.json`.

`train_selfplay.py` accepts this `decks` array and cycles through all unordered pairs. The loader validates every list before training, so unsupported cards reject the pool. `evaluate_policy.py` evaluates every pair with both policy seats and deck orders. The implemented groups cover Priest healing/draw and Reborn (`CORE_CS2_004`, `CATA_302`, `CAP_801`, `CAP_804`), Deathrattle replay (`JAIL_940`), area/targeted damage (`CATA_582`, `CORE_REV_990`, `CORE_BAR_311`, `CATA_308`, `CATA_584`), Tradeable plus Silence (`CORE_SW_066`), Druid damage/Armor (`TIME_702`, `END_007`), Spiderling's turn-only hero Attack, Carrier Whelp's random low-cost Dragon generation, Prescient Slitherdrake's Dragon-dependent cost reduction, Spider Rider's after-hero-attack draw, Kindred for Dragons and Holy spells from the previous turn (`TLC_600`, `TLC_816`), and Naralex's first-Dragon-per-turn discount (`EDR_844`). More recent scenarios cover `CATA_585` Torch's overkill return, `DINO_426` Ritual of Life's filtered Discover and 2/3 copy, `END_011` Acceleration Aura's three turns of temporary Mana, `CATA_131` Felwood Treant's 4-Mana held threshold, `CATA_140` Merithra's 25-Mana held threshold and 1-cost generated Dragons, `EDR_492` Mother Duck's three Rush Ducklings, both Choose One branches for `EDR_463` Twilight Influence and `JAIL_201` Secret Ingredient, `JAIL_875` Staff of Trickery's post-attack Druid Discover discounted by the hero's attack at attack time, `FIR_907` Amirdrassil's summon/Armor/draw sequence and progressive Mana refresh, `JAIL_200` Infest the Scullery's two random minions scaled to hero attacks across the game, and `JAIL_421` Warptooth's distinct-friendly-damage trigger from hand or deck, plus `EDR_846` Shaladrassil's regular and Corrupted Dream outputs and all five variant effects, and `CAP_806` Raith Van Geist's Reborn-history resurrection and forced attacks. RosettaStone tracks previous-turn Dragon plays and Holy spell casts; scenario checks confirm both discounts. Held-Mana tracking counts card, Hero Power, and Tradeable payments. Start-of-turn temporary Mana now expires before start-of-turn triggers, allowing those triggers to grant Mana for the current turn. The bridge includes card race in player-visible hand data. Focused scenarios check the new effects. The latest audit has 74 unique cards with 11 missing rules; 63 are registered or need no text rules, and only the two Warlock lists pass the complete card gate. Continue filling Warrior, Druid, and Priest coverage, then complete full matches before one pooled training and one final held-out evaluation.

## Generate baseline-labeled positions

The generated fixture is in `data/samples/rosettastone_test_decks.json`. It contains two 30-card, collectible minion lists for Warlock and Paladin that pass this pinned engine's Standard checks. To use your own lists, prepare a JSON config with two arrays of exactly 30 known card IDs and optional player class names:

```json
{
  "player1_class": "WARLOCK",
  "player2_class": "PALADIN",
  "player1_deck": ["CARD_ID_1", "..."],
  "player2_deck": ["CARD_ID_1", "..."]
}
```

The JSON above shows the field shape only. Replace both placeholder arrays with exactly 30 known card IDs. The rollout command runs the validator before simulating any games.

Run from the project root; the output must be a new file and will not overwrite an existing dataset:

```powershell
.\.venv\Scripts\python.exe -m manamind.integrations.rosettastone.rollout .\data\samples\rosettastone_test_decks.json .\data\processed\rosetta_baseline.jsonl --games 10 --seed 1
```

Each decision position is written twice, once from each player's legal perspective, under a shared `game_id`. This keeps both hands private and lets the trainer split all states from one match into the same group. The existing `load_labeled_dataset()` reads this JSONL, but do not train on these weak-policy games until the stale format pool, simulator coverage, and dataset balance have been reviewed.

## Next integration work

1. Reconcile the pinned engine's old Standard card pool with the desired Hearthstone format; add explicit ban-list rules if current-format data becomes available.
2. Improve snapshot parity: card mechanics/race, weapons, hero power, and non-minion board entities.
3. Expand legal-action coverage and implement player choices/Discover; verify target and attack rules across both perspectives.
4. Add held-out evaluation against fixed policies and verify that self-play updates improve win rate over multiple seeds.
5. Expand game coverage, card-choice/Discover handling, and Standard metadata before treating self-play metrics as Hearthstone strength.

## Toolchain and licensing

This build uses Windows Visual C++ Build Tools, CMake 3.31.6, Ninja, vcpkg, Python 3.12, and pybind11. The upstream source is distributed under GNU AGPL-3.0. Keep it as a clearly marked third-party checkout and review the license obligations before distributing a combined application.

Upstream links: [RosettaStone repository](https://github.com/utilForever/RosettaStone), [Python extension sources](https://github.com/utilForever/RosettaStone/tree/main/Extensions/RosettaPython).

`EDR_846` Shaladrassil adds the five classic Dream cards, or their five Corrupted versions after a higher-cost card is played while Shaladrassil is held. `CAP_806` Raith Van Geist records minions whose Reborn effect actually resolved, resurrects them from the graveyard, and forces each to attack a random enemy minion. `FIR_959` Fyrakk the Blazing is immune to Fire spells and casts random Fire spells up to 15 mana. Focused C++ scenarios cover these effects. The current five-deck audit is 64/74 cards, with 10 card rules still missing; full-pool training and evaluation remain gated on the remaining card support and complete matches.
