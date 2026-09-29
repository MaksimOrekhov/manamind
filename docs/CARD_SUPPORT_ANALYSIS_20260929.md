# Card support audit — 2026-09-29

This audit covers five saved Standard lists (74 unique cards) and a deterministic stratified extension sample of 26 collectible Standard cards. It is a triage inventory, not a claim of current metagame representation, complete rules correctness, or deck eligibility.

## Results

| Measure | Count |
|---|---:|
| Selected lists | 5 |
| Selected-list cards registered or textless | 64 / 74 |
| Selected-list cards missing nonempty-text registrations | 10 |
| Extension sample | 26 |
| Total triaged cards | 100 |

Route hypotheses: **AUTO 15**, **COMPOSABLE 32**, **MISSING_PRIMITIVE 19**, **CUSTOM 32**, **UNKNOWN 2**. AUTO and COMPOSABLE describe a possible implementation route; they do not indicate verified behavior.

The five saved lists remain blocked by the stricter training gate. Dragon Warrior is 14/17 registered or textless, Attack Druid 17/20, Quest Priest 13/17. Mother Drake and Combo Drake Warlock are 19/19 by direct registration and have historical pilot matches, but their scenario and dependency gates have not been re-run under the stricter audit.

The first alias batches add 20 generated registrations, but none of the 10 missing IDs in the five selected lists is one of these aliases. Thus selected-list registration coverage remains 64/74; the alias work expands the broader Core pool and validates the generator path, not the selected-deck gate.

## Reusable Core alias finding

The current Standard catalog contains **47** Core IDs with a legacy CardDef source, matching `countAsCopyOfDbfId`, and a stripped ID. **42** have equal normalized rules text; **40** of those lack a direct Core definition, while two already have one. Five metadata-linked entries have different rules text and are excluded.

The first implementation package is a deterministic alias declaration generator for these eight IDs:

| Current Core ID | Existing base definition | Effect coverage in the package |
|---|---|---|
| `CORE_BAR_801` | `BAR_801` | Targeted damage and fixed Rush token |
| `CORE_SW_108` | `SW_108` | Damage and add a fixed card to hand |
| `CORE_BT_072` | `BT_072` | Freeze and summon |
| `CORE_BAR_310` | `BAR_310` | Deathrattle healing |
| `CORE_AV_337` | `AV_337` | Deathrattle token summons |
| `CORE_BAR_541` | `BAR_541` | Damage and Discover |
| `CORE_KAR_062` | `KAR_062` | Conditional Battlecry and Discover |
| `CORE_BT_156` | `BT_156` | Dormant timing and Rush metadata |

Matching text and metadata provide a candidate relationship only. Three bounded additions now register 20 aliases. The validator checks metadata links, normalized text, dependencies and duplicate registrations. A parity scenario checks base and Core `CardDef` properties and task counts for all 20 IDs; four independent game scenarios check damage-plus-add-card, damage-plus-token, damage-plus-Taunt-tokens, and damage-plus-draw. The bridge smoke checked deck validation, state observation and legal actions for four representative Core cards. These tests establish only the stated scopes. Two aliases include Discover with a dynamic pool, and remain ineligible for strict training. The other 20 equal-text candidates remain queued pending measurement of the separate effect-composition generator pilot.

## Effect composition pilot

A second generator, [generate_effect_composition.py](../scripts/generate_effect_composition.py), compiles a strict allowlisted IR into ordinary C++ Tasks. Four pre-existing definitions were migrated: `CORE_CS2_004` (enchant then draw), `END_007` (damage, temporary hero attack, draw, armor), `CAP_801` (enchant then Reborn), and `CORE_SW_066` (Battlecry Silence). Four independent scenario tests passed (20 assertions), and bridge smoke accepted all four deck lists and returned observations/legal actions. `CATA_302` remains manual because its implementation heals by the amount of damage taken; substituting a generic full heal could change modifier and source behavior. See `integrations/rosettastone/card_rules/effect_composition.generated.json` and `vendor/RosettaStone/Tests/UnitTests/PlayMode/CardSets/ManaMindEffectCompositionTests.cpp`.

Neither generator changes the selected-deck missing count: it remains 10/74. The alias and composition pilots validate implementation routes in the wider current Core pool; they do not yet complete the five chosen decks or establish training eligibility.

## Capability and dependency inventory

The checkout contains 107 SimpleTasks headers. Source contracts and limitations were inspected for DamageTask, HealFullTask, DrawTask, SummonTask, DestroyTask, DiscoverTask, RandomMinionTask, AddEnchantmentTask, and QuestProgressTask. Random/Discover candidates that cannot be resolved to an exact pool remain `UNKNOWN_POOL`. Literal generated-card and enchantment references are recorded as unverified dependency edges.

See the complete generated Markdown copy at [reports/card_support_analysis_20260929.md](../reports/card_support_analysis_20260929.md), per-card evidence and SHA-256 source manifests in [reports/card_support_analysis_20260929.json](../reports/card_support_analysis_20260929.json), and the fixed 100-card sample in [data/samples/card_support_analysis_sample_20260929.json](../data/samples/card_support_analysis_sample_20260929.json). The task/capability file inventory is [integrations/rosettastone/card_rules/capabilities.json](../integrations/rosettastone/card_rules/capabilities.json).

Rebuild these artifacts from the repository root with:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_card_support_analysis.py
```

The saved catalog is valid as of 2026-09-27, and the selected list pool is dated 2026-09-28. The source fingerprint records RosettaStone revision `e10749b5f0c08d3a6135bce317cb11d1738846ad` and the local modifications present at audit time. No build, match, training, or model evaluation is part of this audit.
