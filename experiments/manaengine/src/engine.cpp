#include "manaengine/engine.hpp"
#include <algorithm>
#include <stdexcept>
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
 if(v=="ENEMY_BOARD_DAMAGE_DRAW")return Ability::EnemyBoardDamageDraw;
 if(v=="ALL_CHARACTERS_DAMAGE")return Ability::AllCharactersDamage;
 if(v=="NEXT_SPELL_DISCOUNT")return Ability::NextSpellDiscount;
 if(v=="NEXT_DEMON_DISCOUNT")return Ability::NextDemonDiscount;
 if(v=="HERO_ATTACK_DRAW")return Ability::HeroAttackDraw;
 if(v=="END_TURN_ENEMY_AREA_DAMAGE")return Ability::EndTurnEnemyAreaDamage;
 if(v=="END_TURN_ENEMY_HERO_DAMAGE")return Ability::EndTurnEnemyHeroDamage;
 if(v=="REINFORCEMENT_AURA")return Ability::ReinforcementAura;
 if(v=="RECRUITER_SUMMON_RUSH")return Ability::RecruiterSummonRush;
 if(v=="DAMAGE_HERO_ATTACK_DRAW_ARMOR")return Ability::DamageHeroAttackDrawArmor;
 if(v=="DAMAGE_MINION_HERO_ATTACK")return Ability::DamageMinionHeroAttack;
 if(v=="DEATHRATTLE_GENERATE")return Ability::DeathrattleGenerate;
 if(v=="RUNTIME_CHOICE_FIXTURE")return Ability::RuntimeChoiceFixture;
 return Ability::None;
}
CardCatalog::CardCatalog(std::vector<CardDefinition> definitions){auto cards=std::make_shared<std::unordered_map<std::string,CardDefinition>>();for(auto& d:definitions)if(!d.card_id.empty())cards->insert_or_assign(d.card_id,std::move(d));if(!cards->contains("GAME_005")){CardDefinition coin;coin.card_id="GAME_005";coin.name="The Coin";coin.card_type="SPELL";coin.card_class="NEUTRAL";coin.ability="COIN_MANA";cards->emplace(coin.card_id,std::move(coin));}definitions_=std::move(cards);}
GameSession::GameSession(std::vector<std::string> d1,std::vector<std::string> d2,std::vector<CardDefinition> defs,std::uint64_t seed,bool shuffle,std::string class1,std::string class2)
 :GameSession(std::move(d1),std::move(d2),std::make_shared<CardCatalog>(std::move(defs)),seed,shuffle,std::move(class1),std::move(class2)){}
GameSession::GameSession(std::vector<std::string> d1,std::vector<std::string> d2,std::shared_ptr<CardCatalog> catalog,std::uint64_t seed,bool shuffle,std::string class1,std::string class2):catalog_(std::move(catalog)),seed_(seed){
 state_.rng.seed(seed); state_.players[0].player_class=std::move(class1);state_.players[1].player_class=std::move(class2);
 state_.players[0].deck=std::move(d1);state_.players[1].deck=std::move(d2);
 for(int p=0;p<2;++p){for(const auto& id:state_.players[p].deck)(void)card(id);if(shuffle)std::shuffle(state_.players[p].deck.begin(),state_.players[p].deck.end(),state_.rng);}
 draw(0,3);draw(1,4);if(state_.players[1].hand.size()<10)state_.players[1].hand.push_back({"GAME_005",0});state_.players[0].max_mana=1;state_.players[0].mana=1;draw(0);
}
const CardDefinition& GameSession::card(const std::string& id)const{auto i=catalog_->definitions_->find(id);if(i==catalog_->definitions_->end())throw std::out_of_range("Card missing from prototype catalog: "+id);return i->second;}
int GameSession::effective_cost(int owner,const HandCard& h)const{const auto& d=card(h.card_id);int c=std::max(0,d.cost+h.cost_delta);if(is_spell(d)&&state_.players[owner].spell_discount>0)c=std::max(0,c-state_.players[owner].spell_discount);if(is_minion(d)&&d.race=="DEMON"&&state_.players[owner].demon_discount>0)c=std::max(0,c-state_.players[owner].demon_discount);return c;}
int GameSession::hero_entity_id(int owner){return owner+1;} int GameSession::owner_from_hero_id(int id){return id-1;}
std::vector<int> GameSession::legal_targets(const CardDefinition& d,int owner)const{
 auto a=ability_of(d);bool minion_only=a==Ability::MinionDamageGenerate||a==Ability::LifestealDamage||a==Ability::Backstab||a==Ability::DamageMinionHeroAttack;
 bool enemy_only=a==Ability::Backstab||a==Ability::LifestealDamage;std::vector<int> out;
 for(int p=0;p<2;++p)for(const auto& m:state_.players[p].board){if(enemy_only&&p==owner)continue;if(a==Ability::Backstab&&m.health!=m.max_health)continue;out.push_back(m.entity_id);}
 if(!minion_only){out.push_back(hero_entity_id(0));out.push_back(hero_entity_id(1));}
 return out;
}
std::vector<Action> GameSession::legal_actions()const{
 std::vector<Action> out;if(state_.result)return out;if(state_.pending_choice){for(std::size_t i=0;i<state_.pending_choice->options.size();++i)out.push_back({ActionType::ChooseCard,-1,-1,state_.pending_choice->options[i],static_cast<int>(i)});return out;}
 int p=state_.active;const auto& me=state_.players[p];const auto& foe=state_.players[1-p];out.push_back({ActionType::EndTurn});
 for(std::size_t i=0;i<me.hand.size();++i){const auto& h=me.hand[i];const auto& d=card(h.card_id);if(effective_cost(p,h)>me.mana||(is_minion(d)&&me.board.size()>=7))continue;
 auto a=ability_of(d);if(a==Ability::TargetDamage||a==Ability::MinionDamageGenerate||a==Ability::FreezeDamage||a==Ability::LifestealDamage||a==Ability::Backstab||a==Ability::DamageHeroAttackDrawArmor||a==Ability::DamageMinionHeroAttack){for(int t:legal_targets(d,p))out.push_back({ActionType::PlayCard,static_cast<int>(i),-1,t});}else out.push_back({ActionType::PlayCard,static_cast<int>(i)});
 }
 if(me.player_class=="MAGE"&&!me.hero_power_used_this_turn&&me.mana>=2){CardDefinition power;power.ability="TARGET_DAMAGE";for(int t:legal_targets(power,p))out.push_back({ActionType::HeroPower,-1,-1,t});}
 bool taunt=false;for(const auto& m:foe.board)if(card(m.card_id).taunt)taunt=true;
 auto add_attacks=[&](int attacker,bool ready,bool rush_only){if(!ready)return;for(const auto& m:foe.board){if(taunt&&!card(m.card_id).taunt)continue;out.push_back({ActionType::Attack,-1,attacker,m.entity_id});}if(!taunt&&!rush_only)out.push_back({ActionType::Attack,-1,attacker,hero_entity_id(1-p)});};
 for(const auto& m:me.board)add_attacks(m.entity_id,m.can_attack&&!m.frozen,m.rush_only);
 if(!me.hero_attacked&&(me.hero_attack>0||(me.weapon&&me.weapon->durability>0)))add_attacks(hero_entity_id(p),true,false);
 return out;
}
void GameSession::draw(int p,int count){auto& me=state_.players[p];for(int i=0;i<count&&!state_.result;++i){if(me.deck.empty()){++me.fatigue;damage_character(hero_entity_id(p),me.fatigue);continue;}auto id=me.deck.front();me.deck.erase(me.deck.begin());if(me.hand.size()<10)me.hand.push_back({std::move(id),0});}update_result();}
void GameSession::damage_character(int target,int amount){if(amount<=0)return;int p=owner_from_hero_id(target);if(p>=0&&p<2){auto& h=state_.players[p];int a=std::min(h.armor,amount);h.armor-=a;h.hero_health-=amount-a;update_result();}else damage_minion(target,amount);}
void GameSession::damage_minion(int id,int amount){for(auto& p:state_.players)for(auto& m:p.board)if(m.entity_id==id)m.health-=amount;}
int GameSession::random_index(std::size_t n){if(!n)throw std::invalid_argument("empty random candidate set");std::uniform_int_distribution<std::size_t>d(0,n-1);return static_cast<int>(d(state_.rng));}
void GameSession::summon_from_deck(int owner,int max_cost,int count,bool rush){for(int n=0;n<count&&state_.players[owner].board.size()<7;++n){auto& deck=state_.players[owner].deck;std::vector<std::size_t> pool;for(std::size_t i=0;i<deck.size();++i){const auto& d=card(deck[i]);if(is_minion(d)&&d.cost<=max_cost)pool.push_back(i);}if(pool.empty())break;auto index=pool[static_cast<std::size_t>(random_index(pool.size()))];auto id=deck[index];deck.erase(deck.begin()+static_cast<std::ptrdiff_t>(index));const auto& d=card(id);int eid=state_.next_entity_id++;state_.players[owner].board.push_back({eid,id,d.attack,d.health,d.health,rush,rush,rush,false});}}

void GameSession::resolve_spell(const CardDefinition& d,int owner,int target){
 const auto a=ability_of(d);int amount=d.damage;
 auto hit=[&](int id,int n,bool freeze,bool lifesteal){int p=owner_from_hero_id(id);if(p>=0&&p<2)damage_character(id,n);else for(auto& side:state_.players)for(auto& m:side.board)if(m.entity_id==id){m.health-=n;if(freeze)m.frozen=true;}if(lifesteal)state_.players[owner].hero_health=std::min(30,state_.players[owner].hero_health+n);};
 switch(a){
  case Ability::CoinMana:state_.players[owner].mana=std::min(10,state_.players[owner].mana+1);break;
  case Ability::TargetDamage:hit(target,amount,false,false);break;
  case Ability::MinionDamageGenerate:hit(target,amount,false,false);if(!d.generated_card.empty()&&state_.players[owner].hand.size()<10)state_.players[owner].hand.push_back({d.generated_card,0});break;
  case Ability::FreezeDamage:hit(target,amount,true,false);break;
  case Ability::LifestealDamage:hit(target,amount,false,true);break;
  case Ability::Backstab:hit(target,amount,false,false);break;
  case Ability::EnemyBoardDamageDraw:{auto enemies=state_.players[1-owner].board;for(const auto& m:enemies)damage_minion(m.entity_id,amount);draw(owner);break;}
  case Ability::AllCharactersDamage:{damage_character(hero_entity_id(0),amount);damage_character(hero_entity_id(1),amount);for(const auto& side:state_.players){auto board=side.board;for(const auto& m:board)damage_minion(m.entity_id,amount);}break;}
  case Ability::NextSpellDiscount:state_.players[owner].spell_discount=std::max(state_.players[owner].spell_discount,2);break;
  case Ability::DamageHeroAttackDrawArmor:hit(target,amount,false,false);state_.players[owner].hero_attack++;state_.players[owner].hero_temp_attack++;draw(owner);state_.players[owner].armor++;break;
  case Ability::DamageMinionHeroAttack:hit(target,amount,false,false);state_.players[owner].hero_attack++;state_.players[owner].hero_temp_attack++;break;
  case Ability::RandomMissiles:for(int n=0;n<amount;++n){std::vector<int> pool{hero_entity_id(1-owner)};for(const auto& m:state_.players[1-owner].board)if(m.health>0)pool.push_back(m.entity_id);int pick=pool[static_cast<std::size_t>(random_index(pool.size()))];damage_character(pick,1);}break;
  default:break;
 }
}
void GameSession::resolve_play(int index,int target){auto& p=state_.players[state_.active];HandCard h=p.hand.at(static_cast<std::size_t>(index));auto d=card(h.card_id);p.mana-=effective_cost(state_.active,h);p.hand.erase(p.hand.begin()+index);if(is_spell(d)&&p.spell_discount>0)p.spell_discount=0;if(is_minion(d)&&d.race=="DEMON"&&p.demon_discount>0)p.demon_discount=0;
 if(is_minion(d)){int eid=state_.next_entity_id++;bool rush=d.rush;p.board.push_back({eid,d.card_id,d.attack,d.health,d.health,rush,rush,rush,false});auto a=ability_of(d);if(a==Ability::DestroyEnemyWeapon||a==Ability::NextDemonDiscount||a==Ability::RecruiterSummonRush)state_.triggers.push_back({TriggerKind::Battlecry,state_.active,eid,d.card_id});}
 else if(is_weapon(d)){if(p.weapon)p.hero_attack-=p.weapon->attack;p.weapon=WeaponState{d.card_id,d.attack,d.durability};p.hero_attack+=d.attack;}
 else if(is_spell(d)){if(ability_of(d)==Ability::ReinforcementAura)p.timed_effects.push_back({d.card_id,d.duration>0?d.duration:3,d.pool_max_cost>0?d.pool_max_cost:2,d.pool_count>0?d.pool_count:1});else resolve_spell(d,state_.active,target);}
 stabilize();
}
void GameSession::resolve_trigger(const Trigger& t){int owner=t.owner;
 if(t.kind==TriggerKind::Battlecry){const auto& d=card(t.card_id);switch(ability_of(d)){case Ability::DestroyEnemyWeapon:state_.players[1-owner].weapon.reset();state_.players[1-owner].hero_attack=state_.players[1-owner].hero_temp_attack;break;case Ability::NextDemonDiscount:state_.players[owner].demon_discount=std::max(2,state_.players[owner].demon_discount);break;case Ability::RecruiterSummonRush:summon_from_deck(owner,d.pool_max_cost>0?d.pool_max_cost:2,d.pool_count>0?d.pool_count:2,true);break;default:break;}return;}
 if(t.kind==TriggerKind::Deathrattle){const auto& d=card(t.card_id);if(ability_of(d)==Ability::DeathrattleGenerate&&!d.generated_card.empty()&&state_.players[owner].hand.size()<10)state_.players[owner].hand.push_back({d.generated_card,0});return;}
 if(t.kind==TriggerKind::AfterHeroAttack){auto board=state_.players[owner].board;for(const auto& m:board)if(ability_of(card(m.card_id))==Ability::HeroAttackDraw)draw(owner);return;}
 if(t.kind==TriggerKind::EndTurn){auto board=state_.players[owner].board;for(const auto& m:board){const auto& d=card(m.card_id);auto a=ability_of(d);if(a==Ability::EndTurnEnemyAreaDamage){auto enemies=state_.players[1-owner].board;for(const auto& e:enemies)damage_minion(e.entity_id,d.damage);damage_character(hero_entity_id(1-owner),d.damage);}else if(a==Ability::EndTurnEnemyHeroDamage)damage_character(hero_entity_id(1-owner),d.damage);}
  auto& effects=state_.players[owner].timed_effects;for(auto i=effects.begin();i!=effects.end();){summon_from_deck(owner,i->max_cost,i->count,false);if(--i->turns_remaining<=0)i=effects.erase(i);else ++i;}}
}
void GameSession::stabilize(){for(;;){while(!state_.triggers.empty()){auto t=state_.triggers.front();state_.triggers.pop_front();resolve_trigger(t);update_result();if(state_.result)return;}bool died=false;for(int owner=0;owner<2;++owner){auto& board=state_.players[owner].board;for(auto i=board.begin();i!=board.end();){if(i->health>0){++i;continue;}died=true;const auto d=card(i->card_id);if(ability_of(d)==Ability::DeathrattleGenerate)state_.deathrattles.push_back({TriggerKind::Deathrattle,owner,i->entity_id,i->card_id});i=board.erase(i);}}
 while(!state_.deathrattles.empty()){auto t=state_.deathrattles.front();state_.deathrattles.pop_front();resolve_trigger(t);update_result();if(state_.result)return;}if(!died&&state_.triggers.empty()&&state_.deathrattles.empty())break;}update_result();}
void GameSession::apply_action(const Action& a){auto legal=legal_actions();if(std::find(legal.begin(),legal.end(),a)==legal.end())throw std::invalid_argument("action is not legal in the current position");
 if(a.type==ActionType::ChooseCard){auto choice=*state_.pending_choice;int id=choice.options.at(static_cast<std::size_t>(a.choice_index));for(auto& m:state_.players[choice.owner].board)if(m.entity_id==id){++m.attack;++m.health;++m.max_health;}state_.pending_choice.reset();stabilize();return;}
 if(a.type==ActionType::PlayCard){resolve_play(a.hand_index,a.target_entity_id);return;}
 if(a.type==ActionType::Attack){int owner=state_.active;bool hero=a.attacker_entity_id==hero_entity_id(owner);int attack=0;if(hero){auto& p=state_.players[owner];attack=p.hero_attack;p.hero_attacked=true;if(p.weapon){--p.weapon->durability;if(p.weapon->durability<=0)p.weapon.reset();}p.hero_attack=p.hero_temp_attack;}else for(auto& m:state_.players[owner].board)if(m.entity_id==a.attacker_entity_id){attack=m.attack;m.can_attack=false;}
  if(a.target_entity_id==hero_entity_id(1-owner))damage_character(a.target_entity_id,attack);else{int retaliation=0;for(const auto& m:state_.players[1-owner].board)if(m.entity_id==a.target_entity_id)retaliation=m.attack;damage_minion(a.target_entity_id,attack);if(!hero)damage_minion(a.attacker_entity_id,retaliation);}if(hero)state_.triggers.push_back({TriggerKind::AfterHeroAttack,owner});stabilize();return;}
 if(a.type==ActionType::HeroPower){auto& p=state_.players[state_.active];p.mana-=2;p.hero_power_used_this_turn=true;damage_character(a.target_entity_id,1);stabilize();return;}
 if(a.type==ActionType::EndTurn){int ending=state_.active;state_.triggers.push_back({TriggerKind::EndTurn,ending});stabilize();if(state_.result)return;auto& old=state_.players[ending];old.hero_temp_attack=0;old.hero_attack=old.weapon?old.weapon->attack:0;old.hero_attacked=false;old.spell_discount=0;old.demon_discount=0;state_.active=1-ending;++state_.turn_number;auto& next=state_.players[state_.active];next.max_mana=std::min(10,next.max_mana+1);next.mana=next.max_mana;next.hero_attack=next.weapon?next.weapon->attack:0;next.hero_attacked=false;next.hero_power_used_this_turn=false;for(auto& m:next.board){m.can_attack=!m.frozen;m.rush_only=false;}draw(state_.active);update_result();}
}
bool GameSession::is_complete()const{return state_.result.has_value();}
std::optional<std::string> GameSession::result()const{return state_.result;}
bool GameSession::needs_choice()const{return state_.pending_choice.has_value();}
std::vector<int> GameSession::choice_options()const{return state_.pending_choice?state_.pending_choice->options:std::vector<int>{};}
std::unique_ptr<GameSession> GameSession::clone()const{return std::make_unique<GameSession>(*this);}
std::uint64_t GameSession::seed()const{return seed_;}
void GameSession::begin_prototype_choice(int max_attack){if(state_.result||state_.pending_choice)throw std::logic_error("choice unavailable");PendingChoice p;p.owner=state_.active;for(const auto& m:state_.players[p.owner].board)if(m.attack<=max_attack)p.options.push_back(m.entity_id);if(p.options.empty())throw std::logic_error("state produced no choice candidates");state_.pending_choice=std::move(p);}
Observation GameSession::observation(int perspective)const{if(perspective<0||perspective>1)throw std::invalid_argument("perspective must be 0 or 1");int other=1-perspective;Observation o;o.turn_number=state_.turn_number;o.active_player=state_.active==perspective?"SELF":"OPPONENT";
 auto convert=[&](int owner){const auto& p=state_.players[owner];ObservedPlayer x;x.player_class=p.player_class;x.hero_health=std::max(0,p.hero_health);x.armor=p.armor;x.hero_attack=p.hero_attack;x.max_mana=p.max_mana;x.available_mana=p.mana;x.deck_size=static_cast<int>(p.deck.size());x.hand_size=static_cast<int>(p.hand.size());x.fatigue=p.fatigue;x.hero_power_ready=p.player_class=="MAGE"&&!p.hero_power_used_this_turn;if(p.player_class=="MAGE")x.hero_power=ObservedCard{"HERO_08bp","HERO_POWER","MAGE","",2,2,0,0,0};if(p.weapon){const auto& d=card(p.weapon->card_id);x.weapon=ObservedCard{d.card_id,d.card_type,d.card_class,d.race,d.cost,d.cost,d.attack,d.health,d.durability,p.weapon->attack,p.weapon->durability};}int pos=0;for(const auto& m:p.board){const auto& d=card(m.card_id);x.board.push_back(ObservedCard{d.card_id,d.card_type,d.card_class,d.race,d.cost,d.cost,d.attack,d.health,d.durability,m.attack,m.health,pos++,m.entity_id,m.can_attack,m.rush,m.frozen});x.board.back().max_health=m.max_health;}return x;};
 o.self_player=convert(perspective);o.opponent=convert(other);for(const auto& h:state_.players[perspective].hand){const auto& d=card(h.card_id);o.self_hand.push_back(ObservedCard{d.card_id,d.card_type,d.card_class,d.race,d.cost,effective_cost(perspective,h),d.attack,d.health,d.durability});}o.self_hand_known_count=static_cast<int>(o.self_hand.size());return o;}
void GameSession::update_result(){bool a=state_.players[0].hero_health<=0,b=state_.players[1].hero_health<=0;if(a&&b)state_.result="DRAW";else if(a)state_.result="PLAYER2_WIN";else if(b)state_.result="PLAYER1_WIN";}
} // namespace manaengine
