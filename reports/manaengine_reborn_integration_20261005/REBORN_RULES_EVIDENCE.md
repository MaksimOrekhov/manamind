# Reborn rules evidence follow-up (historical report port)

Ported without production-code changes from `claude/reborn-prototype` commit
`a35ddc6f0b0bd736d6a3b30e2a31884e39204cc1` during repository consolidation.
This preserves the previously reviewed evidence trail; it does not promote a
rules or verification status. The historical links were not independently
re-fetched during this port.

Date: 2026-10-05. Branch `claude/reborn-prototype` at `6b5555e`. Report only; no production change.

Verdict: **REBORN_RULES_PARTIALLY_RESOLVED**

## Evidence collected

| ID | Source | Kind | What it shows |
|---|---|---|---|
| E1 | [Jetz72 gist "Reborn vs Added Deathrattle"](https://gist.github.com/Jetz72/6b60de57d22d901161861d71cf4bdaac), 2019-08-08 | Live-client `Power.log` (tier 2, 2019 client) | Candletaker (Reborn) with an added Deathrattle (On a Stegodon) dies at `ZONE_POSITION` 2. Inside the `DEATHS` block the minions to its right shift left at once (sequential removal). A `TRIGGER` block with `TriggerKeyword=DEATHRATTLE` summons Stegodon at position 2. **Afterwards** a new entity (id 128, `CREATOR=18`) is created at position 2 with `HEALTH=2`, `DAMAGE=1`, `HAS_BEEN_REBORN=1`, then `REBORN=0`. Stegodon is pushed right to position 3. The enchantment leaves play (`REMOVEDFROMGAME`). |
| E2 | [Blizzard forum "Teleporting reborn minions"](https://us.forums.blizzard.com/en/hearthstone/t/teleporting-reborn-minions/13808), 2019-09-10/11 | Client video report (tier 2) plus a rules-expert explanation by Jetz (tier 3) | Board Bone Wraith (0), Wasteland Assassin (1), Silver Hand Recruit (2). Wraith and Assassin die together. Observed result: the Reborn copies end up **on separate sides** of the Recruit. Explanation: each dead minion remembers the numerical position it died in. The Assassin's Reborn triggered first "since it was in play before the Wraith" and was summoned into position 1 (right of the Recruit). Then the Wraith was summoned into position 0. Final order: Wraith, Recruit, Assassin. No Blizzard staff reply. |
| E3 | hearthstone.wiki.gg Reborn notes | Rules documentation (tier 3) | "Deathrattles are resolved before Reborn, regardless of the order in which the cards were played", with the Khartut Defender / Sylvanas example. 1 Health, original maximum Health, no enchantments, a unique copy. |
| E4 | hearthstone.wiki.gg Advanced rulebook, rule 7 | Rules documentation (tier 3) | Deaths are queued and resolved in order of play. |
| E5 | RosettaStone `ProcessGraveyard`/`SummonReborn` | Simulator (tier 5) | Removes dead minions in queue order, recording each one's position at its own removal. Runs all death tasks, then Reborn at the recorded position, clamped. |
| E6 | twanvl `hearthstone-battlegrounds-simulator` `battle.cpp` | Battlegrounds simulator (tier 4) | Position = number of surviving minions to the left. Processes deaths left to right, with Deathrattle then Reborn interleaved per minion. Its own comment says the ordering in Battlegrounds is "not clear". A summon fails on a full board. |

## Results per question

### 1. Board slot

- **Single death on a side (A X B, X dies): STRONGLY_CORROBORATED.** E1 shows the return at the death position. E2, E5 and E6 agree: A X B. It is not upgraded to VERIFIED because the only client evidence is from 2019 and no current-client replay was captured.
- **Several deaths on one side (A X B Y C, X and Y die, both Reborn): UNRESOLVED.** The best-supported model (E1 sequential removal + E2 observation + E5) is:
  1. Deaths are processed in order of play. Each removal records the minion's current zone position, after earlier removals in the batch.
  2. Reborns return in order of play, each inserted at its recorded position in the current board (clamped).

  Predicted results with this model:
  - X played before Y: X recorded 1, Y recorded 2 → final **A X Y B C**.
  - Y played before X: Y recorded 3, X recorded 1 → final **A X B C Y**.

  The original order is *not* generally preserved. E2 directly refutes the prototype's "restore original relative order" rule: that rule predicts Wraith, Assassin, Recruit, but the client showed Wraith, Recruit, Assassin. It also refutes the E6 model (Assassin, Wraith, Recruit). One question stays open: is the recorded index the position at the minion's own sequential removal or its pre-batch position? E2 cannot tell them apart. E1 only shows sequential shifting, with one death on the side. There is also no current-client confirmation that the 2019 quirk was not changed.
- **A single Reborn when another minion on the same side also died: UNRESOLVED.** The models diverge here too. Example D X B, where D and X die and X has Reborn, with X played before D: the sequential model gives B X; the prototype gives X B.

### 2. Order of several Reborns

- **Same controller: STRONGLY_CORROBORATED — order of play** (E2 explicit, consistent with E4 and E5).
- **Both players: UNRESOLVED.** No direct evidence. E4's order-of-play rule probably extends across players. This is inert in ManaEngine today: the boards are separate and there are no on-summon triggers; only `activation_sequence` assignment order depends on it.

### 3. Deathrattle and Reborn

- **The minion's own Deathrattle (including an added one) before its Reborn: VERIFIED for the 2019 client** (E1 log order).
- **All Deathrattles of the batch before any Reborn, across different minions: STRONGLY_CORROBORATED** (E3 explicit example, E5). E6 interleaves per minion, but it is a Battlegrounds model that states uncertainty.
- **New fact from E1:** a Reborn copy is inserted at its own recorded position even when a Deathrattle has already summoned there. It lands *left* of the Deathrattle summon. The prototype currently fails closed when the board changed before Reborn, so it is safe, not wrong.

### 4. Board capacity

**UNRESOLVED.** No direct evidence for a Reborn meeting a full board, or a board filled by earlier death-phase summons. The general summon-fails-when-full behaviour (E6, and the summon contract) suggests the Reborn fails. ManaEngine cannot reach this case today, because Deathrattles never summon and an intervening board change fails closed.

## Consequences for the prototype (not changed here)

- The prototype is consistent with the evidence when **at most one minion of a side dies in the batch** (a single death, or deaths only on the other side).
- For **two or more deaths on the same side with at least one Reborn**, its relative-order rule contradicts the only client observation (E2).
- Smallest correct next step: implement the best-supported model (sequential recorded position, insertion in order of play) **and** gate the unresolved case with an evidence constraint until a current-client replay confirms it.

## Recommended EvidenceConstraint (do not implement in this branch)

`RebornMultiDeathSlotUnverified` (serialized `REBORN_MULTI_DEATH_SLOT_UNVERIFIED`).

- **Raise it when** a Reborn copy is summoned from a death batch in which the **same side lost two or more minions**, Reborn or not.
- **Do not raise it for:**
  - a single Reborn death on a side, even with deaths on the other side;
  - batches without Reborn.
- **Why this granularity:** it covers exactly the cases where the plausible models diverge (E2 vs prototype vs E6, sequential vs pre-batch index). It leaves the corroborated common case unflagged.
- **Cross-side ordering** needs no constraint until on-summon triggers or other order-sensitive summon reactions exist. When they do, add `RebornCrossSideOrderUnverified`.

## Replays that would close the gaps

A current-client Power.log of each of these, comparing final `ZONE_POSITION`s:

1. A X B Y C, with X and Y both Reborn and dying together. Run twice: once with X played first, once with Y played first.
2. D X B, with D (no Reborn) and X (Reborn) dying together. Run with X played first and with D played first.
3. One Reborn minion on each side dying together, recording the `FULL_ENTITY` creation order.
4. A Reborn minion dying on a board where earlier death-phase summons fill the remaining slots.
