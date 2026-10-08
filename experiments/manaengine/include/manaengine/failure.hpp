#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
namespace manaengine {
// Append-only identities: never renumber an existing entry.
enum class FailureKind : std::uint8_t { Unsupported=1, RuleUnresolved=2, BudgetLimit=3, EngineDefect=4 };
enum class FailureCode : std::uint16_t {
    LEGACY_UNTYPED = 1,
    DAMAGE_DEPTH_BUDGET_EXCEEDED = 2,
    DAMAGE_PACKET_BUDGET_EXCEEDED = 3,
    DAMAGE_WORK_BUDGET_EXCEEDED = 4,
    CATALOG_REFERENCE_MISSING = 5,
    DAMAGE_FRAME_PROTOCOL_VIOLATION = 6,
    DAMAGE_TARGET_LOST = 7,
    DECLARATION_CONTRACT_VIOLATION = 8,
    INVALID_DAMAGE_PACKET = 9,
    INVARIANT_VIOLATION = 10,
    LEGALITY_EXECUTION_MISMATCH = 11,
    MISSING_DISPATCH_HANDLER = 12,
    NUMERIC_RANGE_VIOLATION = 13,
    QUIESCENCE_VIOLATED = 14,
    RESOURCE_EXHAUSTED = 15,
    UNEXPECTED_EXCEPTION = 16,
    UNKNOWN_EXCEPTION = 17,
    COLOSSAL_CAPACITY_UNREVIEWED = 18,
    COLOSSAL_TRANSFORM_UNREVIEWED = 19,
    CONTROL_CHANGE_UNREVIEWED = 20,
    DAMAGE_OUTCOME_TARGET_UNRESOLVED = 21,
    DAMAGE_REACTION_ORDER_UNREVIEWED = 22,
    DAMAGE_SOURCE_BOUNDARY_UNREVIEWED = 23,
    DARK_GIFT_ASSIGNMENT_UNRESOLVED = 24,
    DARK_GIFT_STACKING_UNREVIEWED = 25,
    DISCOVER_POOL_INCOMPLETE = 26,
    EOT_SOURCE_BOUNDARY_UNREVIEWED = 27,
    GENERATION_HAND_FULL_ORDER_UNREVIEWED = 28,
    HEAL_MORTALLY_WOUNDED_UNREVIEWED = 29,
    INSTANCE_COPY_SOURCE_UNREVIEWED = 30,
    MODIFIER_LIFETIME_UNREVIEWED = 31,
    OVERLOAD_CAPACITY_UNREVIEWED = 32,
    POOL_EMPTY_SEMANTICS_UNREVIEWED = 33,
    POOL_IDENTITY_NOT_LOADED = 34,
    POOL_MEMBERSHIP_CANDIDATE_ONLY = 35,
    RANDOM_SECRET_POOL_MEMBERSHIP_MISMATCH = 36,
    RANDOM_SELECTION_PENDING_DEATH_UNREVIEWED = 37,
    REBORN_ORDERING_UNREVIEWED = 38,
    SHATTER_MODIFIER_INHERITANCE_UNREVIEWED = 39,
    SHATTER_MODIFIER_MERGE_UNREVIEWED = 40,
    SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED = 41,
    TAKES_DAMAGE_BOUNDARY_UNREVIEWED = 42,
    UNSUPPORTED_CARD_BEHAVIOR = 43,
    UNSUPPORTED_CARD_ENTERED_HAND = 44,
    UNSUPPORTED_CARD_IN_ACTIVE_HAND = 45,
    UNSUPPORTED_DARK_GIFT_OUTCOME = 46,
    UNSUPPORTED_DISCARD_TRIGGER = 47,
    UNSUPPORTED_DISCOVER_OUTCOME = 48,
    UNSUPPORTED_GENERATED_CARD = 49,
    UNSUPPORTED_GENERATED_CARD_UNDEFINED = 50,
    UNSUPPORTED_HERO_CLASS = 51,
    UNSUPPORTED_MINION_HISTORY_TYPE = 52,
    UNSUPPORTED_RANDOM_SECRET_OUTCOME = 53,
    UNSUPPORTED_SECRET_DEPENDENCY = 54,
    UNSUPPORTED_SUMMONED_CARD = 55,
    UNSUPPORTED_TRANSFORM_OUTCOME = 56,
    UNSUPPORTED_VANILLA_SPELL = 57,
    HEALING_BONUS_SCOPE_UNREVIEWED = 58,
    UNSUPPORTED_HERO_POWER = 59,
};
const char* failure_code_id(FailureCode code);
const char* failure_kind_id(FailureKind kind);
FailureKind failure_kind_of(FailureCode code);
struct FailureRecord {
    FailureCode code;
    std::string detail, context;
    FailureKind kind() const { return failure_kind_of(code); }
    bool operator==(const FailureRecord&) const = default;
};
class UnsupportedSimulationError : public std::runtime_error {
public:
    explicit UnsupportedSimulationError(const std::string& detail)
        : UnsupportedSimulationError(FailureCode::LEGACY_UNTYPED, detail) {}
    UnsupportedSimulationError(FailureCode code, std::string detail, std::string context={})
        : std::runtime_error(detail), record_{code, std::move(detail), std::move(context)} {}
    explicit UnsupportedSimulationError(FailureRecord record)
        : std::runtime_error(record.detail), record_(std::move(record)) {}
    const FailureRecord& record() const noexcept { return record_; }
private:
    FailureRecord record_;
};
// Keep implementation-specific out_of_range text while typing the audited caller.
template<class Container> decltype(auto) checked_at(Container& values, std::size_t index, FailureCode code) {
    try { return values.at(index); }
    catch(const std::out_of_range& e) { throw UnsupportedSimulationError(code, e.what()); }
}
} // namespace manaengine
