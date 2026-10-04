#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <memory>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
namespace manaengine {
enum class DamageKind { Combat, Spell, Effect, HeroPower, Fatigue };
enum class DamageAttribution { None, DirectSpell, ExternalSpellEffect };
enum class EffectKind { Damage, Draw, GainArmor, ModifyHeroAttack, Freeze, SummonFixed, DestroyMinion, Heal, HealMinionToFull, BuffFriendlyMinions, DiscardRandomSpell };
enum class TargetSelector { ExplicitCharacter, ExplicitEnemyCharacter, ExplicitMinion, ExplicitDamagedEnemyMinion, ExplicitFriendlyMinion, EnemyMinions, EnemyCharacters, AllCharacters, AllMinions, SelfHero, Self, RandomEnemyMinion };
enum class DeckDrawFilter { Any, Spell, FireSpell };
enum class DamageOutcomeCondition { None, MortallyWounded, Survives, Always };
enum class DamageOutcomeFollowup { None, DrawSelf, HealEnemyHero, DrawTargetOwner };
enum class SummonCondition { None, HoldingDragon };
enum class DiscardSpellSchool { None, Nature, Fire };
struct EffectStep { EffectKind kind=EffectKind::Damage; TargetSelector target=TargetSelector::ExplicitCharacter; int amount=0; bool lifesteal=false; std::string summon_card; SummonCondition summon_condition=SummonCondition::None; int conditional_extra_count=0; DiscardSpellSchool discard_school=DiscardSpellSchool::None; bool requires_previous_discard=false; };
class UnsupportedSimulationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
struct CardDefinition {
    std::string card_id, name, card_type="UNKNOWN_TYPE", card_class="UNKNOWN_CLASS", race, spell_school;
    std::string ability="NONE", generated_card, transform_card, support_state="UNSUPPORTED";
    std::string choice_pool, secret_trigger="NONE", secret_effect="NONE";
    std::string shatter_left_card, shatter_right_card;
    std::vector<EffectStep> effects;
    std::vector<std::string> minion_types;
    std::string kindred_copy_contract="NONE";
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
    bool rush=false, taunt=false, lifesteal=false, collectible=false, battlecry=false;
    bool prepare=false, secret=false;
};
class CardCatalog {
public:
    explicit CardCatalog(std::vector<CardDefinition> definitions);
private:
    std::shared_ptr<const std::unordered_map<std::string,CardDefinition>> definitions_;
    friend class GameSession;
};
enum class ActionType { PlayCard, Attack, HeroPower, EndTurn, ChooseCard, PrepareCard };
struct Action {
    ActionType type=ActionType::EndTurn;
    int hand_index=-1, attacker_entity_id=-1, target_entity_id=-1, choice_index=-1;
    // Semantic fields cross the policy boundary; entity IDs remain execution handles.
    std::string card_id, card_type, source_card_id, target_card_id, choice_card_id;
    int card_cost=-1, card_attack=-1, card_health=-1, card_durability=-1;
    bool source_is_hero=false, target_is_hero=false, target_is_self=false, target_taunt=false;
    int source_attack=-1, source_health=-1, source_board_position=-1;
    int target_attack=-1, target_health=-1, target_board_position=-1;
    int choice_card_cost=-1, choice_card_attack=-1, choice_card_health=-1;
    std::string choice_card_type;
    std::string shatter_fragment, shatter_original_card_id;
    int shatter_partner_hand_position=-1;
    bool execution_equal(const Action& other) const {
        return type==other.type && hand_index==other.hand_index &&
               attacker_entity_id==other.attacker_entity_id &&
               target_entity_id==other.target_entity_id && choice_index==other.choice_index;
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
    bool stealth=false, silenced=false, immune=false;
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
    std::optional<std::string> result() const;
    bool needs_choice() const;
    std::vector<int> choice_options() const;
    std::unique_ptr<GameSession> clone() const;
    void begin_prototype_choice(int max_attack=2);
    std::uint64_t seed() const;
    void set_trace_enabled(bool enabled);
    const std::vector<std::string>& diagnostic_trace() const;
private:
    static constexpr int damage_boundary_contract_version=1;
    enum class DamageEvaluationContract { CurrentAtStep, MissileTotal };
    struct SpellEffectContext {
      int owner=0, source_entity=-1, persistent_bonus=0;
      DamageEvaluationContract contract=DamageEvaluationContract::CurrentAtStep;
    };
    enum class Ability { None, CoinMana, TargetDamage, MinionDamageGenerate, RandomMissiles, Discover, DestroyEnemyWeapon,
      FreezeDamage, LifestealDamage, Backstab,
      NextSpellDiscount, NextDemonDiscount, HeroAttackDraw, EndTurnEnemyAreaDamage,
      EndTurnEnemyHeroDamage, ReinforcementAura, RecruiterSummonRush, CastRandomSecrets, SpellDamageAura, DeathrattleDraw,
      EffectComposition, DeathrattleGenerate, RuntimeChoiceFixture, HeldSpellCostReduction, SpellDamageGainsAttack, SpellDamageHandDeck };
    enum class EventWindow { OpponentCastsSpell, FriendlyMinionAttacked, FriendlyHeroAttacked, EnemyMinionAttacks, OpponentPlaysMinion, OpponentTurnEnds };
    enum class SecretEffect { Counterspell, IceBarrier, OasisAlly, MysticMisdirection, ExplosiveRunes, FlamesOfInfinity, EnemyAreaDamage };
    enum class TriggerKind { Battlecry, AfterHeroAttack, EndTurn, Deathrattle, SecretWindow };
    enum class ContinuationKind { BuffSelectedMinion, AddSelectedCardToHand };
    enum class Zone { Deck, Hand, Board, Weapon, Secret, Graveyard };
    enum class ShatterFragment { None, Left, Right, Solo };
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
      bool stealth=false,silenced=false,immune=false,has_attacked_this_turn=false;
      int prepare_locked_turn=-1;
      std::uint64_t activation_sequence=0;
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
    struct PendingChoice { int owner=0; std::vector<int> options; std::vector<std::string> card_options; int choice_cost_delta=0; ContinuationKind continuation=ContinuationKind::BuffSelectedMinion; };
    struct EngineState { int active=0,turn_number=1,next_entity_id=100; std::uint64_t next_event_sequence=1; std::array<PlayerState,2> players;
      std::deque<Trigger> triggers,deathrattles; std::optional<PendingChoice> pending_choice;
      bool trace_enabled=false; std::vector<std::string> trace;
      std::mt19937_64 rng; std::optional<std::string> result,unsupported; };
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
    void summon_fixed(int owner,const std::string& card_id,int count);
    void validate_instance_copy_v1(const CardInstance& source,int owner,Zone expected);
    void summon_instance_copy_v1(int owner,int source_entity);
    bool kindred_qualified(int owner,const CardDefinition& definition) const;
    void record_minion_play(int owner,const CardDefinition& definition);
    void transform_board(int owner,int entity,const std::string& card_id);
    void resolve_play(int hand_index,int target_id); void resolve_spell(const CardDefinition& def,int owner,int target_id,int card_spell_damage=0,int source_entity=-1);
    int evaluate_spell_damage(const SpellEffectContext& context,int base_amount);
    void record_spell_damage_event(int owner,int amount);
    bool resolve_secret_window(EventWindow window,int event_owner,int subject_entity_id=-1);
    bool resolve_secret_instance(int secret_owner,int entity_id,EventWindow window,int subject_entity_id=-1);
    bool resolve_attack_secret_windows(int attacker_owner,int attacker_entity_id,bool hero_attack,int target_entity_id);
    void activate_secret(CardInstance secret);
    void assign_activation_sequence(CardInstance& source);
    void resolve_end_turn_reactions(int owner);
    int resolve_effects(const CardDefinition& def,const SpellEffectContext& context,int target_id);
    void begin_discover(int owner,const CardDefinition& source);
    void update_held_card_spell_progress(int owner);
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
