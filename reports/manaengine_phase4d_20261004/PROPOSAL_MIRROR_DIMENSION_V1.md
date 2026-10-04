# CAPABILITY PACKAGE PROPOSAL — `manaengine_holding_dragon_fixed_summon_v1`

## Semantic contract

Extend typed `SUMMON_FIXED` with an optional `HOLDING_DRAGON` condition and bounded extra summon count. At effect resolution, inspect the caster's current hand for any card whose pinned minion types include `DRAGON`. Summon the declared fixed minion once, plus the declared extra count when the condition holds. Use the existing board capacity and summon path. This is a hand-state check; a Dragon only on board does not qualify.

## Candidate cards

- Reviewed root: `TIME_006` — Mirror Dimension.
- Unsupported prototype roots before this package: 1.
- Candidate's pinned text: `Summon a 0/4 minion with Taunt. If you are holding a Dragon, summon another.`
- Fixed dependency: `TIME_006t1` — Mirrored Mage, 0/4 Taunt. It is present in the selected Standard metadata snapshot and its Full Definition Slice.
- Expected declaration-only consumers: 1 after the shared typed condition exists. A second native control declaration uses the same contract with a different additional count; it is test-only and does not claim another supported card.

## Existing primitives

- `EFFECT_COMPOSITION` and typed `SUMMON_FIXED`.
- Exact fixed dependency validation, summon identity creation and seven-slot board limit.
- Pinned minion-type metadata on hand entities.

## Required shared changes

- Add an allowlisted `SummonCondition.HOLDING_DRAGON` plus `conditional_extra_count` to the existing typed effect schema.
- Evaluate the condition once as the summon instruction resolves; do not add card-ID dispatch, a new scheduler, a new observation feature, or a general formula language.
- No C++ adapter observation change or schema bump.

## Rules evidence and timing

- Blizzard Card Library: [Mirror Dimension](https://hearthstone.blizzard.com/en-gb/cards/119541-mirror-dimension/), official text and exact card identity.
- Pinned metadata: `data/cards/standard_current_enUS.json`, including `TIME_006t1`; dependency details cross-checked in `DYNAMIC_GENERATION_FULL_DEFINITION_SLICE.json`.
- Reviewed snapshot boundary: the conditional reads the caster's hand when the effect step resolves. Summoning one copy does not change hand membership; additional copies are capped by available board slots.
- Confidence: medium-high for the text and dependency identity. No client replay or Power.log captured for this specific interaction.

## Tests

- No held Dragon → one exact 0/4 Taunt.
- Dragon held → two exact tokens.
- Dragon only on board → one token.
- Independent control declaration varies the extra count without renderer changes.
- Adapter path uses actual legal action and exports two exact token instances.
- Strict parser rejects unknown condition values; native catalog validation rejects condition/count mismatch and condition fields on non-summon effects.

## CUSTOM / deferred outliers

- None in this one-root package.
- No canonical evidence or training admission is promoted by this implementation.

## Completion record

- Package ID: `manaengine_holding_dragon_fixed_summon_v1`.
- Implementation: complete; root `TIME_006` plus fixed token dependency `TIME_006t1`.
- Declaration-only root consumers: 1/1; CUSTOM/deferred outliers: 0.
- Shared changes: typed C++ `SummonCondition`, contract validation/resolution, pybind exposure and strict Python parsing; one root declaration and one vanilla dependency declaration. No observation/schema change.
- Native: PASS, 41 scenario groups / 710 assertions. Scenarios cover absent Dragon, Dragon in hand, Dragon only on board, and an independent declaration with a different conditional count.
- Adapter: PASS, full ManaEngine adapter file, 23 passed; actual legal action exports two exact `TIME_006t1` minions.
- Generic identity guard: PASS (201 reviewed AST exceptions; CUSTOM ownership checked). Ruff: PASS. `git diff --check`: PASS.
- Observed elapsed wall span: 12m02s (15:50:10–16:02:12 UTC); 4 correction cycles and 3 builds.
- No card-ID behavioral branch, canonical evidence promotion, training admission, or DECK_READY claim.
