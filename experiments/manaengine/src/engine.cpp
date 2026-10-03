#include "manaengine/engine.hpp"
#include <algorithm>
#include <stdexcept>
#include <unordered_set>
#include <utility>
namespace manaengine {
namespace { bool is_minion(const CardDefinition& c){return c.card_type=="MINION";} bool is_spell(const CardDefinition& c){return c.card_type=="SPELL";} bool is_weapon(const CardDefinition& c){return c.card_type=="WEAPON";} }
GameSession::Ability GameSession::ability_of(const CardDefinition& c) {
 const auto& v=c.ability;
 if(v=="COIN_MANA")return Ability::CoinMana;
 if(v=="TARGET_DAMAGE")return Ability::TargetDamage;
 if(v=="MINION_DAMAGE_GENERATE")return Ability::MinionDamageGenerate;
 if(v=="RANDOM_MISSILES")return Ability::RandomMissiles;
 if(v=="DESTROY_ENEMY_WEAPON")return Ability::DestroyEnemyWeapon;
 if(v=="FREEZE_DAMAGE")return Ability::FreezeDamage;
 if(v=="LIFESTEAL_DAMAGE")return Ability::LifestealDamage;
 if(v=="BACKSTAB")return Ability::Backstab;
 if(v=="NEXT_SPELL_DISCOUNT")return Ability::NextSpellDiscount;
 if(v=="NEXT_DEMON_DISCOUNT")return Ability::NextDemonDiscount;
 if(v=="HERO_ATTACK_DRAW")return Ability::HeroAttackDraw;
 if(v=="END_TURN_ENEMY_AREA_DAMAGE")return Ability::EndTurnEnemyAreaDamage;
 if(v=="END_TURN_ENEMY_HERO_DAMAGE")return Ability::EndTurnEnemyHeroDamage;
 if(v=="REINFORCEMENT_AURA")return Ability::ReinforcementAura;
 if(v=="RECRUITER_SUMMON_RUSH")return Ability::RecruiterSummonRush;
 if(v=="EFFECT_COMPOSITION")return Ability::EffectComposition;
 if(v=="DEATHRATTLE_GENERATE")return Ability::DeathrattleGenerate;
 if(v=="RUNTIME_CHOICE_FIXTURE")return Ability::RuntimeChoiceFixture;
 if(v=="HELD_SPELL_COST_REDUCTION")return Ability::HeldSpellCostReduction;
 if(v=="NONE"&&c.support_state=="VERIFIED_VANILLA")return Ability::None;
 if(v=="NONE")throw UnsupportedSimulationError("unsupported card effect: "+c.card_id);
 throw std::invalid_argument("unknown ManaEngine ability: "+v+" on "+c.card_id);
}
CardCatalog::CardCatalog(std::vector<CardDefinition> definitions){
 static const std::unordered_set<std::string> abilities={"NONE","COIN_MANA","TARGET_DAMAGE","MINION_DAMAGE_GENERATE","RANDOM_MISSILES","DESTROY_ENEMY_WEAPON","FREEZE_DAMAGE","LIFESTEAL_DAMAGE","BACKSTAB","NEXT_SPELL_DISCOUNT","NEXT_DEMON_DISCOUNT","HERO_ATTACK_DRAW","END_TURN_ENEMY_AREA_DAMAGE","END_TURN_ENEMY_HERO_DAMAGE","REINFORCEMENT_AURA","RECRUITER_SUMMON_RUSH","EFFECT_COMPOSITION","DEATHRATTLE_GENERATE","RUNTIME_CHOICE_FIXTURE","HELD_SPELL_COST_REDUCTION"};
 auto cards=std::make_shared<std::unordered_map<std::string,CardDefinition>>();
 for(auto& d:definitions){if(d.card_id.empty())throw std::invalid_argument("CardDefinition.card_id cannot be empty");if(!abilities.contains(d.ability))throw std::invalid_argument("unknown ManaEngine ability: "+d.ability+" on "+d.card_id);if(d.support_state!="SUPPORTED"&&d.support_state!="VERIFIED_VANILLA"&&d.support_state!="UNSUPPORTED")throw std::invalid_argument("invalid support_state on "+d.card_id);if(d.support_state=="VERIFIED_VANILLA"&&d.ability!="NONE")throw std::invalid_argument("VERIFIED_VANILLA card must use NONE ability: "+d.card_id);if(d.support_state=="SUPPORTED"&&d.ability=="NONE")throw std::invalid_argument("SUPPORTED card must declare an implemented ability: "+d.card_id);if((d.ability=="EFFECT_COMPOSITION")!=(!d.effects.empty()))throw std::invalid_argument("EFFECT_COMPOSITION requires a nonempty effects list, and other abilities must not declare effects: "+d.card_id);if((d.ability=="HELD_SPELL_COST_REDUCTION")!=(d.spell_cost_reduction_per_cast>0))throw std::invalid_argument("HELD_SPELL_COST_REDUCTION requires a positive spell_cost_reduction_per_cast and other abilities must not declare one: "+d.card_id);for(const auto& e:d.effects){if(e.amount<0)throw std::invalid_argument("effect amount cannot be negative: "+d.card_id);if(e.kind==EffectKind::Damage&&(e.target==TargetSelector::Self))throw std::invalid_argument("Damage cannot target Self: "+d.card_id);if(e.kind==EffectKind::Draw&&e.target!=TargetSelector::Self)throw std::invalid_argument("Draw must target Self: "+d.card_id);if(e.kind==EffectKind::GainArmor&&e.target!=TargetSelector::Self)throw std::invalid_argument("GainArmor must target Self: "+d.card_id);if(e.kind==EffectKind::ModifyHeroAttack&&e.target!=TargetSelector::Self)throw std::invalid_argument("ModifyHeroAttack must target Self: "+d.card_id);if(e.kind==EffectKind::Freeze&&(e.target!=TargetSelector::ExplicitCharacter||e.amount!=0))throw std::invalid_argument("Freeze requires an explicit character target and amount zero: "+d.card_id);}if(!cards->emplace(d.card_id,std::move(d)).second)throw std::invalid_argument("duplicate CardDefinition ID");}
 if(!cards->contains("GAME_005")){CardDefinition coin;coin.card_id="GAME_005";coin.name="The Coin";coin.card_type="SPELL";coin.card_class="NEUTRAL";coin.ability="COIN_MANA";coin.support_state="SUPPORTED";cards->emplace(coin.card_id,std::move(coin));}
 definitions_=std::move(cards);
}
GameSession::GameSession(std::vector<std::string> d1,std::vector<std::string> d2,std::vector<CardDefinition> defs,std::uint64_t seed,bool shuffle,std::string class1,std::string class2)
 :GameSession(std::move(d1),std::move(d2),std::make_shared<CardCatalog>(std::move(defs)),seed,shuffle,std::move(class1),std::move(class2)){}
GameSession::GameSession(std::vector<std::string> d1,std::vector<std::string> d2,std::shared_ptr<CardCatalog> catalog,std::uint64_t seed,bool shuffle,std::string class1,std::string class2):catalog_(std::move(catalog)),seed_(seed){
 state_.rng.seed(seed); state_.players[0].player_class=std::move(class1);state_.players[1].player_class=std::move(class2);
 for(int p=0;p<2;++p){auto& deck=p==0?d1:d2;for(const auto& id:deck)state_.players[p].deck.push_back(make_instance(id,p,Zone::Deck,"DECK"));if(shuffle)stable_shuffle(state_.players[p].deck);update_zone_positions(p,Zone::Deck);}
 draw(0,3);draw(1,4);if(state_.players[1].hand.size()<10){auto coin=make_instance("GAME_005",1,Zone::Hand,"GENERATED");state_.players[1].hand.push_back(std::move(coin));update_zone_positions(1,Zone::Hand);}state_.players[0].max_mana=1;state_.players[0].mana=1;draw(0);state_.players[0].turns_started=1;recompute_hero_attack(0);
}
const CardDefinition& GameSession::card(const std::string& id)const{auto i=catalog_->definitions_->find(id);if(i==catalog_->definitions_->end())throw std::out_of_range("Card missing from prototype catalog: "+id);return i->second;}
GameSession::CardInstance GameSession::make_instance(const std::string& id,int owner,Zone zone,std::string provenance){const auto& d=card(id);CardInstance x;x.entity_id=state_.next_entity_id++;x.card_id=id;x.owner=owner;x.controller=owner;x.zone=zone;x.provenance=std::move(provenance);x.attack=d.attack;x.health=d.health;x.max_health=d.health;x.durability=d.durability;x.current_durability=d.durability;x.rush=d.rush;x.taunt=d.taunt;return x;}
void GameSession::update_zone_positions(int owner,Zone zone){auto& p=state_.players[owner];auto set=[&](auto& values){for(std::size_t i=0;i<values.size();++i){values[i].zone=zone;values[i].zone_position=static_cast<int>(i);}};if(zone==Zone::Deck)set(p.deck);else if(zone==Zone::Hand)set(p.hand);else if(zone==Zone::Board)set(p.board);else if(zone==Zone::Graveyard)set(p.graveyard);else if(zone==Zone::Weapon&&p.weapon){p.weapon->zone=zone;p.weapon->zone_position=0;}}
void GameSession::move_to_graveyard(int owner,CardInstance instance){instance.zone=Zone::Graveyard;instance.controller=owner;instance.zone_position=static_cast<int>(state_.players[owner].graveyard.size());state_.players[owner].graveyard.push_back(std::move(instance));}
std::uint64_t GameSession::next_u64(){return state_.rng();}
std::size_t GameSession::bounded_random(std::size_t bound){if(bound==0)throw std::invalid_argument("empty random candidate set");const auto n=static_cast<std::uint64_t>(bound);const auto threshold=(std::uint64_t{0}-n)%n;for(;;){auto value=next_u64();if(value>=threshold)return static_cast<std::size_t>(value%n);}}
void GameSession::stable_shuffle(std::vector<CardInstance>& values){for(std::size_t i=values.size();i>1;--i){auto j=bounded_random(i);std::swap(values[i-1],values[j]);}}
int GameSession::effective_cost(int owner,const HandCard& h)const{const auto& d=card(h.card_id);int c=std::max(0,d.cost+h.cost_delta);if(is_spell(d)&&state_.players[owner].spell_discount>0)c=std::max(0,c-state_.players[owner].spell_discount);if(is_minion(d)&&d.race=="DEMON"&&state_.players[owner].demon_discount>0)c=std::max(0,c-state_.players[owner].demon_discount);return c;}
void GameSession::update_held_card_spell_progress(int owner){for(auto& held:state_.players[owner].hand){const auto& d=card(held.card_id);if(ability_of(d)!=Ability::HeldSpellCostReduction)continue;++held.counters["spells_played_from_hand"];held.cost_delta-=d.spell_cost_reduction_per_cast;}}
int GameSession::hero_entity_id(int owner){return owner+1;} int GameSession::owner_from_hero_id(int id){return id-1;}
std::vector<int> GameSession::legal_targets(const CardDefinition& d,int owner)const{
 auto a=ability_of(d);bool minion_only=a==Ability::MinionDamageGenerate||a==Ability::LifestealDamage||a==Ability::Backstab;
 if(a==Ability::EffectComposition)for(const auto& e:d.effects)if(e.kind==EffectKind::Damage&&e.target==TargetSelector::ExplicitMinion)minion_only=true;
 bool enemy_only=a==Ability::Backstab||a==Ability::LifestealDamage;std::vector<int> out;
 for(int p=0;p<2;++p)for(const auto& m:state_.players[p].board){if(enemy_only&&p==owner)continue;if(a==Ability::Backstab&&m.health!=m.max_health)continue;out.push_back(m.entity_id);}
 if(!minion_only){out.push_back(hero_entity_id(0));out.push_back(hero_entity_id(1));}
 return out;
}
std::vector<Action> GameSession::legal_actions()const{
 if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);
 std::vector<Action> out;if(state_.result)return out;if(state_.pending_choice){for(std::size_t i=0;i<state_.pending_choice->options.size();++i)out.push_back({ActionType::ChooseCard,-1,-1,state_.pending_choice->options[i],static_cast<int>(i)});return out;}
 int p=state_.active;const auto& me=state_.players[p];const auto& foe=state_.players[1-p];out.push_back({ActionType::EndTurn});
 for(std::size_t i=0;i<me.hand.size();++i){const auto& h=me.hand[i];const auto& d=card(h.card_id);if(d.support_state=="UNSUPPORTED")throw UnsupportedSimulationError("unsupported card is available to the active player");if(effective_cost(p,h)>me.mana||(is_minion(d)&&me.board.size()>=7))continue;
 auto a=ability_of(d);bool targeted=a==Ability::TargetDamage||a==Ability::MinionDamageGenerate||a==Ability::FreezeDamage||a==Ability::LifestealDamage||a==Ability::Backstab;if(a==Ability::EffectComposition)targeted=std::any_of(d.effects.begin(),d.effects.end(),[](const auto& e){return (e.kind==EffectKind::Damage&&(e.target==TargetSelector::ExplicitCharacter||e.target==TargetSelector::ExplicitMinion))||(e.kind==EffectKind::Freeze&&e.target==TargetSelector::ExplicitCharacter);});if(targeted){for(int t:legal_targets(d,p))out.push_back({ActionType::PlayCard,static_cast<int>(i),-1,t});}else out.push_back({ActionType::PlayCard,static_cast<int>(i)});
 }
 if(me.player_class=="MAGE"&&!me.hero_power_used_this_turn&&me.mana>=2){CardDefinition power;power.ability="TARGET_DAMAGE";for(int t:legal_targets(power,p))out.push_back({ActionType::HeroPower,-1,-1,t});}
 bool taunt=false;for(const auto& m:foe.board)if(m.taunt&&!m.silenced)taunt=true;
 auto add_attacks=[&](int attacker,bool ready,bool rush_only){if(!ready)return;for(const auto& m:foe.board){if(taunt&&(!m.taunt||m.silenced))continue;out.push_back({ActionType::Attack,-1,attacker,m.entity_id});}if(!taunt&&!rush_only)out.push_back({ActionType::Attack,-1,attacker,hero_entity_id(1-p)});};
 for(const auto& m:me.board)add_attacks(m.entity_id,m.can_attack&&!m.frozen,m.rush_only);
 if(!me.hero_attacked&&!me.hero_frozen&&(me.hero_attack>0||(me.weapon&&me.weapon->durability>0)))add_attacks(hero_entity_id(p),true,false);
 return out;
}
std::vector<Action> GameSession::semantic_legal_actions()const{
 auto actions=legal_actions();
 const int actor=state_.active;
 auto fill_card=[&](Action& a,const CardDefinition& d){a.card_id=d.card_id;a.card_type=d.card_type;a.card_cost=d.cost;a.card_attack=d.attack;a.card_health=d.health;a.card_durability=d.durability;};
 auto fill_target=[&](Action& a,int id){
  if(id==hero_entity_id(0)||id==hero_entity_id(1)){int owner=owner_from_hero_id(id);a.target_is_hero=true;a.target_is_self=owner==actor;a.target_health=state_.players[owner].hero_health;a.target_attack=owner==actor?state_.players[owner].hero_attack:0;return;}
  for(int owner=0;owner<2;++owner)for(std::size_t pos=0;pos<state_.players[owner].board.size();++pos){const auto& m=state_.players[owner].board[pos];if(m.entity_id==id){a.target_is_self=owner==actor;a.target_card_id=m.card_id;a.target_attack=m.attack;a.target_health=m.health;a.target_board_position=static_cast<int>(pos);a.target_taunt=m.taunt&&!m.silenced;return;}}
 };
 auto fill_source=[&](Action& a,int id){
  if(id==hero_entity_id(actor)){a.source_is_hero=true;a.source_attack=state_.players[actor].hero_attack;a.source_health=state_.players[actor].hero_health;return;}
  for(std::size_t pos=0;pos<state_.players[actor].board.size();++pos){const auto& m=state_.players[actor].board[pos];if(m.entity_id==id){a.source_card_id=m.card_id;a.source_attack=m.attack;a.source_health=m.health;a.source_board_position=static_cast<int>(pos);return;}}
 };
 for(auto& a:actions){
  if(a.type==ActionType::PlayCard){const auto& h=state_.players[actor].hand.at(static_cast<std::size_t>(a.hand_index));const auto& d=card(h.card_id);fill_card(a,d);a.card_cost=effective_cost(actor,h);if(a.target_entity_id>=0)fill_target(a,a.target_entity_id);}
  else if(a.type==ActionType::Attack){fill_source(a,a.attacker_entity_id);fill_target(a,a.target_entity_id);}
  else if(a.type==ActionType::HeroPower){fill_card(a,card("HERO_08bp"));a.card_type="HERO_POWER";a.card_cost=2;if(a.target_entity_id>=0)fill_target(a,a.target_entity_id);}
  else if(a.type==ActionType::ChooseCard&&state_.pending_choice){const auto& choice=*state_.pending_choice;int id=choice.options.at(static_cast<std::size_t>(a.choice_index));fill_target(a,id);for(const auto& m:state_.players[choice.owner].board)if(m.entity_id==id){const auto& d=card(m.card_id);a.choice_card_id=d.card_id;a.choice_card_type=d.card_type;a.choice_card_cost=d.cost;a.choice_card_attack=d.attack;a.choice_card_health=d.health;break;}}
 }
 return actions;
}
void GameSession::draw(int p,int count){auto& me=state_.players[p];for(int i=0;i<count&&!state_.result;++i){if(me.deck.empty()){++me.fatigue;damage_character(hero_entity_id(p),me.fatigue);continue;}auto instance=std::move(me.deck.front());me.deck.erase(me.deck.begin());if(me.hand.size()<10){instance.zone=Zone::Hand;instance.controller=p;if(card(instance.card_id).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="unsupported card drawn into player hand; simulation branch invalid";me.hand.push_back(std::move(instance));}else move_to_graveyard(p,std::move(instance));}update_zone_positions(p,Zone::Deck);update_zone_positions(p,Zone::Hand);update_result();}
void GameSession::damage_character(int target,int amount){if(amount<=0)return;int p=owner_from_hero_id(target);if(p>=0&&p<2){auto& h=state_.players[p];int a=std::min(h.armor,amount);h.armor-=a;h.hero_health-=amount-a;update_result();}else damage_minion(target,amount);}
void GameSession::damage_minion(int id,int amount){for(auto& p:state_.players)for(auto& m:p.board)if(m.entity_id==id)m.health-=amount;}
void GameSession::freeze_character(int id){int owner=owner_from_hero_id(id);if(owner>=0&&owner<2){auto& p=state_.players[owner];const bool chance_now=owner==state_.active&&!p.hero_attacked;const int expiration=p.turns_started+(chance_now?0:1);p.hero_frozen=true;p.hero_freeze_expire_turn=std::max(p.hero_freeze_expire_turn,expiration);return;}for(int p=0;p<2;++p)for(auto& m:state_.players[p].board)if(m.entity_id==id){const bool chance_now=p==state_.active&&m.can_attack&&!m.has_attacked_this_turn;const int expiration=state_.players[p].turns_started+(chance_now?0:1);m.frozen=true;m.freeze_expire_owner_turn=std::max(m.freeze_expire_owner_turn,expiration);return;}}
void GameSession::recompute_hero_attack(int owner){auto& p=state_.players[owner];p.hero_attack=(owner==state_.active&&p.weapon?p.weapon->attack:0)+p.hero_temp_attack;}
int GameSession::random_index(std::size_t n){return static_cast<int>(bounded_random(n));}
void GameSession::summon_from_deck(int owner,int max_cost,int count,bool rush){for(int n=0;n<count&&state_.players[owner].board.size()<7;++n){auto& p=state_.players[owner];auto& deck=p.deck;std::vector<std::size_t> pool;for(std::size_t i=0;i<deck.size();++i){const auto& d=card(deck[i].card_id);if(is_minion(d)&&d.cost<=max_cost)pool.push_back(i);}if(pool.empty())break;auto index=bounded_random(pool.size());auto instance=std::move(deck[pool[index]]);deck.erase(deck.begin()+static_cast<std::ptrdiff_t>(pool[index]));if(card(instance.card_id).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="dynamic pool selected an unsupported outcome; simulation branch invalid";instance.zone=Zone::Board;instance.controller=owner;instance.attack=card(instance.card_id).attack;instance.health=card(instance.card_id).health;instance.max_health=instance.health;instance.rush=rush;instance.rush_only=rush;instance.can_attack=rush;instance.provenance="DECK_SUMMON";p.board.push_back(std::move(instance));update_zone_positions(owner,Zone::Deck);update_zone_positions(owner,Zone::Board);}}

void GameSession::resolve_spell(const CardDefinition& d,int owner,int target){
 const auto a=ability_of(d);int amount=d.damage;
 auto hit=[&](int id,int n,bool freeze,bool lifesteal){int p=owner_from_hero_id(id);if(p>=0&&p<2){damage_character(id,n);if(freeze)freeze_character(id);}else for(auto& side:state_.players)for(auto& m:side.board)if(m.entity_id==id){m.health-=n;if(freeze)freeze_character(id);}if(lifesteal)state_.players[owner].hero_health=std::min(30,state_.players[owner].hero_health+n);};
 switch(a){
  case Ability::CoinMana:state_.players[owner].mana=std::min(10,state_.players[owner].mana+1);break;
  case Ability::TargetDamage:hit(target,amount,false,false);break;
  case Ability::MinionDamageGenerate:hit(target,amount,false,false);if(!d.generated_card.empty()&&state_.players[owner].hand.size()<10){auto generated=make_instance(d.generated_card,owner,Zone::Hand,"GENERATED");if(card(d.generated_card).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="generated an unsupported card outcome; simulation branch invalid";state_.players[owner].hand.push_back(std::move(generated));update_zone_positions(owner,Zone::Hand);}break;
  case Ability::FreezeDamage:hit(target,amount,true,false);break;
  case Ability::LifestealDamage:hit(target,amount,false,true);break;
  case Ability::Backstab:hit(target,amount,false,false);break;
  case Ability::NextSpellDiscount:state_.players[owner].spell_discount=std::max(state_.players[owner].spell_discount,2);break;
  case Ability::EffectComposition:resolve_effects(d,owner,target);break;
  case Ability::RandomMissiles:for(int n=0;n<amount;++n){std::vector<int> pool{hero_entity_id(1-owner)};for(const auto& m:state_.players[1-owner].board)if(m.health>0)pool.push_back(m.entity_id);int pick=pool[static_cast<std::size_t>(random_index(pool.size()))];damage_character(pick,1);}break;
  case Ability::None:throw UnsupportedSimulationError("vanilla/no-effect spell cannot be resolved as an effect spell");
  default:throw UnsupportedSimulationError("effect handler is not implemented for selected card");
 }
}
void GameSession::resolve_effects(const CardDefinition& d,int owner,int target){for(const auto& e:d.effects){switch(e.kind){case EffectKind::Damage:if(e.target==TargetSelector::ExplicitCharacter||e.target==TargetSelector::ExplicitMinion)damage_character(target,e.amount);else if(e.target==TargetSelector::EnemyMinions){auto board=state_.players[1-owner].board;for(const auto& m:board)damage_minion(m.entity_id,e.amount);}else if(e.target==TargetSelector::AllCharacters){damage_character(hero_entity_id(0),e.amount);damage_character(hero_entity_id(1),e.amount);for(const auto& side:state_.players){auto board=side.board;for(const auto& m:board)damage_minion(m.entity_id,e.amount);}}else throw UnsupportedSimulationError("invalid selector for Damage effect");break;case EffectKind::Draw:draw(owner,e.amount);break;case EffectKind::GainArmor:state_.players[owner].armor+=e.amount;break;case EffectKind::ModifyHeroAttack:state_.players[owner].hero_temp_attack+=e.amount;recompute_hero_attack(owner);break;case EffectKind::Freeze:freeze_character(target);break;}}}
void GameSession::resolve_play(int index,int target){
 auto& p=state_.players[state_.active];
 CardInstance instance=std::move(p.hand.at(static_cast<std::size_t>(index)));
 const auto d=card(instance.card_id);
 p.mana-=effective_cost(state_.active,instance);
 p.hand.erase(p.hand.begin()+index);update_zone_positions(state_.active,Zone::Hand);
 if(is_spell(d)&&p.spell_discount>0)p.spell_discount=0;
 if(is_minion(d)&&d.race=="DEMON"&&p.demon_discount>0)p.demon_discount=0;
 if(is_minion(d)){
  instance.zone=Zone::Board;instance.controller=state_.active;instance.zone_position=static_cast<int>(p.board.size());
  instance.attack=d.attack;instance.health=d.health;instance.max_health=d.health;instance.can_attack=d.rush;instance.rush=d.rush;instance.rush_only=d.rush;instance.has_attacked_this_turn=false;p.board.push_back(std::move(instance));
  auto a=ability_of(d);if(a==Ability::DestroyEnemyWeapon||a==Ability::NextDemonDiscount||a==Ability::RecruiterSummonRush)state_.triggers.push_back({TriggerKind::Battlecry,state_.active,p.board.back().entity_id,d.card_id});
  update_zone_positions(state_.active,Zone::Board);
 } else if(is_weapon(d)){
  if(p.weapon)move_to_graveyard(state_.active,std::move(*p.weapon));
  instance.zone=Zone::Weapon;instance.controller=state_.active;instance.zone_position=0;p.weapon=std::move(instance);recompute_hero_attack(state_.active);
 } else if(is_spell(d)){
  update_held_card_spell_progress(state_.active);
  if(ability_of(d)==Ability::ReinforcementAura)p.timed_effects.push_back({d.card_id,d.duration>0?d.duration:3,d.pool_max_cost>0?d.pool_max_cost:2,d.pool_count>0?d.pool_count:1});else resolve_spell(d,state_.active,target);
  move_to_graveyard(state_.active,std::move(instance));
 } else {
  throw UnsupportedSimulationError("unsupported card type selected for play");
 }
 stabilize();
}
void GameSession::resolve_trigger(const Trigger& t){int owner=t.owner;
 if(t.kind==TriggerKind::Battlecry){const auto& d=card(t.card_id);switch(ability_of(d)){case Ability::DestroyEnemyWeapon:{auto& foe=state_.players[1-owner];if(foe.weapon){auto destroyed=std::move(*foe.weapon);foe.weapon.reset();move_to_graveyard(1-owner,std::move(destroyed));recompute_hero_attack(1-owner);}break;}case Ability::NextDemonDiscount:state_.players[owner].demon_discount=std::max(2,state_.players[owner].demon_discount);break;case Ability::RecruiterSummonRush:summon_from_deck(owner,d.pool_max_cost>0?d.pool_max_cost:2,d.pool_count>0?d.pool_count:2,true);break;default:throw UnsupportedSimulationError("missing Battlecry handler for supported card");}return;}
 if(t.kind==TriggerKind::Deathrattle){const auto& d=card(t.card_id);if(ability_of(d)==Ability::DeathrattleGenerate&&!d.generated_card.empty()&&state_.players[owner].hand.size()<10){auto generated=make_instance(d.generated_card,owner,Zone::Hand,"GENERATED");if(card(d.generated_card).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="deathrattle generated an unsupported card outcome; simulation branch invalid";state_.players[owner].hand.push_back(std::move(generated));update_zone_positions(owner,Zone::Hand);}return;}
 if(t.kind==TriggerKind::AfterHeroAttack){auto board=state_.players[owner].board;for(const auto& m:board)if(ability_of(card(m.card_id))==Ability::HeroAttackDraw)draw(owner);return;}
 if(t.kind==TriggerKind::EndTurn){auto board=state_.players[owner].board;for(const auto& m:board){const auto& d=card(m.card_id);auto a=ability_of(d);if(a==Ability::EndTurnEnemyAreaDamage){auto enemies=state_.players[1-owner].board;for(const auto& e:enemies)damage_minion(e.entity_id,d.damage);damage_character(hero_entity_id(1-owner),d.damage);}else if(a==Ability::EndTurnEnemyHeroDamage)damage_character(hero_entity_id(1-owner),d.damage);}
  auto& effects=state_.players[owner].timed_effects;for(auto i=effects.begin();i!=effects.end();){summon_from_deck(owner,i->max_cost,i->count,false);if(--i->turns_remaining<=0)i=effects.erase(i);else ++i;}}
}
void GameSession::stabilize(){for(;;){while(!state_.triggers.empty()){auto t=state_.triggers.front();state_.triggers.pop_front();resolve_trigger(t);update_result();if(state_.result)return;}bool died=false;for(int owner=0;owner<2;++owner){auto& board=state_.players[owner].board;for(auto i=board.begin();i!=board.end();){if(i->health>0){++i;continue;}died=true;CardInstance dead=std::move(*i);const auto d=card(dead.card_id);if(ability_of(d)==Ability::DeathrattleGenerate)state_.deathrattles.push_back({TriggerKind::Deathrattle,owner,dead.entity_id,dead.card_id});i=board.erase(i);move_to_graveyard(owner,std::move(dead));}update_zone_positions(owner,Zone::Board);}
 while(!state_.deathrattles.empty()){auto t=state_.deathrattles.front();state_.deathrattles.pop_front();resolve_trigger(t);update_result();if(state_.result)return;}if(!died&&state_.triggers.empty()&&state_.deathrattles.empty())break;}update_result();}
void GameSession::apply_action(const Action& a){auto legal=legal_actions();if(std::none_of(legal.begin(),legal.end(),[&](const Action& candidate){return candidate.execution_equal(a);}))throw std::invalid_argument("action is not legal in the current position");
 if(a.type==ActionType::ChooseCard){auto choice=*state_.pending_choice;int id=choice.options.at(static_cast<std::size_t>(a.choice_index));for(auto& m:state_.players[choice.owner].board)if(m.entity_id==id){++m.attack;++m.health;++m.max_health;}state_.pending_choice.reset();stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::PlayCard){resolve_play(a.hand_index,a.target_entity_id);if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::Attack){int owner=state_.active;bool hero=a.attacker_entity_id==hero_entity_id(owner);int attack=0;if(hero){auto& p=state_.players[owner];attack=p.hero_attack;p.hero_attacked=true;if(p.weapon){--p.weapon->durability;if(p.weapon->durability<=0){auto broken=std::move(*p.weapon);p.weapon.reset();move_to_graveyard(owner,std::move(broken));}else p.weapon->current_durability=p.weapon->durability;}recompute_hero_attack(owner);}else for(auto& m:state_.players[owner].board)if(m.entity_id==a.attacker_entity_id){attack=m.attack;m.can_attack=false;m.has_attacked_this_turn=true;}
  if(a.target_entity_id==hero_entity_id(1-owner))damage_character(a.target_entity_id,attack);else{int retaliation=0;for(const auto& m:state_.players[1-owner].board)if(m.entity_id==a.target_entity_id)retaliation=m.attack;damage_minion(a.target_entity_id,attack);if(!hero)damage_minion(a.attacker_entity_id,retaliation);}if(hero)state_.players[owner].hero_attacked=true;if(hero)state_.triggers.push_back({TriggerKind::AfterHeroAttack,owner});stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::HeroPower){auto& p=state_.players[state_.active];p.mana-=2;p.hero_power_used_this_turn=true;damage_character(a.target_entity_id,1);stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::EndTurn){int ending=state_.active;state_.triggers.push_back({TriggerKind::EndTurn,ending});stabilize();if(state_.result)return;auto& old=state_.players[ending];old.hero_temp_attack=0;old.hero_attack=0;old.hero_attacked=false;old.spell_discount=0;if(old.hero_frozen&&old.turns_started>=old.hero_freeze_expire_turn){old.hero_frozen=false;old.hero_freeze_expire_turn=0;}for(auto& m:old.board)if(m.frozen&&old.turns_started>=m.freeze_expire_owner_turn){m.frozen=false;m.freeze_expire_owner_turn=0;}state_.active=1-ending;++state_.turn_number;auto& next=state_.players[state_.active];++next.turns_started;next.max_mana=std::min(10,next.max_mana+1);next.mana=next.max_mana;next.hero_attacked=false;next.hero_power_used_this_turn=false;for(auto& m:next.board){m.can_attack=!m.frozen;m.rush_only=false;m.has_attacked_this_turn=false;}recompute_hero_attack(state_.active);draw(state_.active);update_result();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);}
}
bool GameSession::is_complete()const{return state_.result.has_value();}
void GameSession::validate_invariants()const{
 std::unordered_set<int> ids;
 auto check_zone=[&](int owner,Zone expected,const std::vector<CardInstance>& cards){for(std::size_t i=0;i<cards.size();++i){const auto& c=cards[i];if(!ids.insert(c.entity_id).second)throw std::logic_error("duplicate entity instance ID");if(c.owner<0||c.owner>1||c.controller!=owner||c.zone!=expected||c.zone_position!=static_cast<int>(i))throw std::logic_error("entity zone ownership/position mismatch");if(expected==Zone::Board&&c.health<=0)throw std::logic_error("dead entity remains targetable on board");}};
 for(int p=0;p<2;++p){const auto& x=state_.players[p];if(x.hand.size()>10||x.board.size()>7)throw std::logic_error("zone capacity invariant violated");if(x.max_mana<0||x.max_mana>10||x.mana<0||x.mana>10)throw std::logic_error("mana invariant violated");check_zone(p,Zone::Deck,x.deck);check_zone(p,Zone::Hand,x.hand);check_zone(p,Zone::Board,x.board);check_zone(p,Zone::Graveyard,x.graveyard);if(x.weapon){const auto& w=*x.weapon;if(!ids.insert(w.entity_id).second||w.zone!=Zone::Weapon||w.owner!=p||w.zone_position!=0)throw std::logic_error("weapon instance identity/zone invariant violated");}}
 if(state_.result&&!legal_actions().empty())throw std::logic_error("terminal state has gameplay actions");
}
bool GameSession::is_valid()const{return !state_.unsupported.has_value();}
std::optional<std::string> GameSession::unsupported_outcome()const{return state_.unsupported;}
std::optional<std::string> GameSession::result()const{return state_.result;}
bool GameSession::needs_choice()const{return state_.pending_choice.has_value();}
std::vector<int> GameSession::choice_options()const{return state_.pending_choice?state_.pending_choice->options:std::vector<int>{};}
std::unique_ptr<GameSession> GameSession::clone()const{return std::make_unique<GameSession>(*this);}
std::uint64_t GameSession::seed()const{return seed_;}
void GameSession::begin_prototype_choice(int max_attack){if(state_.result||state_.pending_choice)throw std::logic_error("choice unavailable");PendingChoice p;p.owner=state_.active;for(const auto& m:state_.players[p.owner].board)if(m.attack<=max_attack)p.options.push_back(m.entity_id);if(p.options.empty())throw std::logic_error("state produced no choice candidates");state_.pending_choice=std::move(p);}
Observation GameSession::observation(int perspective)const{
 if(perspective<0||perspective>1)throw std::invalid_argument("perspective must be 0 or 1");
 const int other=1-perspective;Observation o;o.turn_number=state_.turn_number;o.active_player=state_.active==perspective?"SELF":"OPPONENT";
 auto base_card=[&](const std::string& id){const auto& d=card(id);ObservedCard x;x.card_id=d.card_id;x.card_type=d.card_type;x.card_class=d.card_class;x.race=d.race;x.cost=d.cost;x.attack=d.attack;x.health=d.health;x.durability=d.durability;return x;};
 auto convert=[&](int owner){const auto& p=state_.players[owner];ObservedPlayer x;x.player_class=p.player_class;x.hero_health=std::max(0,p.hero_health);x.armor=p.armor;x.hero_attack=p.hero_attack;x.max_mana=p.max_mana;x.available_mana=p.mana;x.deck_size=static_cast<int>(p.deck.size());x.hand_size=static_cast<int>(p.hand.size());x.fatigue=p.fatigue;x.hero_power_ready=p.player_class=="MAGE"&&!p.hero_power_used_this_turn;x.hero_frozen=p.hero_frozen;
  if(p.player_class=="MAGE"){auto hp=base_card("HERO_08bp");hp.card_type="HERO_POWER";hp.current_cost=2;hp.current_attack=0;hp.current_health=0;x.hero_power=hp;}
  if(p.weapon){auto w=base_card(p.weapon->card_id);w.current_cost=w.cost;w.current_attack=p.weapon->attack;w.current_health=p.weapon->health;w.current_durability=p.weapon->durability;x.weapon=w;}
  for(const auto& m:p.board){auto b=base_card(m.card_id);b.current_cost=b.cost;b.current_attack=m.attack;b.current_health=m.health;b.current_durability=m.durability;b.board_position=m.zone_position;b.entity_id=m.entity_id;b.can_attack=m.can_attack;b.rush=m.rush;b.frozen=m.frozen;b.taunt=m.taunt&&!m.silenced;b.divine_shield=m.divine_shield;b.stealth=m.stealth;b.silenced=m.silenced;b.immune=m.immune;b.max_health=m.max_health;x.board.push_back(std::move(b));}return x;};
 o.self_player=convert(perspective);o.opponent=convert(other);
 for(const auto& h:state_.players[perspective].hand){auto item=base_card(h.card_id);item.current_cost=effective_cost(perspective,h);item.entity_id=h.entity_id;o.self_hand.push_back(std::move(item));}
 o.self_hand_known_count=static_cast<int>(o.self_hand.size());return o;
}
void GameSession::update_result(){bool a=state_.players[0].hero_health<=0,b=state_.players[1].hero_health<=0;if(a&&b)state_.result="DRAW";else if(a)state_.result="PLAYER2_WIN";else if(b)state_.result="PLAYER1_WIN";}
} // namespace manaengine
