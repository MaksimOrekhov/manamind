#pragma once
#include "manaengine/failure.hpp"
#include <array>
#include <cstdint>
#include <deque>
#include <memory>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
namespace manaengine {
enum class DamageKind { Combat, Spell, Effect, HeroPower, Fatigue };
enum class DamageAttribution { None, DirectSpell, ExternalSpellEffect };
enum class EffectKind { Damage, Draw, GainArmor, ModifyHeroAttack, Freeze, SummonFixed, DestroyMinion, Heal, HealMinionToFull, BuffFriendlyMinions, DiscardRandomSpell, BuffMinion, ModifyWeaponAttack };
// Append-only: numeric identities are stable. The RandomDistinct* selectors sample min(random_count,n) enemies without
// replacement (see EffectStep::random_count); the selector alone decides whether the enemy hero is a candidate.
enum class TargetSelector { ExplicitCharacter, ExplicitEnemyCharacter, ExplicitMinion, ExplicitDamagedEnemyMinion, ExplicitFriendlyMinion, EnemyMinions, EnemyCharacters, AllCharacters, AllMinions, SelfHero, Self, RandomEnemyMinion, ExplicitDamagedMinion, FriendlyWeapon, RandomDistinctEnemyCharacters, RandomDistinctEnemyMinions };
enum class DeckDrawFilter { Any, Spell, FireSpell };
enum class DamageOutcomeCondition { None, MortallyWounded, Survives, Always };
enum class DamageOutcomeFollowup { None, DrawSelf, HealEnemyHero, DrawTargetOwner };
enum class SummonCondition { None, HoldingDragon };
enum class DiscardSpellSchool { None, Nature, Fire };
enum class PoolPredicateKind { StandardSpellSchool, StandardSpellBaseCost };
enum class PoolClassPolicy { AnyClass, NonNeutralClass };
enum class PoolMembershipStatus { Candidate, MembershipReviewed, ReviewedInferred };
enum class PoolDependencyStatus { Open, DependencyClosed };
enum class PoolExclusionStatus { ReviewedExcluded, Unresolved };
enum class PoolExclusionKind { Quest, Rune, NonGeneratable, ClassPolicy, NeutralPolicy, EventPolicy, Alias, Ban, Other };
enum class DarkGiftRuntimeMembershipStatus { Unresolved };
enum class DarkGiftSamplerStatus { Unverified };
// ArcaneBarrageTargetingContractUnverified covers only enemy-hero pool membership, distinct sampling and
// insufficient-candidate semantics (k=min(2,n), n=0 included). It does not cover Arcane Barrage topology.
enum class EvidenceConstraint { DarkGiftSamplerUnverified, DarkGiftRuntimeMembershipUnresolved, RebornMultiDeathSlotUnverified, MortalQueuedEotSourceUnverified, ArcaneBarrageTargetingContractUnverified, FirePoolMembershipInferred };
const char* evidence_constraint_id(EvidenceConstraint constraint);
struct PoolPredicate { PoolPredicateKind kind=PoolPredicateKind::StandardSpellSchool; std::string school; int base_cost=-1; PoolClassPolicy class_policy=PoolClassPolicy::AnyClass; };
struct PoolExclusion { PoolExclusionKind category=PoolExclusionKind::Other; PoolExclusionStatus status=PoolExclusionStatus::Unresolved; std::vector<std::string> card_ids; std::string rationale, evidence_ref; };
struct PoolManifest {
    std::string pool_id, format_profile_id, as_of_date, metadata_snapshot_id, metadata_snapshot_sha256;
    int schema_version=1, contract_version=1, count=0;
    PoolPredicate predicate;
    std::vector<std::string> card_ids;
    std::string sorted_membership_sha256, predicate_rules_fingerprint;
    PoolMembershipStatus membership_status=PoolMembershipStatus::Candidate;
    PoolDependencyStatus dependency_status=PoolDependencyStatus::Open;
    bool training_eligible=false;
    std::vector<PoolExclusion> exclusions;
};
struct DarkGiftOptionManifest {
    std::string manifest_id, source_metadata_id, source_metadata_sha256;
    int schema_version=1, contract_version=1;
    std::vector<std::string> candidate_option_ids, launch_reviewed_option_ids;
    std::string candidate_membership_sha256, launch_reviewed_membership_sha256;
    DarkGiftRuntimeMembershipStatus runtime_membership_status=DarkGiftRuntimeMembershipStatus::Unresolved;
    DarkGiftSamplerStatus sampler_status=DarkGiftSamplerStatus::Unverified;
    bool training_eligible=false;
};
struct GeneratedInstanceModifiers { int additive_cost_delta=0; };
std::string pool_membership_sha256(const std::vector<std::string>& card_ids);
std::string pool_predicate_rules_fingerprint(const PoolManifest& manifest);
void validate_pool_manifest(const PoolManifest& manifest);
void validate_dark_gift_option_manifest(const DarkGiftOptionManifest& manifest);
// Random-distinct Damage fields (valid only with a RandomDistinct* selector): random_count in 1..3 targets sampled
// without replacement; exclude_previous_target removes the card's explicit target (bound by an earlier explicit Damage
// step) from the candidates; evidence_constraint is the reviewed debt recorded whenever the instruction executes.
struct EffectStep { EffectKind kind=EffectKind::Damage; TargetSelector target=TargetSelector::ExplicitCharacter; int amount=0; bool lifesteal=false; std::string summon_card; SummonCondition summon_condition=SummonCondition::None; int conditional_extra_count=0; DiscardSpellSchool discard_school=DiscardSpellSchool::None; bool requires_previous_discard=false; int random_count=0; bool exclude_previous_target=false; std::optional<EvidenceConstraint> evidence_constraint; };
struct CardDefinition {
    std::string card_id, name, card_type="UNKNOWN_TYPE", card_class="UNKNOWN_CLASS", race, spell_school;
    std::string ability="NONE", generated_card, transform_card, support_state="UNSUPPORTED";
    std::string choice_pool, secret_trigger="NONE", secret_effect="NONE";
    std::string shatter_left_card, shatter_right_card;
    std::vector<EffectStep> effects;
    std::vector<EffectStep> choose_one_a, choose_one_b;
    std::vector<std::string> minion_types;
    // Spatial left-to-right appendage identity for the intrinsic Colossal hook.
    std::vector<std::string> colossal_appendages;
    std::string kindred_copy_contract="NONE";
    std::string takes_damage_pool_id;
    int takes_damage_cost_delta=0;
    std::vector<std::string> required_mechanics;
    std::vector<std::string> reviewed_random_secret_pool;
    bool rules_contract_reviewed=false;
    int cost=0, attack=0, health=0, durability=0, damage=0, pool_max_cost=0, pool_count=0, duration=0;
    int spell_cost_reduction_per_cast=0, held_spell_threshold=0, choice_count=0, choice_cost_delta=0, random_cast_count=0;
    int spell_damage=0, damaged_spell_damage=0, deathrattle_draw_count=0, spell_damage_attack=0, spell_damage_grant=0;
    int spell_damage_cost_reduction=0;
    DeckDrawFilter deck_draw_filter=DeckDrawFilter::Any;
    DamageOutcomeCondition damage_outcome_condition=DamageOutcomeCondition::None;
    DamageOutcomeFollowup damage_outcome_followup=DamageOutcomeFollowup::None;
    int damage_outcome_amount=0, overload=0;
    std::string dark_gift_option_pool_id;
    int dark_gift_attack=0, dark_gift_health=0, dark_gift_cost=0;
    std::vector<std::string> dark_gift_keywords;
    bool dark_gift_requires_battlecry=false, dark_gift_requires_positive_attack=false;
    bool rush=false, taunt=false, lifesteal=false, collectible=false, battlecry=false;
    bool reborn=false; // Reviewed intrinsic keyword, not a granted restoration variant.
    bool prepare=false, secret=false;
    bool requires_friendly_weapon=false;
};
class CardCatalog {
public:
    explicit CardCatalog(std::vector<CardDefinition> definitions,
                         std::vector<PoolManifest> pools={},
                         std::string metadata_snapshot_id={},
                         std::string metadata_snapshot_sha256={},
                         std::vector<DarkGiftOptionManifest> dark_gift_manifests={});
private:
    std::shared_ptr<const std::unordered_map<std::string,CardDefinition>> definitions_;
    std::shared_ptr<const std::unordered_map<std::string,PoolManifest>> pools_;
    std::shared_ptr<const std::unordered_map<std::string,DarkGiftOptionManifest>> dark_gift_manifests_;
    friend class GameSession;
    friend struct TestAccess;
};
enum class ActionType { PlayCard, Attack, HeroPower, EndTurn, ChooseCard, PrepareCard };
struct Action {
    ActionType type=ActionType::EndTurn;
    int hand_index=-1, attacker_entity_id=-1, target_entity_id=-1, choice_index=-1, choose_one=0;
    // Semantic fields cross the policy boundary; entity IDs remain execution handles.
    std::string card_id, card_type, source_card_id, target_card_id, choice_card_id;
    int card_cost=-1, card_attack=-1, card_health=-1, card_durability=-1;
    bool source_is_hero=false, target_is_hero=false, target_is_self=false, target_taunt=false;
    int source_attack=-1, source_health=-1, source_board_position=-1;
    int target_attack=-1, target_health=-1, target_board_position=-1;
    int choice_card_cost=-1, choice_card_attack=-1, choice_card_health=-1;
    std::string choice_card_type;
    std::string shatter_fragment, shatter_original_card_id, choice_dark_gift;
    std::vector<std::string> card_dark_gifts;
    int shatter_partner_hand_position=-1;
    bool execution_equal(const Action& other) const {
        return type==other.type && hand_index==other.hand_index &&
               attacker_entity_id==other.attacker_entity_id &&
               target_entity_id==other.target_entity_id && choice_index==other.choice_index && choose_one==other.choose_one;
    }
};
struct ObservedCard {
    int held_spell_progress=0, trigger_remaining=-1, effect_turns_remaining=0, freeze_turns_remaining=0;
    bool prepare_used=false;
    std::string card_id, card_type, card_class, race;
    std::string shatter_fragment, shatter_original_card_id;
    int shatter_partner_hand_position=-1;
    bool prepare_locked=false;
    int cost=0, current_cost=0, attack=0, health=0, durability=0, current_durability=0, current_spell_damage=0;
    int current_attack=0, current_health=0, board_position=0, entity_id=-1;
    bool can_attack=false, rush=false, frozen=false, taunt=false, divine_shield=false, lifesteal=false;
    bool stealth=false, silenced=false, immune=false, charge=false, reborn=false;
    std::vector<std::string> dark_gifts;
    int max_health=0;
};
struct ObservedPlayer {
    std::vector<std::string> current_turn_minion_types_played, previous_turn_minion_types_played;
    int spells_cast_this_turn=0, spell_discount=0, demon_discount=0, hero_freeze_turns_remaining=0;
    std::vector<ObservedCard> active_effects;
    std::string player_class;
    int hero_health=30, armor=0, hero_attack=0, max_mana=0, available_mana=0, overloaded_mana=0, pending_overload=0;
    int deck_size=0, hand_size=0, fatigue=0, secret_count=0, spell_damage=0;
    std::vector<std::string> known_secrets;
    bool hero_power_ready=false, hero_frozen=false;
    std::optional<ObservedCard> hero_power;
    std::optional<ObservedCard> weapon;
    std::vector<ObservedCard> board;
};
struct Observation {
    std::string pending_choice_owner;
    std::vector<ObservedCard> pending_choice_options;
    int turn_number=1;
    std::string active_player="SELF";
    ObservedPlayer self_player, opponent;
    std::vector<ObservedCard> self_hand;
    int self_hand_known_count=0;
};
class GameSession {
public:
    GameSession(GameSession&&)=default;
    GameSession(std::vector<std::string> player1_deck, std::vector<std::string> player2_deck,
                std::vector<CardDefinition> definitions, std::uint64_t seed=0, bool shuffle=true,
                std::string player1_class="UNKNOWN_CLASS", std::string player2_class="UNKNOWN_CLASS");
    GameSession(std::vector<std::string> player1_deck, std::vector<std::string> player2_deck,
                std::shared_ptr<CardCatalog> catalog, std::uint64_t seed=0, bool shuffle=true,
                std::string player1_class="UNKNOWN_CLASS", std::string player2_class="UNKNOWN_CLASS");
    Observation observation(int perspective=0) const;
    std::vector<Action> legal_actions() const;
    std::vector<Action> semantic_legal_actions() const;
    void apply_action(const Action& action);
    bool is_complete() const;
    void validate_invariants() const;
    bool is_valid() const;
    std::optional<std::string> unsupported_outcome() const;
    const std::set<EvidenceConstraint>& evidence_constraints() const;
    std::optional<std::string> result() const;
    bool needs_choice() const;
    std::vector<int> choice_options() const;
    std::unique_ptr<GameSession> clone() const;
    void begin_prototype_choice(int max_attack=2);
    std::uint64_t seed() const;
    void set_trace_enabled(bool enabled);
    const std::vector<std::string>& diagnostic_trace() const;
private:
    GameSession(const GameSession&)=default; // Public clone enforces quiescence.
    static constexpr int damage_boundary_contract_version=1;
    enum class DamageEvaluationContract { CurrentAtStep, MissileTotal };
    struct SpellEffectContext {
      int owner=0, source_entity=-1, persistent_bonus=0;
      DamageEvaluationContract contract=DamageEvaluationContract::CurrentAtStep;
    };
    enum class Ability { None, CoinMana, TargetDamage, MinionDamageGenerate, RandomMissiles, Discover, DestroyEnemyWeapon,
      FreezeDamage, LifestealDamage, Backstab,
      NextSpellDiscount, NextDemonDiscount, HeroAttackDraw, EndTurnEnemyAreaDamage,
      EndTurnOtherMinionsDamage,
      EndTurnEnemyHeroDamage, ReinforcementAura, RecruiterSummonRush, CastRandomSecrets, SpellDamageAura, DeathrattleDraw,
      EffectComposition, DeathrattleGenerate, RuntimeChoiceFixture, HeldSpellCostReduction, SpellDamageGainsAttack, SpellDamageHandDeck, DarkGiftOption, TakesDamageGenerate };
    enum class EventWindow { OpponentCastsSpell, FriendlyMinionAttacked, FriendlyHeroAttacked, EnemyMinionAttacks, OpponentPlaysMinion, OpponentTurnEnds };
    enum class SecretEffect { Counterspell, IceBarrier, OasisAlly, MysticMisdirection, ExplosiveRunes, FlamesOfInfinity, EnemyAreaDamage };
    enum class TriggerKind { Battlecry, AfterHeroAttack, EndTurn, Deathrattle, SecretWindow };
    enum class ContinuationKind { BuffSelectedMinion, AddSelectedCardToHand, SelectChooseOneMode, ResolveChooseOneTarget };
    enum class Zone { Deck, Hand, Board, Weapon, Secret, Graveyard };
    enum class ShatterFragment { None, Left, Right, Solo };
    struct PersistentModifier { std::string source_card_id; int attack_delta=0, health_delta=0, cost_delta=0; bool taunt=false, lifesteal=false, charge=false; };
    struct CardInstance {
      int entity_id=-1, owner=0, controller=0, zone_position=-1, cost_delta=0, spell_damage_bonus=0;
      Zone zone=Zone::Deck;
      std::string card_id, provenance="DECK";
      std::string shatter_original_card_id;
      int shatter_partner_entity_id=-1;
      ShatterFragment shatter_fragment=ShatterFragment::None;
      bool shatter_consumed=false;
      int attack=0,health=0,max_health=0,durability=0,current_durability=0,freeze_expire_owner_turn=0;
      bool can_attack=false,rush=false,rush_only=false,frozen=false,taunt=false,divine_shield=false,lifesteal=false;
      bool stealth=false,silenced=false,immune=false,has_attacked_this_turn=false,charge=false;
      bool reborn=false; // Active and unconsumed on this entity.
      int prepare_locked_turn=-1;
      std::uint64_t activation_sequence=0;
      std::vector<PersistentModifier> persistent_modifiers;
      std::vector<std::string> enchantments;
      std::unordered_map<std::string,int> counters;
    };
    using HandCard=CardInstance;
    using MinionState=CardInstance;
    using WeaponState=CardInstance;
    struct TimedEffect { std::string card_id; int turns_remaining=0,max_cost=0,count=0; std::uint64_t activation_sequence=0; };
    struct PlayerState { std::string player_class="UNKNOWN_CLASS"; int hero_health=30,armor=0,hero_attack=0,hero_temp_attack=0;
      std::vector<std::string> current_turn_minion_types_played,previous_turn_minion_types_played;
      int max_mana=0,mana=0,fatigue=0,spell_discount=0,demon_discount=0,turns_started=0,spells_cast_this_turn=0,overloaded_mana=0,pending_overload=0;
      std::int64_t spell_damage_dealt_this_turn=0;
      bool hero_attacked=false,hero_power_used_this_turn=false,hero_frozen=false; int hero_freeze_expire_turn=0;
      std::vector<CardInstance> deck; std::vector<CardInstance> hand; std::vector<CardInstance> board;
      std::vector<CardInstance> graveyard; std::vector<CardInstance> secrets;
      std::optional<WeaponState> weapon; std::vector<TimedEffect> timed_effects; };
    struct Trigger { TriggerKind kind; int owner; int entity_id=-1; std::string card_id; int target_entity_id=-1; EventWindow window=EventWindow::OpponentCastsSpell; };
    struct PendingChoice { int owner=0; std::vector<int> options; std::vector<std::string> card_options, card_dark_gifts; int choice_cost_delta=0; ContinuationKind continuation=ContinuationKind::BuffSelectedMinion; EffectStep selected_effect; std::string source_card_id; int source_entity=-1, persistent_bonus=0, selected_mode=0; };
    enum class DamageDispatch { ApplyAllThenReact, SinglePacketThenReact };
    enum class DamageEventOrder { MinionEntrySequence, SingleTarget, ScalarOnly };
    enum class DamageFrameStage { Apply, DispatchEvent, DispatchReaction, Complete };
    enum class ReactionKind { SelfTakesDamageV1, FirstSpellDamageAttackV1 };
    enum class Prevention { None, Zero, Immune, DivineShield };
    struct EntityHandle { int entity_id=-1, controller=-1; std::uint64_t entry_sequence=0; std::string card_id; bool silenced=false; };
    struct DamagePacketIntent {
      int source_entity=-1, source_controller=0; EntityHandle target;
      int amount=0; DamageKind kind=DamageKind::Effect;
      DamageAttribution attribution=DamageAttribution::None; bool lifesteal=false;
    };
    struct DamageReactionSnapshot {
      ReactionKind kind=ReactionKind::SelfTakesDamageV1; EntityHandle consumer;
      std::string pool_id; int value=0;
    };
    struct PacketOutcome {
      DamagePacketIntent intent; Prevention prevention=Prevention::None;
      int reported_damage=0; std::int64_t health_delta=0, armor_delta=0;
      std::uint64_t event_sequence=0;
      std::optional<DamageReactionSnapshot> self_reaction;
    };
    struct DamageGroupFrame {
      std::uint64_t group_id=0,parent_group_id=0;
      DamageDispatch dispatch=DamageDispatch::SinglePacketThenReact;
      DamageEventOrder order=DamageEventOrder::SingleTarget;
      DamageFrameStage stage=DamageFrameStage::Apply;
      std::vector<PacketOutcome> outcomes;
      std::vector<DamageReactionSnapshot> current_event_reactions;
      std::vector<EntityHandle> board_sources;
      std::size_t event_cursor=0,reaction_cursor=0;
    };
    struct EngineState { int active=0,turn_number=1,next_entity_id=100; std::uint64_t next_event_sequence=1; std::array<PlayerState,2> players;
      std::deque<Trigger> triggers,deathrattles; std::optional<PendingChoice> pending_choice;
      bool trace_enabled=false; std::vector<std::string> trace;
      std::mt19937_64 rng; std::uint64_t next_damage_sequence=1; std::optional<std::string> result,unsupported;
      std::set<EvidenceConstraint> evidence_constraints;
      std::vector<DamageGroupFrame> damage_frames;
      std::uint64_t next_damage_group_id=1;
      std::size_t damage_work=0; };
    struct DamageOccurrence {
      int damage_source_entity_id=-1, damaged_entity_id=-1, damaged_controller=-1;
      DamageKind damage_kind=DamageKind::Effect; DamageAttribution attribution=DamageAttribution::None;
      int packet_amount=0; std::int64_t actual_health_delta=0;
      std::uint64_t damage_group_id=0, sequence=0, consumer_activation_sequence=0;
      std::string captured_pool_id; int captured_cost_delta=0;
    };
    std::shared_ptr<const CardCatalog> catalog_;
    EngineState state_; std::uint64_t seed_=0;
    static Ability ability_of(const CardDefinition& card);
    static std::optional<EventWindow> secret_window_of(const std::string& trigger);
    static SecretEffect secret_effect_of(const CardDefinition& card);
    const CardDefinition& card(const std::string& id) const;
    int effective_cost(int owner,const HandCard& item) const;
    int spell_damage_for(int owner) const;
    std::vector<int> legal_targets(const CardDefinition& def,int owner) const;
    void draw(int owner,int count=1); void draw_from_deck(int owner,int count,DeckDrawFilter filter);
    int deal_damage(int source,int target,int amount,DamageKind kind,int controller,bool lifesteal=false,DamageAttribution attribution=DamageAttribution::None);
    EntityHandle damage_target_handle(int target);
    DamagePacketIntent damage_intent(int source,int target,int amount,DamageKind kind,int controller,bool lifesteal=false,DamageAttribution attribution=DamageAttribution::None);
    bool has_self_damage_reaction(const DamagePacketIntent& packet) const;
    void guard_scalar_damage(const std::vector<DamagePacketIntent>& packets);
    void guard_area_spell_modifiers(const std::vector<DamagePacketIntent>& packets);
    PacketOutcome apply_damage_packet(const DamagePacketIntent& packet);
    std::size_t open_damage_group(std::vector<DamagePacketIntent> packets,DamageDispatch dispatch,DamageEventOrder order);
    void dispatch_damage_event(std::size_t frame_index);
    int close_damage_group(std::size_t frame_index);
    int run_damage_group(std::vector<DamagePacketIntent> packets,DamageDispatch dispatch,DamageEventOrder order);
    void require_quiescent() const;
    void execute_action(const Action& action);
    void consume_damage_work();
    void validate_damage_frame_sources(std::size_t frame_index);
    void resolve_damage_occurrence(const DamageOccurrence& occurrence);
    void generate_random_card_to_hand(int owner,const std::string& pool_id,GeneratedInstanceModifiers modifiers);
    void summon_fixed(int owner,const std::string& card_id,int count);
    void enter_board_with_appendages(int owner,CardInstance instance,int position);
    void validate_instance_copy_v1(const CardInstance& source,int owner,Zone expected);
    void summon_instance_copy_v1(int owner,int source_entity);
    bool kindred_qualified(int owner,const CardDefinition& definition) const;
    void record_minion_play(int owner,const CardDefinition& definition);
    void transform_board(int owner,int entity,const std::string& card_id);
    void resolve_play(int hand_index,int target_id); void resolve_spell(const CardDefinition& def,int owner,int target_id,int card_spell_damage=0,int source_entity=-1);
    int evaluate_spell_damage(const SpellEffectContext& context,int base_amount);
    bool resolve_secret_window(EventWindow window,int event_owner,int subject_entity_id=-1);
    bool resolve_secret_instance(int secret_owner,int entity_id,EventWindow window,int subject_entity_id=-1);
    bool resolve_attack_secret_windows(int attacker_owner,int attacker_entity_id,bool hero_attack,int target_entity_id);
    void activate_secret(CardInstance secret);
    void assign_activation_sequence(CardInstance& source);
    void resolve_end_turn_reactions(int owner);
    int resolve_effects(const CardDefinition& def,const SpellEffectContext& context,int target_id);
    int resolve_random_distinct_damage(const CardDefinition& def,const SpellEffectContext& context,const EffectStep& step,int previous_target);
    void begin_discover(int owner,const CardDefinition& source);
    [[noreturn]] void reject_unsupported(std::string reason);
    bool dark_gift_eligible(const CardDefinition& minion,const CardDefinition& gift) const;
    void apply_dark_gift(CardInstance& instance,const std::string& gift_id);
    void project_modifiers(CardInstance& instance,const CardDefinition& definition) const;
    void require_supported_modifier_lifecycle();
    static std::vector<std::string> dark_gift_ids(const CardInstance& instance);
    void update_held_card_spell_progress(int owner);
    struct RebornPending { int owner=0; std::string card_id; int dead_entity_id=-1, recorded_slot=0; std::uint64_t play_order=0; };
    void resolve_reborns(std::vector<RebornPending> pending,const std::array<std::vector<std::pair<int,std::string>>,2>& survivor_board);
    void resolve_trigger(const Trigger& trigger); void stabilize(); void summon_from_deck(int owner,int max_cost,int count,bool grant_rush);
    int random_index(std::size_t count); void update_result();
    void trace_event(std::string event);
    std::uint64_t next_u64(); std::size_t bounded_random(std::size_t bound);
    void stable_shuffle(std::vector<CardInstance>& cards);
    CardInstance make_instance(const std::string& card_id,int owner,Zone zone,std::string provenance);
    void enter_hand(int owner,CardInstance instance);
    CardInstance remove_card_from_hand(int owner,std::size_t hand_position);
    void update_shatter_links(int owner);
    void shatter_on_hand_entry(int owner,CardInstance instance);
    void update_zone_positions(int owner,Zone zone);
    void move_to_graveyard(int owner,CardInstance instance);
    void freeze_character(int target_id);
    void recompute_hero_attack(int owner);
    static int hero_entity_id(int owner); static int owner_from_hero_id(int entity_id);
    friend struct TestAccess;
};
} // namespace manaengine
