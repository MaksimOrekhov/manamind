#pragma once
#include "manaengine/engine.hpp"
#include <array>
#include <cstddef>
#include <string_view>

namespace manaengine {
// Hero Power v1 (ENGINE-GATE-0). A Hero Power is a catalog card of type HERO_POWER whose behaviour is an
// EFFECT_COMPOSITION effect list, executed by the same effect primitives as spells (Damage, Heal pipeline v1, GainArmor).
// A player's class is NOT proof of their current Hero Power: sessions store the current power identity explicitly and this
// table is only the reviewed *starting* power of a newly created prototype session.
struct ReviewedBaseHeroPower { std::string_view player_class, card_id; };
inline constexpr std::array<ReviewedBaseHeroPower,4> reviewed_base_hero_powers{{
    {"HUNTER","HERO_05bp"},{"MAGE","HERO_08bp"},{"PRIEST","HERO_09bp"},{"WARRIOR","HERO_01bp"}}};
// Empty when the class has no reviewed base power (unknown/unsupported classes stay rejected).
inline std::string_view reviewed_base_hero_power(std::string_view player_class){
    for(const auto& row:reviewed_base_hero_powers)if(row.player_class==player_class)return row.card_id;
    return {};
}
// Selectors that make the Hero Power action carry a target handle. EnemyHero/Self/SelfHero-style selectors resolve
// without a handle, so the advertised action has no target (Steady Shot, Armor Up!).
inline bool hero_power_selector_is_explicit(TargetSelector selector){
    return selector==TargetSelector::ExplicitCharacter||selector==TargetSelector::ExplicitEnemyCharacter||
           selector==TargetSelector::ExplicitMinion||selector==TargetSelector::ExplicitDamagedEnemyMinion||
           selector==TargetSelector::ExplicitFriendlyMinion||selector==TargetSelector::ExplicitDamagedMinion||
           selector==TargetSelector::ExplicitFriendlyCharacter;
}
// Reviewed (kind, selector) pairs for a supported Hero Power step. Anything else is rejected at catalog load.
inline bool hero_power_step_is_reviewed(const EffectStep& step){
    const bool bare=!step.lifesteal&&step.summon_card.empty()&&step.summon_condition==SummonCondition::None&&
                    step.conditional_extra_count==0&&step.discard_school==DiscardSpellSchool::None&&
                    !step.requires_previous_discard&&step.random_count==0&&!step.exclude_previous_target&&!step.evidence_constraint;
    if(!bare||step.amount<=0||step.amount>1000)return false;
    switch(step.kind){
    case EffectKind::Damage:return step.target==TargetSelector::ExplicitCharacter||step.target==TargetSelector::EnemyHero;
    case EffectKind::Heal:return step.target==TargetSelector::ExplicitCharacter||step.target==TargetSelector::ExplicitFriendlyCharacter;
    case EffectKind::GainArmor:return step.target==TargetSelector::Self;
    default:return false;
    }
}
} // namespace manaengine
