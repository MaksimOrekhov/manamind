# TIME_855 — Arcane Barrage design audit

Verdict: **BLOCKED_DESIGN_REVIEW / MORE_RULES_EVIDENCE_REQUIRED**.
No Barrage declaration or implementation added.

## Established inputs

Pinned snapshot identifies `TIME_855`, dbfId `119528`, Mage Arcane spell, cost 3; printed damage values are 3 to the selected enemy and 2 to two other random enemies. Snapshot/hash are recorded in [the rules review](DAMAGE_GROUP_RULES_REVIEW.md).

Its [external metadata record](https://hearthstone.wiki.gg/wiki/Arcane_Barrage) corroborates identity/text but contains no adequate selection/reaction timing specification. No current-client replay or independently demonstrated Barrage ordering was obtained. RosettaStone behavior would be an implementation comparator, not a substitute for missing rules.

The text supports treating the selected enemy as excluded from 'other'. It suggests two distinct extras, but that interpretation alone cannot establish an executable without-replacement selection algorithm, selection timing, reaction barriers, empty-set behavior or exact RNG mapping.

## Questions resolved separately

| Dimension | Established / proposed expectation | Missing evidence / admission |
|---|---|---|
| Explicit target | Enemy character, hero or minion, under current legal target requirements | Metadata legality review remains independent of random-target legality |
| 'Other' | Selected entity excluded from extra outcomes | Confirm identity-based exclusion after transform/removal; do not reinsert target because its state changed |
| Replacement | Two different extras is the text-level hypothesis | Without-replacement sampling law and order not demonstrated; do not implement arbitrary duplicate suppression |
| Initial candidate set | Enemy characters other than selected target, with random-target mortality restrictions as a candidate contract | Are extras frozen before first hit or selected live later? Does the first extra's reaction alter the second candidate set? |
| Insufficient extras | Likely resolve available extras only | No replay confirming zero/one extra behavior, wasted hits or RNG consumption; keep unknown |
| First selected minion becomes mortal | It is already excluded by 'other' | Does its damage reaction complete before extra selection? Does any forced death boundary intervene? |
| Extra target becomes mortal/removed | Group versus sequential topology determines result | Predrawn second extra, live redraw, no-retarget skip and fail-closed behavior cannot be chosen from text |
| Spell Damage | Under ordinary printed-hit hypothesis, 3+B and 2+B; never `MISSILE_TOTAL` | B may change between instructions; number of instructions itself unresolved. Requires live-aura test/control |
| Death/Reborn | Normal phase model would defer death removal until outer spell boundary | No evidence this spell has no special step/death boundary; confirm in replay rather than assuming |
| Reactions | Architecture can implement complete reactions per event or after area mutation | Which events form one group is unresolved |
| Clone/RNG | One deterministic stream, no reroll/supported-only pool | Expected number/order of selections depends on unresolved topology |

## Topologies the local infrastructure could represent

1. One heterogeneous apply-all group: select two extras up front, mutate 3/2/2, then react.
2. First single packet/reactions, then select distinct extras and apply a two-packet group.
3. Three sequential single-packet groups: each extra selected live after preceding reactions, remembering exclusions.

All can use value packet intents and local continuation. They disagree observably when first-hit reactions generate new targets, kill a later target or change Spell Damage. General AoE rules do not select a topology for a fixed-count multi-target spell. The architecture is sufficient machinery **once** topology is reviewed; it is not sufficient rules evidence now.

## Minimum evidence request

Capture current client build, full visible setup and Power.log (or equivalently inspectable replay) for:

- Selected enemy plus exactly two extras, with distinct IDs and damage reactions recording when they activate.
- Selected target plus one and zero extras; record both packets and selection events where observable.
- Reaction to selected damage that summons a new enemy minion before the extra outcomes.
- First extra's reaction mortally wounds/removes another candidate; distinguish snapshot from live retargeting.
- Spell Damage source that changes contribution as a result of the first event, plus a static +2 control.
- Shielded extra and lethal Reborn extra; record phase/death ordering and original/new identities.

Avoid inferring internal RNG draw count from a single final board or from animation order. Native deterministic mapping can be simulator-owned after outcome distribution/timing is established; parity need not reproduce Blizzard's hidden PRNG implementation.

## Exact path to a bounded future declaration

If evidence establishes topology 2, for example, specify: finish selected single group; build reviewed live extras set excluding selected ID; sample up to two distinct entries under a documented simulator selection law; evaluate one current amount for extras if modifiers stable; run their apply-all group; then outer spell death phase. Alternative evidence requires alternative parameters, not a card-ID branch.

Add a genuinely reusable `DistinctRandomTargetsV1` selector only after its minimum/maximum count, exclusions, snapshot timing, mortality policy and insufficient-target rules are all reviewed. Require an independent second declarative control variation without renderer changes. Unique unresolved topology remains deferred/CUSTOM-first, never a new generic operation to hide one card.

**No architecture scheduler redesign is proved by Barrage. No implementation is justified yet.** The next implementation package should deliver the local damage barrier on admitted consumers, preserving this blocker.
