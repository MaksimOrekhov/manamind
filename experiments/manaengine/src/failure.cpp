#include "manaengine/failure.hpp"
namespace manaengine {
FailureKind failure_kind_of(FailureCode code) {
    switch(code) {
    case FailureCode::LEGACY_UNTYPED: return FailureKind::EngineDefect;
    case FailureCode::DAMAGE_DEPTH_BUDGET_EXCEEDED: return FailureKind::BudgetLimit;
    case FailureCode::DAMAGE_PACKET_BUDGET_EXCEEDED: return FailureKind::BudgetLimit;
    case FailureCode::DAMAGE_WORK_BUDGET_EXCEEDED: return FailureKind::BudgetLimit;
    case FailureCode::CATALOG_REFERENCE_MISSING: return FailureKind::EngineDefect;
    case FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION: return FailureKind::EngineDefect;
    case FailureCode::DAMAGE_TARGET_LOST: return FailureKind::EngineDefect;
    case FailureCode::DECLARATION_CONTRACT_VIOLATION: return FailureKind::EngineDefect;
    case FailureCode::INVALID_DAMAGE_PACKET: return FailureKind::EngineDefect;
    case FailureCode::INVARIANT_VIOLATION: return FailureKind::EngineDefect;
    case FailureCode::LEGALITY_EXECUTION_MISMATCH: return FailureKind::EngineDefect;
    case FailureCode::MISSING_DISPATCH_HANDLER: return FailureKind::EngineDefect;
    case FailureCode::NUMERIC_RANGE_VIOLATION: return FailureKind::EngineDefect;
    case FailureCode::QUIESCENCE_VIOLATED: return FailureKind::EngineDefect;
    case FailureCode::RESOURCE_EXHAUSTED: return FailureKind::EngineDefect;
    case FailureCode::UNEXPECTED_EXCEPTION: return FailureKind::EngineDefect;
    case FailureCode::UNKNOWN_EXCEPTION: return FailureKind::EngineDefect;
    case FailureCode::COLOSSAL_CAPACITY_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::COLOSSAL_TRANSFORM_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::CONTROL_CHANGE_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::DAMAGE_OUTCOME_TARGET_UNRESOLVED: return FailureKind::RuleUnresolved;
    case FailureCode::DAMAGE_REACTION_ORDER_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::DAMAGE_SOURCE_BOUNDARY_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::DARK_GIFT_ASSIGNMENT_UNRESOLVED: return FailureKind::RuleUnresolved;
    case FailureCode::DARK_GIFT_STACKING_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::DISCOVER_POOL_INCOMPLETE: return FailureKind::RuleUnresolved;
    case FailureCode::EOT_SOURCE_BOUNDARY_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::GENERATION_HAND_FULL_ORDER_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::HEAL_MORTALLY_WOUNDED_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::INSTANCE_COPY_SOURCE_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::MODIFIER_LIFETIME_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::OVERLOAD_CAPACITY_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::POOL_EMPTY_SEMANTICS_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::POOL_IDENTITY_NOT_LOADED: return FailureKind::RuleUnresolved;
    case FailureCode::POOL_MEMBERSHIP_CANDIDATE_ONLY: return FailureKind::RuleUnresolved;
    case FailureCode::RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH: return FailureKind::RuleUnresolved;
    case FailureCode::RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::REBORN_ORDERING_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::SHATTER_MODIFIER_INHERITANCE_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::SHATTER_MODIFIER_MERGE_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::TAKES_DAMAGE_BOUNDARY_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::UNSUPPORTED_CARD_BEHAVIOR: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_CARD_ENTERED_HAND: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_CARD_IN_ACTIVE_HAND: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_DARK_GIFT_OUTCOME: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_DISCARD_TRIGGER: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_DISCOVER_OUTCOME: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_GENERATED_CARD: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_GENERATED_CARD_UNDEFINED: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_HERO_CLASS: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_MINION_HISTORY_TYPE: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_RANDOM_SECRET_OUTCOME: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_SECRET_DEPENDENCY: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_SUMMONED_CARD: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_TRANSFORM_OUTCOME: return FailureKind::Unsupported;
    case FailureCode::UNSUPPORTED_VANILLA_SPELL: return FailureKind::Unsupported;
    case FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED: return FailureKind::RuleUnresolved;
    case FailureCode::UNSUPPORTED_HERO_POWER: return FailureKind::Unsupported;
    }
    return FailureKind::EngineDefect; // unknown numeric identity fails closed
}
const char* failure_code_id(FailureCode code) {
    switch(code) {
    case FailureCode::LEGACY_UNTYPED: return "LEGACY_UNTYPED";
    case FailureCode::DAMAGE_DEPTH_BUDGET_EXCEEDED: return "DAMAGE_DEPTH_BUDGET_EXCEEDED";
    case FailureCode::DAMAGE_PACKET_BUDGET_EXCEEDED: return "DAMAGE_PACKET_BUDGET_EXCEEDED";
    case FailureCode::DAMAGE_WORK_BUDGET_EXCEEDED: return "DAMAGE_WORK_BUDGET_EXCEEDED";
    case FailureCode::CATALOG_REFERENCE_MISSING: return "CATALOG_REFERENCE_MISSING";
    case FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION: return "DAMAGE_FRAME_PROTOCOL_VIOLATION";
    case FailureCode::DAMAGE_TARGET_LOST: return "DAMAGE_TARGET_LOST";
    case FailureCode::DECLARATION_CONTRACT_VIOLATION: return "DECLARATION_CONTRACT_VIOLATION";
    case FailureCode::INVALID_DAMAGE_PACKET: return "INVALID_DAMAGE_PACKET";
    case FailureCode::INVARIANT_VIOLATION: return "INVARIANT_VIOLATION";
    case FailureCode::LEGALITY_EXECUTION_MISMATCH: return "LEGALITY_EXECUTION_MISMATCH";
    case FailureCode::MISSING_DISPATCH_HANDLER: return "MISSING_DISPATCH_HANDLER";
    case FailureCode::NUMERIC_RANGE_VIOLATION: return "NUMERIC_RANGE_VIOLATION";
    case FailureCode::QUIESCENCE_VIOLATED: return "QUIESCENCE_VIOLATED";
    case FailureCode::RESOURCE_EXHAUSTED: return "RESOURCE_EXHAUSTED";
    case FailureCode::UNEXPECTED_EXCEPTION: return "UNEXPECTED_EXCEPTION";
    case FailureCode::UNKNOWN_EXCEPTION: return "UNKNOWN_EXCEPTION";
    case FailureCode::COLOSSAL_CAPACITY_UNREVIEWED: return "COLOSSAL_CAPACITY_UNREVIEWED";
    case FailureCode::COLOSSAL_TRANSFORM_UNREVIEWED: return "COLOSSAL_TRANSFORM_UNREVIEWED";
    case FailureCode::CONTROL_CHANGE_UNREVIEWED: return "CONTROL_CHANGE_UNREVIEWED";
    case FailureCode::DAMAGE_OUTCOME_TARGET_UNRESOLVED: return "DAMAGE_OUTCOME_TARGET_UNRESOLVED";
    case FailureCode::DAMAGE_REACTION_ORDER_UNREVIEWED: return "DAMAGE_REACTION_ORDER_UNREVIEWED";
    case FailureCode::DAMAGE_SOURCE_BOUNDARY_UNREVIEWED: return "DAMAGE_SOURCE_BOUNDARY_UNREVIEWED";
    case FailureCode::DARK_GIFT_ASSIGNMENT_UNRESOLVED: return "DARK_GIFT_ASSIGNMENT_UNRESOLVED";
    case FailureCode::DARK_GIFT_STACKING_UNREVIEWED: return "DARK_GIFT_STACKING_UNREVIEWED";
    case FailureCode::DISCOVER_POOL_INCOMPLETE: return "DISCOVER_POOL_INCOMPLETE";
    case FailureCode::EOT_SOURCE_BOUNDARY_UNREVIEWED: return "EOT_SOURCE_BOUNDARY_UNREVIEWED";
    case FailureCode::GENERATION_HAND_FULL_ORDER_UNREVIEWED: return "GENERATION_HAND_FULL_ORDER_UNREVIEWED";
    case FailureCode::HEAL_MORTALLY_WOUNDED_UNREVIEWED: return "HEAL_MORTALLY_WOUNDED_UNREVIEWED";
    case FailureCode::INSTANCE_COPY_SOURCE_UNREVIEWED: return "INSTANCE_COPY_SOURCE_UNREVIEWED";
    case FailureCode::MODIFIER_LIFETIME_UNREVIEWED: return "MODIFIER_LIFETIME_UNREVIEWED";
    case FailureCode::OVERLOAD_CAPACITY_UNREVIEWED: return "OVERLOAD_CAPACITY_UNREVIEWED";
    case FailureCode::POOL_EMPTY_SEMANTICS_UNREVIEWED: return "POOL_EMPTY_SEMANTICS_UNREVIEWED";
    case FailureCode::POOL_IDENTITY_NOT_LOADED: return "POOL_IDENTITY_NOT_LOADED";
    case FailureCode::POOL_MEMBERSHIP_CANDIDATE_ONLY: return "POOL_MEMBERSHIP_CANDIDATE_ONLY";
    case FailureCode::RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH: return "RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH";
    case FailureCode::RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED: return "RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED";
    case FailureCode::REBORN_ORDERING_UNREVIEWED: return "REBORN_ORDERING_UNREVIEWED";
    case FailureCode::SHATTER_MODIFIER_INHERITANCE_UNREVIEWED: return "SHATTER_MODIFIER_INHERITANCE_UNREVIEWED";
    case FailureCode::SHATTER_MODIFIER_MERGE_UNREVIEWED: return "SHATTER_MODIFIER_MERGE_UNREVIEWED";
    case FailureCode::SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED: return "SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED";
    case FailureCode::TAKES_DAMAGE_BOUNDARY_UNREVIEWED: return "TAKES_DAMAGE_BOUNDARY_UNREVIEWED";
    case FailureCode::UNSUPPORTED_CARD_BEHAVIOR: return "UNSUPPORTED_CARD_BEHAVIOR";
    case FailureCode::UNSUPPORTED_CARD_ENTERED_HAND: return "UNSUPPORTED_CARD_ENTERED_HAND";
    case FailureCode::UNSUPPORTED_CARD_IN_ACTIVE_HAND: return "UNSUPPORTED_CARD_IN_ACTIVE_HAND";
    case FailureCode::UNSUPPORTED_DARK_GIFT_OUTCOME: return "UNSUPPORTED_DARK_GIFT_OUTCOME";
    case FailureCode::UNSUPPORTED_DISCARD_TRIGGER: return "UNSUPPORTED_DISCARD_TRIGGER";
    case FailureCode::UNSUPPORTED_DISCOVER_OUTCOME: return "UNSUPPORTED_DISCOVER_OUTCOME";
    case FailureCode::UNSUPPORTED_GENERATED_CARD: return "UNSUPPORTED_GENERATED_CARD";
    case FailureCode::UNSUPPORTED_GENERATED_CARD_UNDEFINED: return "UNSUPPORTED_GENERATED_CARD_UNDEFINED";
    case FailureCode::UNSUPPORTED_HERO_CLASS: return "UNSUPPORTED_HERO_CLASS";
    case FailureCode::UNSUPPORTED_MINION_HISTORY_TYPE: return "UNSUPPORTED_MINION_HISTORY_TYPE";
    case FailureCode::UNSUPPORTED_RANDOM_SECRET_OUTCOME: return "UNSUPPORTED_RANDOM_SECRET_OUTCOME";
    case FailureCode::UNSUPPORTED_SECRET_DEPENDENCY: return "UNSUPPORTED_SECRET_DEPENDENCY";
    case FailureCode::UNSUPPORTED_SUMMONED_CARD: return "UNSUPPORTED_SUMMONED_CARD";
    case FailureCode::UNSUPPORTED_TRANSFORM_OUTCOME: return "UNSUPPORTED_TRANSFORM_OUTCOME";
    case FailureCode::UNSUPPORTED_VANILLA_SPELL: return "UNSUPPORTED_VANILLA_SPELL";
    case FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED: return "HEALING_BONUS_SCOPE_UNREVIEWED";
    case FailureCode::UNSUPPORTED_HERO_POWER: return "UNSUPPORTED_HERO_POWER";
    }
    return "UNKNOWN_FAILURE_CODE";
}
const char* failure_kind_id(FailureKind kind) {
    switch(kind) {
    case FailureKind::Unsupported: return "UNSUPPORTED";
    case FailureKind::RuleUnresolved: return "RULE_UNRESOLVED";
    case FailureKind::BudgetLimit: return "BUDGET_LIMIT";
    case FailureKind::EngineDefect: return "ENGINE_DEFECT";
    }
    return "ENGINE_DEFECT";
}
} // namespace manaengine
