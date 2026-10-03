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
enum class EffectKind { Damage, Draw, GainArmor, ModifyHeroAttack };
enum class TargetSelector { ExplicitCharacter, ExplicitMinion, EnemyMinions, AllCharacters, Self };
struct EffectStep { EffectKind kind=EffectKind::Damage; TargetSelector target=TargetSelector::ExplicitCharacter; int amount=0; };
class UnsupportedSimulationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
struct CardDefinition {
    std::string card_id, name, card_type="UNKNOWN_TYPE", card_class="UNKNOWN_CLASS", race;
    std::string ability="NONE", generated_card, support_state="UNSUPPORTED";
    std::vector<EffectStep> effects;
    int cost=0, attack=0, health=0, durability=0, damage=0, pool_max_cost=0, pool_count=0, duration=0;
    bool rush=false, taunt=false;
};
class CardCatalog {
public:
    explicit CardCatalog(std::vector<CardDefinition> definitions);
private:
    std::shared_ptr<const std::unordered_map<std::string,CardDefinition>> definitions_;
    friend class GameSession;
};
enum class ActionType { PlayCard, Attack, HeroPower, EndTurn, ChooseCard };
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
    bool execution_equal(const Action& other) const {
        return type==other.type && hand_index==other.hand_index &&
               attacker_entity_id==other.attacker_entity_id &&
               target_entity_id==other.target_entity_id && choice_index==other.choice_index;
    }
};
struct ObservedCard {
    std::string card_id, card_type, card_class, race;
    int cost=0, current_cost=0, attack=0, health=0, durability=0, current_durability=0;
    int current_attack=0, current_health=0, board_position=0, entity_id=-1;
    bool can_attack=false, rush=false, frozen=false, taunt=false, divine_shield=false;
    bool stealth=false, silenced=false, immune=false;
    int max_health=0;
};
struct ObservedPlayer {
    std::string player_class;
    int hero_health=30, armor=0, hero_attack=0, max_mana=0, available_mana=0;
    int deck_size=0, hand_size=0, fatigue=0;
    bool hero_power_ready=false, hero_frozen=false;
    std::optional<ObservedCard> hero_power;
    std::optional<ObservedCard> weapon;
    std::vector<ObservedCard> board;
};
struct Observation {
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
private:
    enum class Ability { None, CoinMana, TargetDamage, MinionDamageGenerate, RandomMissiles, DestroyEnemyWeapon,
      FreezeDamage, LifestealDamage, Backstab,
      NextSpellDiscount, NextDemonDiscount, HeroAttackDraw, EndTurnEnemyAreaDamage,
      EndTurnEnemyHeroDamage, ReinforcementAura, RecruiterSummonRush,
      EffectComposition, DeathrattleGenerate, RuntimeChoiceFixture };
    enum class TriggerKind { Battlecry, AfterHeroAttack, EndTurn, Deathrattle };
    enum class ContinuationKind { BuffSelectedMinion };
    enum class Zone { Deck, Hand, Board, Weapon, Graveyard };
    struct CardInstance {
      int entity_id=-1, owner=0, controller=0, zone_position=-1, cost_delta=0;
      Zone zone=Zone::Deck;
      std::string card_id, provenance="DECK";
      int attack=0,health=0,max_health=0,durability=0,current_durability=0,freeze_expire_owner_turn=0;
      bool can_attack=false,rush=false,rush_only=false,frozen=false,taunt=false,divine_shield=false;
      bool stealth=false,silenced=false,immune=false,has_attacked_this_turn=false;
      std::vector<std::string> enchantments;
      std::unordered_map<std::string,int> counters;
    };
    using HandCard=CardInstance;
    using MinionState=CardInstance;
    using WeaponState=CardInstance;
    struct TimedEffect { std::string card_id; int turns_remaining=0,max_cost=0,count=0; };
    struct PlayerState { std::string player_class="UNKNOWN_CLASS"; int hero_health=30,armor=0,hero_attack=0,hero_temp_attack=0;
      int max_mana=0,mana=0,fatigue=0,spell_discount=0,demon_discount=0,turns_started=0;
      bool hero_attacked=false,hero_power_used_this_turn=false,hero_frozen=false; int hero_freeze_expire_turn=0;
      std::vector<CardInstance> deck; std::vector<CardInstance> hand; std::vector<CardInstance> board;
      std::vector<CardInstance> graveyard;
      std::optional<WeaponState> weapon; std::vector<TimedEffect> timed_effects; };
    struct Trigger { TriggerKind kind; int owner; int entity_id=-1; std::string card_id; };
    struct PendingChoice { int owner=0; std::vector<int> options; ContinuationKind continuation=ContinuationKind::BuffSelectedMinion; };
    struct EngineState { int active=0,turn_number=1,next_entity_id=100; std::array<PlayerState,2> players;
      std::deque<Trigger> triggers,deathrattles; std::optional<PendingChoice> pending_choice;
      std::mt19937_64 rng; std::optional<std::string> result,unsupported; };
    std::shared_ptr<const CardCatalog> catalog_;
    EngineState state_; std::uint64_t seed_=0;
    static Ability ability_of(const CardDefinition& card);
    const CardDefinition& card(const std::string& id) const;
    int effective_cost(int owner,const HandCard& item) const;
    std::vector<int> legal_targets(const CardDefinition& def,int owner) const;
    void draw(int owner,int count=1); void damage_character(int target_id,int amount); void damage_minion(int entity_id,int amount);
    void resolve_play(int hand_index,int target_id); void resolve_spell(const CardDefinition& def,int owner,int target_id);
    void resolve_effects(const CardDefinition& def,int owner,int target_id);
    void resolve_trigger(const Trigger& trigger); void stabilize(); void summon_from_deck(int owner,int max_cost,int count,bool grant_rush);
    int random_index(std::size_t count); void update_result();
    std::uint64_t next_u64(); std::size_t bounded_random(std::size_t bound);
    void stable_shuffle(std::vector<CardInstance>& cards);
    CardInstance make_instance(const std::string& card_id,int owner,Zone zone,std::string provenance);
    void update_zone_positions(int owner,Zone zone);
    void move_to_graveyard(int owner,CardInstance instance);
    void freeze_character(int target_id);
    void recompute_hero_attack(int owner);
    static int hero_entity_id(int owner); static int owner_from_hero_id(int entity_id);
    friend struct TestAccess;
};
} // namespace manaengine
