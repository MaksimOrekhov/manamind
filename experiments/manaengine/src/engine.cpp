#include "manaengine/engine.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <unordered_set>
#include <utility>
namespace manaengine {
namespace { bool is_minion(const CardDefinition& c){return c.card_type=="MINION";} bool is_spell(const CardDefinition& c){return c.card_type=="SPELL";} bool is_weapon(const CardDefinition& c){return c.card_type=="WEAPON";} bool is_secret(const CardDefinition& c){return c.secret;} }
void GameSession::trace_event(std::string event){if(state_.trace_enabled)state_.trace.push_back(std::move(event));}
void GameSession::assign_activation_sequence(CardInstance& source){source.activation_sequence=state_.next_event_sequence++;}
void GameSession::activate_secret(CardInstance secret){auto& owner=state_.players[secret.owner];const auto& definition=card(secret.card_id);if(!is_secret(definition))throw std::logic_error("only Secret cards can enter Secret zone");if(owner.secrets.size()>=5||std::any_of(owner.secrets.begin(),owner.secrets.end(),[&](const auto& active){return active.card_id==secret.card_id;})){trace_event("SECRET_CAST_FAILED card="+secret.card_id);return;}secret.zone=Zone::Secret;secret.controller=secret.owner;secret.zone_position=static_cast<int>(owner.secrets.size());assign_activation_sequence(secret);owner.secrets.push_back(std::move(secret));trace_event("SECRET_ACTIVATE card="+owner.secrets.back().card_id+" sequence="+std::to_string(owner.secrets.back().activation_sequence));}

namespace { const char* trace_action_name(ActionType type){switch(type){case ActionType::PlayCard:return "PLAY_CARD";case ActionType::PrepareCard:return "PREPARE_CARD";case ActionType::Attack:return "ATTACK";case ActionType::HeroPower:return "HERO_POWER";case ActionType::EndTurn:return "END_TURN";case ActionType::ChooseCard:return "CHOOSE_CARD";}return "UNKNOWN";} }
GameSession::Ability GameSession::ability_of(const CardDefinition& c) {
 const auto& v=c.ability;
 if(v=="COIN_MANA")return Ability::CoinMana;
 if(v=="TARGET_DAMAGE")return Ability::TargetDamage;
 if(v=="MINION_DAMAGE_GENERATE")return Ability::MinionDamageGenerate;
 if(v=="RANDOM_MISSILES")return Ability::RandomMissiles;
 if(v=="DISCOVER")return Ability::Discover;
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
 if(v=="CAST_RANDOM_SECRETS")return Ability::CastRandomSecrets;
 if(v=="SPELL_DAMAGE_AURA")return Ability::SpellDamageAura;
 if(v=="DEATHRATTLE_DRAW")return Ability::DeathrattleDraw;
 if(v=="SPELL_DAMAGE_GAINS_ATTACK")return Ability::SpellDamageGainsAttack;
 if(v=="SPELL_DAMAGE_HAND_DECK")return Ability::SpellDamageHandDeck;
 if(v=="SECRET")return Ability::None;
 if(v=="NONE"&&c.support_state=="VERIFIED_VANILLA")return Ability::None;
 if(v=="NONE")throw UnsupportedSimulationError("unsupported card effect: "+c.card_id);
 throw std::invalid_argument("unknown ManaEngine ability: "+v+" on "+c.card_id);
}
std::optional<GameSession::EventWindow> GameSession::secret_window_of(const std::string& trigger){
 if(trigger=="OPPONENT_CASTS_SPELL")return EventWindow::OpponentCastsSpell;if(trigger=="FRIENDLY_MINION_ATTACKED")return EventWindow::FriendlyMinionAttacked;if(trigger=="FRIENDLY_HERO_ATTACKED")return EventWindow::FriendlyHeroAttacked;if(trigger=="ENEMY_MINION_ATTACKS")return EventWindow::EnemyMinionAttacks;if(trigger=="OPPONENT_PLAYS_MINION")return EventWindow::OpponentPlaysMinion;if(trigger=="OPPONENT_TURN_ENDS")return EventWindow::OpponentTurnEnds;return std::nullopt;
}
GameSession::SecretEffect GameSession::secret_effect_of(const CardDefinition& card){
 if(card.secret_effect=="COUNTERSPELL")return SecretEffect::Counterspell;if(card.secret_effect=="ICE_BARRIER")return SecretEffect::IceBarrier;if(card.secret_effect=="OASIS_ALLY")return SecretEffect::OasisAlly;if(card.secret_effect=="MYSTIC_MISDIRECTION")return SecretEffect::MysticMisdirection;if(card.secret_effect=="EXPLOSIVE_RUNES")return SecretEffect::ExplosiveRunes;if(card.secret_effect=="FLAMES_OF_INFINITY")return SecretEffect::FlamesOfInfinity;if(card.secret_effect=="ENEMY_AREA_DAMAGE")return SecretEffect::EnemyAreaDamage;throw std::invalid_argument("unknown Secret effect on "+card.card_id);
}
CardCatalog::CardCatalog(std::vector<CardDefinition> definitions){
 static const std::unordered_set<std::string> abilities={"NONE","COIN_MANA","TARGET_DAMAGE","MINION_DAMAGE_GENERATE","RANDOM_MISSILES","DISCOVER","DESTROY_ENEMY_WEAPON","FREEZE_DAMAGE","LIFESTEAL_DAMAGE","BACKSTAB","NEXT_SPELL_DISCOUNT","NEXT_DEMON_DISCOUNT","HERO_ATTACK_DRAW","END_TURN_ENEMY_AREA_DAMAGE","END_TURN_ENEMY_HERO_DAMAGE","REINFORCEMENT_AURA","RECRUITER_SUMMON_RUSH","EFFECT_COMPOSITION","DEATHRATTLE_GENERATE","RUNTIME_CHOICE_FIXTURE","HELD_SPELL_COST_REDUCTION","SECRET","CAST_RANDOM_SECRETS","SPELL_DAMAGE_AURA","DEATHRATTLE_DRAW","SPELL_DAMAGE_GAINS_ATTACK","SPELL_DAMAGE_HAND_DECK"};
 auto cards=std::make_shared<std::unordered_map<std::string,CardDefinition>>();
 for(auto& d:definitions){if(d.minion_types.empty()&&!d.race.empty())d.minion_types={d.race};if(d.kindred_copy_contract!="NONE"&&(d.kindred_copy_contract!="INSTANCE_COPY_V1"||!is_minion(d)||d.minion_types.empty()||d.ability!="DEATHRATTLE_DRAW"||d.deck_draw_filter!=DeckDrawFilter::Spell||d.deathrattle_draw_count!=1||d.rush||d.taunt||d.lifesteal||d.prepare||d.battlecry||!d.shatter_left_card.empty()||d.spell_damage||d.damaged_spell_damage))throw std::invalid_argument("unsupported Kindred copy contract");if(d.card_id.empty())throw std::invalid_argument("CardDefinition.card_id cannot be empty");if(!abilities.contains(d.ability))throw std::invalid_argument("unknown ManaEngine ability: "+d.ability+" on "+d.card_id);if(d.support_state!="SUPPORTED"&&d.support_state!="VERIFIED_VANILLA"&&d.support_state!="UNSUPPORTED")throw std::invalid_argument("invalid support_state on "+d.card_id);if(d.support_state!="UNSUPPORTED"&&!d.rules_contract_reviewed)throw std::invalid_argument("support requires an explicit reviewed rules contract: "+d.card_id);for(const auto& mechanic:d.required_mechanics){bool represented=(mechanic=="TRIGGER_VISUAL"||mechanic=="EVIL_GLOW")||(mechanic=="TAUNT"&&d.taunt)||(mechanic=="RUSH"&&d.rush)||(mechanic=="LIFESTEAL"&&(d.lifesteal||d.ability=="LIFESTEAL_DAMAGE"||std::any_of(d.effects.begin(),d.effects.end(),[](const auto& e){return e.lifesteal;})))||(mechanic=="BATTLECRY"&&d.battlecry&&d.ability!="NONE")||(mechanic=="SECRET"&&d.ability=="SECRET")||(mechanic=="IMMUNETOSPELLPOWER"&&(d.ability=="SECRET"||d.ability=="RANDOM_MISSILES"))||(mechanic=="DEATHRATTLE"&&(d.ability=="DEATHRATTLE_DRAW"||d.ability=="DEATHRATTLE_GENERATE"))||(mechanic=="SPELLPOWER"&&(d.spell_damage>0||d.damaged_spell_damage>0))||(mechanic=="DISCOVER"&&d.ability=="DISCOVER")||(mechanic=="FREEZE"&&(d.ability=="FREEZE_DAMAGE"||std::any_of(d.effects.begin(),d.effects.end(),[](const auto& e){return e.kind==EffectKind::Freeze;})));if(d.support_state!="UNSUPPORTED"&&!represented)throw std::invalid_argument("unrepresented rules mechanic "+mechanic+" on "+d.card_id);}if(d.support_state=="VERIFIED_VANILLA"&&d.ability!="NONE")throw std::invalid_argument("VERIFIED_VANILLA card must use NONE ability: "+d.card_id);if(d.support_state=="SUPPORTED"&&d.ability=="NONE")throw std::invalid_argument("SUPPORTED card must declare an implemented ability: "+d.card_id);if(d.ability=="SECRET"&&(!is_secret(d)||d.secret_trigger=="NONE"||d.secret_effect=="NONE"))throw std::invalid_argument("SECRET requires a typed trigger/effect declaration: "+d.card_id);if(d.ability=="SECRET"){static const std::unordered_set<std::string> contracts={"FRIENDLY_MINION_ATTACKED|OASIS_ALLY","OPPONENT_CASTS_SPELL|COUNTERSPELL","FRIENDLY_HERO_ATTACKED|ICE_BARRIER","OPPONENT_PLAYS_MINION|EXPLOSIVE_RUNES","OPPONENT_TURN_ENDS|FLAMES_OF_INFINITY","ENEMY_MINION_ATTACKS|MYSTIC_MISDIRECTION","FRIENDLY_HERO_ATTACKED|ENEMY_AREA_DAMAGE"};if(!contracts.contains(d.secret_trigger+"|"+d.secret_effect))throw std::invalid_argument("unsupported Secret trigger/effect contract: "+d.card_id);}if((d.ability=="CAST_RANDOM_SECRETS")!=(d.random_cast_count>0)|| (d.ability=="CAST_RANDOM_SECRETS"&&(!is_minion(d)||!d.battlecry)))throw std::invalid_argument("CAST_RANDOM_SECRETS requires a minion Battlecry and positive random_cast_count: "+d.card_id);if((d.ability=="EFFECT_COMPOSITION")!=(!d.effects.empty()))throw std::invalid_argument("EFFECT_COMPOSITION requires a nonempty effects list, and other abilities must not declare effects: "+d.card_id);if((d.ability=="HELD_SPELL_COST_REDUCTION")!=(d.spell_cost_reduction_per_cast>0))throw std::invalid_argument("HELD_SPELL_COST_REDUCTION requires a positive spell_cost_reduction_per_cast and other abilities must not declare one: "+d.card_id);if((d.held_spell_threshold>0)!=(!d.transform_card.empty()))throw std::invalid_argument("held_spell_threshold and transform_card must be declared together: "+d.card_id);if(d.held_spell_threshold>0&&(!is_spell(d)||d.effects.empty()))throw std::invalid_argument("held-card threshold applies only to an effect spell: "+d.card_id);if((d.ability=="DISCOVER")!=(d.choice_count>0&&!d.choice_pool.empty()))throw std::invalid_argument("DISCOVER requires a positive choice_count and declared choice_pool: "+d.card_id);if(d.ability=="DISCOVER"&&(!is_spell(d)||d.choice_count!=3||d.choice_cost_delta>0||d.choice_pool!="MINION_BATTLECRY_PLAYER_CLASS_NEUTRAL"))throw std::invalid_argument("unsupported DISCOVER contract on "+d.card_id);if(d.lifesteal&&d.card_type!="MINION")throw std::invalid_argument("Lifesteal keyword is only modeled on minions: "+d.card_id);if((d.shatter_left_card.empty())!=d.shatter_right_card.empty())throw std::invalid_argument("Shatter must declare both fragment card IDs: "+d.card_id);if((!d.shatter_left_card.empty())&&!is_spell(d))throw std::invalid_argument("Shatter source must be a spell with two declared fragments: "+d.card_id);if(d.spell_damage_cost_reduction<0||(d.spell_damage_cost_reduction>0&&!is_spell(d)))throw std::invalid_argument("spell damage cost reduction requires a nonnegative spell coefficient: "+d.card_id);for(const auto& e:d.effects){if(e.kind==EffectKind::SummonFixed){if(e.target!=TargetSelector::Self||e.amount<=0||e.amount>7||e.summon_card.empty())throw std::invalid_argument("SummonFixed requires SELF, count 1..7 and dependency: "+d.card_id);if((e.summon_condition==SummonCondition::None)!=(e.conditional_extra_count==0)||e.conditional_extra_count<0||e.conditional_extra_count>7)throw std::invalid_argument("SummonFixed condition and extra count must be paired within 0..7: "+d.card_id);}else if(!e.summon_card.empty()||e.summon_condition!=SummonCondition::None||e.conditional_extra_count!=0)throw std::invalid_argument("summon-only fields require SummonFixed: "+d.card_id);if(e.target==TargetSelector::RandomEnemyMinion&&e.kind!=EffectKind::Damage)throw std::invalid_argument("RandomEnemyMinion requires a Damage step: "+d.card_id);if(e.amount<0)throw std::invalid_argument("effect amount cannot be negative: "+d.card_id);if(e.kind==EffectKind::Damage&&(e.target==TargetSelector::Self))throw std::invalid_argument("Damage cannot target Self: "+d.card_id);if(e.lifesteal&&e.kind!=EffectKind::Damage)throw std::invalid_argument("Lifesteal may only be applied to Damage steps: "+d.card_id);if(e.kind==EffectKind::Draw&&e.target!=TargetSelector::Self)throw std::invalid_argument("Draw must target Self: "+d.card_id);if(e.kind==EffectKind::GainArmor&&e.target!=TargetSelector::Self)throw std::invalid_argument("GainArmor must target Self: "+d.card_id);if(e.kind==EffectKind::ModifyHeroAttack&&e.target!=TargetSelector::Self)throw std::invalid_argument("ModifyHeroAttack must target Self: "+d.card_id);if(e.kind==EffectKind::Freeze&&((e.target!=TargetSelector::ExplicitCharacter&&e.target!=TargetSelector::ExplicitEnemyCharacter)||e.amount!=0))throw std::invalid_argument("Freeze requires an explicit character target and amount zero: "+d.card_id);}if(!cards->emplace(d.card_id,std::move(d)).second)throw std::invalid_argument("duplicate CardDefinition ID");}
 for(const auto& [id,d]:*cards){if(d.spell_damage<0||d.damaged_spell_damage<0||d.deathrattle_draw_count<0||d.spell_damage_attack<0||d.spell_damage_grant<0)throw std::invalid_argument("Spell Damage, trigger Attack, and deathrattle draw values cannot be negative: "+id);if((d.ability=="SPELL_DAMAGE_AURA")!=(d.damaged_spell_damage>0))throw std::invalid_argument("SPELL_DAMAGE_AURA requires a positive damaged-only Spell Damage value: "+id);if((d.ability=="DEATHRATTLE_DRAW")!=(d.deathrattle_draw_count>0))throw std::invalid_argument("DEATHRATTLE_DRAW requires a positive draw count: "+id);if(d.ability!="DEATHRATTLE_DRAW"&&d.deck_draw_filter!=DeckDrawFilter::Any)throw std::invalid_argument("deck draw filter is valid only for DEATHRATTLE_DRAW: "+id);if(d.ability=="DEATHRATTLE_DRAW"&&!is_minion(d))throw std::invalid_argument("DEATHRATTLE_DRAW requires a minion: "+id);if((d.ability=="SPELL_DAMAGE_GAINS_ATTACK")!=(d.spell_damage_attack>0))throw std::invalid_argument("SPELL_DAMAGE_GAINS_ATTACK requires a positive spell_damage_attack value: "+id);if(d.ability=="SPELL_DAMAGE_GAINS_ATTACK"&&!is_minion(d))throw std::invalid_argument("SPELL_DAMAGE_GAINS_ATTACK requires a minion: "+id);if((d.ability=="SPELL_DAMAGE_HAND_DECK")!=(d.spell_damage_grant>0))throw std::invalid_argument("SPELL_DAMAGE_HAND_DECK requires a positive spell_damage_grant and other abilities must not declare one: "+id);if(d.ability=="SPELL_DAMAGE_HAND_DECK"&&(!is_minion(d)||!d.battlecry))throw std::invalid_argument("SPELL_DAMAGE_HAND_DECK requires a minion Battlecry: "+id);if((d.spell_damage>0||d.damaged_spell_damage>0)&&!is_minion(d))throw std::invalid_argument("Spell Damage aura requires a minion: "+id);}
 for(const auto& [id,d]:*cards)for(const auto& e:d.effects){if(e.kind==EffectKind::DestroyMinion&&e.target!=TargetSelector::ExplicitDamagedEnemyMinion&&e.target!=TargetSelector::ExplicitFriendlyMinion)throw std::invalid_argument("DestroyMinion requires a side-constrained minion target: "+id);if((e.target==TargetSelector::ExplicitDamagedEnemyMinion||e.target==TargetSelector::ExplicitFriendlyMinion)&&e.kind!=EffectKind::DestroyMinion)throw std::invalid_argument("side-constrained minion selectors require DestroyMinion: "+id);if((e.target==TargetSelector::AllMinions||e.target==TargetSelector::SelfHero)&&e.kind!=EffectKind::Damage)throw std::invalid_argument("area/self-hero selectors require Damage: "+id);if(e.kind==EffectKind::Heal&&(e.target!=TargetSelector::ExplicitCharacter||e.amount<=0))throw std::invalid_argument("Heal requires EXPLICIT_CHARACTER and a positive amount: "+id);if(e.kind==EffectKind::HealMinionToFull&&(e.target!=TargetSelector::ExplicitMinion||e.amount!=0))throw std::invalid_argument("HealMinionToFull requires EXPLICIT_MINION and zero amount: "+id);}
 for(const auto& [id,d]:*cards)if(d.secret_effect=="ENEMY_AREA_DAMAGE"&&(d.secret_trigger!="FRIENDLY_HERO_ATTACKED"||d.damage<=0))throw std::invalid_argument("ENEMY_AREA_DAMAGE requires FRIENDLY_HERO_ATTACKED and positive damage: "+id);
 for(const auto& [id,d]:*cards){const auto condition=d.damage_outcome_condition;const auto followup=d.damage_outcome_followup;const bool allowed=(condition==DamageOutcomeCondition::MortallyWounded&&(followup==DamageOutcomeFollowup::DrawSelf||followup==DamageOutcomeFollowup::HealEnemyHero))||(condition==DamageOutcomeCondition::Survives&&followup==DamageOutcomeFollowup::DrawSelf)||(condition==DamageOutcomeCondition::Always&&followup==DamageOutcomeFollowup::DrawTargetOwner);if((condition!=DamageOutcomeCondition::None&&!allowed)||(condition==DamageOutcomeCondition::None&&followup!=DamageOutcomeFollowup::None))throw std::invalid_argument("unsupported damage outcome condition/follow-up pair: "+id);}
 for(const auto& [id,d]:*cards)if(d.damage_outcome_followup==DamageOutcomeFollowup::DrawTargetOwner&&d.damage_outcome_amount!=0)throw std::invalid_argument("DRAW_TARGET_OWNER does not accept a numeric amount: "+id);
 for(const auto& [id,d]:*cards){const bool conditioned=d.damage_outcome_condition!=DamageOutcomeCondition::None;const bool followup=d.damage_outcome_followup!=DamageOutcomeFollowup::None;if(conditioned!=followup)throw std::invalid_argument("damage outcome condition and follow-up must be declared together: "+id);if(!conditioned){if(d.damage_outcome_amount!=0)throw std::invalid_argument("damage_outcome_amount requires an outcome follow-up: "+id);continue;}if(d.ability!="EFFECT_COMPOSITION"||!is_spell(d)||d.effects.size()!=1||d.effects.front().kind!=EffectKind::Damage||d.effects.front().target!=TargetSelector::ExplicitMinion||d.effects.front().amount<=0||d.effects.front().lifesteal)throw std::invalid_argument("damage outcome v1 requires one positive explicit-minion spell damage step: "+id);if((d.damage_outcome_followup==DamageOutcomeFollowup::DrawSelf&&d.damage_outcome_amount!=0)||(d.damage_outcome_followup==DamageOutcomeFollowup::HealEnemyHero&&d.damage_outcome_amount<=0))throw std::invalid_argument("invalid damage outcome follow-up amount: "+id);}
 for(const auto& [id,d]:*cards)if(d.support_state!="UNSUPPORTED"&&!d.shatter_left_card.empty()){if(d.shatter_left_card==d.shatter_right_card||!cards->contains(d.shatter_left_card)||!cards->contains(d.shatter_right_card))throw std::invalid_argument("Shatter fragment definitions are missing or duplicated for "+id);const auto& left=cards->at(d.shatter_left_card);const auto& right=cards->at(d.shatter_right_card);if(left.support_state=="UNSUPPORTED"||right.support_state=="UNSUPPORTED"||!is_spell(left)||!is_spell(right)||left.cost!=d.cost||right.cost!=d.cost||!left.shatter_left_card.empty()||!right.shatter_left_card.empty())throw std::invalid_argument("Shatter fragments must be supported non-Shatter spells with the source cost for "+id);}
 for(const auto& [id,d]:*cards)for(const auto& e:d.effects)if(e.kind==EffectKind::SummonFixed){
  const auto dependency=cards->find(e.summon_card);
  if(dependency==cards->end()||!is_minion(dependency->second)||dependency->second.support_state=="UNSUPPORTED")throw std::invalid_argument("SummonFixed requires a supported exact minion dependency: "+id);
 }
 for(const auto& [id,d]:*cards){for(std::size_t i=0;i<d.effects.size();++i){const auto& e=d.effects[i];if(e.kind==EffectKind::BuffFriendlyMinions&&(e.target!=TargetSelector::Self||e.amount<=0||e.amount>30||e.discard_school!=DiscardSpellSchool::None))throw std::invalid_argument("BuffFriendlyMinions requires SELF, positive stats and no discard school: "+id);if(e.kind==EffectKind::DiscardRandomSpell&&(e.target!=TargetSelector::Self||e.amount!=0||e.discard_school==DiscardSpellSchool::None||e.requires_previous_discard))throw std::invalid_argument("DiscardRandomSpell requires SELF, zero amount and an explicit school: "+id);if(e.kind!=EffectKind::DiscardRandomSpell&&e.discard_school!=DiscardSpellSchool::None)throw std::invalid_argument("discard_school is only valid on DiscardRandomSpell: "+id);if(e.requires_previous_discard&&(e.kind!=EffectKind::BuffFriendlyMinions||i==0||d.effects[i-1].kind!=EffectKind::DiscardRandomSpell))throw std::invalid_argument("conditional buff must directly follow DiscardRandomSpell: "+id);}}
 if(!cards->contains("GAME_005")){CardDefinition coin;coin.card_id="GAME_005";coin.name="The Coin";coin.card_type="SPELL";coin.card_class="NEUTRAL";coin.ability="COIN_MANA";coin.support_state="SUPPORTED";coin.rules_contract_reviewed=true;cards->emplace(coin.card_id,std::move(coin));}
 definitions_=std::move(cards);
}
GameSession::GameSession(std::vector<std::string> d1,std::vector<std::string> d2,std::vector<CardDefinition> defs,std::uint64_t seed,bool shuffle,std::string class1,std::string class2)
 :GameSession(std::move(d1),std::move(d2),std::make_shared<CardCatalog>(std::move(defs)),seed,shuffle,std::move(class1),std::move(class2)){}
GameSession::GameSession(std::vector<std::string> d1,std::vector<std::string> d2,std::shared_ptr<CardCatalog> catalog,std::uint64_t seed,bool shuffle,std::string class1,std::string class2):catalog_(std::move(catalog)),seed_(seed){
 if(class1!="MAGE"||class2!="MAGE")throw UnsupportedSimulationError("session requires implemented hero powers; only Mage mirror supported");
 state_.rng.seed(seed); state_.players[0].player_class=std::move(class1);state_.players[1].player_class=std::move(class2);
 for(int p=0;p<2;++p){auto& deck=p==0?d1:d2;for(const auto& id:deck)state_.players[p].deck.push_back(make_instance(id,p,Zone::Deck,"DECK"));if(shuffle)stable_shuffle(state_.players[p].deck);update_zone_positions(p,Zone::Deck);}
 draw(0,3);draw(1,4);if(state_.players[1].hand.size()<10){auto coin=make_instance("GAME_005",1,Zone::Hand,"GENERATED");state_.players[1].hand.push_back(std::move(coin));update_zone_positions(1,Zone::Hand);}state_.players[0].max_mana=1;state_.players[0].mana=1;draw(0);state_.players[0].turns_started=1;recompute_hero_attack(0);
}
const CardDefinition& GameSession::card(const std::string& id)const{auto i=catalog_->definitions_->find(id);if(i==catalog_->definitions_->end())throw std::out_of_range("Card missing from prototype catalog: "+id);return i->second;}
GameSession::CardInstance GameSession::make_instance(const std::string& id,int owner,Zone zone,std::string provenance){const auto& d=card(id);CardInstance x;x.entity_id=state_.next_entity_id++;x.card_id=id;x.owner=owner;x.controller=owner;x.zone=zone;x.provenance=std::move(provenance);x.attack=d.attack;x.health=d.health;x.max_health=d.health;x.durability=d.durability;x.current_durability=d.durability;x.rush=d.rush;x.taunt=d.taunt;x.lifesteal=d.lifesteal;return x;}
void GameSession::update_zone_positions(int owner,Zone zone){auto& p=state_.players[owner];auto set=[&](auto& values){for(std::size_t i=0;i<values.size();++i){values[i].zone=zone;values[i].zone_position=static_cast<int>(i);}};if(zone==Zone::Deck)set(p.deck);else if(zone==Zone::Hand)set(p.hand);else if(zone==Zone::Board)set(p.board);else if(zone==Zone::Secret)set(p.secrets);else if(zone==Zone::Graveyard)set(p.graveyard);else if(zone==Zone::Weapon&&p.weapon){p.weapon->zone=zone;p.weapon->zone_position=0;}}
void GameSession::move_to_graveyard(int owner,CardInstance instance){instance.zone=Zone::Graveyard;instance.controller=owner;instance.zone_position=static_cast<int>(state_.players[owner].graveyard.size());state_.players[owner].graveyard.push_back(std::move(instance));}
void GameSession::enter_hand(int owner,CardInstance instance){auto& hand=state_.players[owner].hand;if(hand.size()>=10){move_to_graveyard(owner,std::move(instance));return;}instance.zone=Zone::Hand;instance.controller=owner;if(card(instance.card_id).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="unsupported card entered player hand; simulation branch invalid";const auto& d=card(instance.card_id);if(!instance.shatter_consumed&&!d.shatter_left_card.empty()){shatter_on_hand_entry(owner,std::move(instance));return;}hand.push_back(std::move(instance));update_zone_positions(owner,Zone::Hand);update_shatter_links(owner);}
void GameSession::shatter_on_hand_entry(int owner,CardInstance original){if(original.spell_damage_bonus!=0||original.cost_delta!=0||original.prepare_locked_turn>=0||!original.counters.empty()||!original.enchantments.empty()){state_.unsupported="Shatter pre-split modifier inheritance requires independent rules verification";throw UnsupportedSimulationError(*state_.unsupported);}auto& hand=state_.players[owner].hand;const auto& source=card(original.card_id);if(hand.size()>=10){move_to_graveyard(owner,std::move(original));return;}const auto left_id=source.shatter_left_card,right_id=source.shatter_right_card;CardInstance left=std::move(original);left.card_id=left_id;left.shatter_original_card_id=source.card_id;left.shatter_fragment=ShatterFragment::Left;left.shatter_consumed=true;if(hand.size()==9){left.shatter_fragment=ShatterFragment::Solo;left.shatter_partner_entity_id=-1;hand.insert(hand.begin(),std::move(left));trace_event("SHATTER_SOLO card="+source.card_id+" fragment="+left_id);update_zone_positions(owner,Zone::Hand);update_shatter_links(owner);return;}CardInstance right=make_instance(right_id,owner,Zone::Hand,"SHATTERED");right.spell_damage_bonus=left.spell_damage_bonus;right.shatter_original_card_id=source.card_id;right.shatter_fragment=ShatterFragment::Right;right.shatter_consumed=true;left.shatter_partner_entity_id=right.entity_id;right.shatter_partner_entity_id=left.entity_id;hand.insert(hand.begin(),std::move(left));hand.push_back(std::move(right));trace_event("SHATTER card="+source.card_id+" fragments="+left_id+","+right_id);update_zone_positions(owner,Zone::Hand);update_shatter_links(owner);}
void GameSession::update_shatter_links(int owner){auto& hand=state_.players[owner].hand;for(std::size_t i=0;i<hand.size();++i){auto& fragment=hand[i];if(fragment.shatter_fragment==ShatterFragment::None||fragment.shatter_fragment==ShatterFragment::Solo)continue;auto partner=std::find_if(hand.begin(),hand.end(),[&](const auto& item){return item.entity_id==fragment.shatter_partner_entity_id;});if(partner==hand.end()){fragment.shatter_partner_entity_id=-1;fragment.shatter_fragment=ShatterFragment::Solo;trace_event("SHATTER_UNLINK entity="+std::to_string(fragment.entity_id));continue;}}
for(;;){bool recombined=false;for(std::size_t i=0;i+1<hand.size();++i){auto& left=hand[i];auto& right=hand[i+1];if(left.shatter_fragment!=ShatterFragment::Left||right.shatter_fragment!=ShatterFragment::Right||left.shatter_partner_entity_id!=right.entity_id||right.shatter_partner_entity_id!=left.entity_id)continue;if(left.cost_delta!=0||right.cost_delta!=0||left.spell_damage_bonus!=0||right.spell_damage_bonus!=0||left.prepare_locked_turn>=0||right.prepare_locked_turn>=0||!left.counters.empty()||!right.counters.empty()||!left.enchantments.empty()||!right.enchantments.empty()){state_.unsupported="Shatter merge of instance modifiers requires rules verification";throw UnsupportedSimulationError(*state_.unsupported);}CardInstance combined=std::move(left);CardInstance other=std::move(right);const std::string original=combined.shatter_original_card_id;combined.card_id=original;combined.shatter_original_card_id.clear();combined.shatter_partner_entity_id=-1;combined.shatter_fragment=ShatterFragment::None;combined.shatter_consumed=true;combined.cost_delta+=other.cost_delta;combined.spell_damage_bonus+=other.spell_damage_bonus;combined.enchantments.insert(combined.enchantments.end(),other.enchantments.begin(),other.enchantments.end());for(const auto& [key,value]:other.counters)combined.counters[key]+=value;hand.erase(hand.begin()+static_cast<std::ptrdiff_t>(i),hand.begin()+static_cast<std::ptrdiff_t>(i+2));hand.insert(hand.begin()+static_cast<std::ptrdiff_t>(i),std::move(combined));trace_event("SHATTER_RECOMBINE card="+original);update_zone_positions(owner,Zone::Hand);recombined=true;break;}if(!recombined)break;}}
std::uint64_t GameSession::next_u64(){return state_.rng();}
std::size_t GameSession::bounded_random(std::size_t bound){if(bound==0)throw std::invalid_argument("empty random candidate set");const auto n=static_cast<std::uint64_t>(bound);const auto threshold=(std::uint64_t{0}-n)%n;for(;;){auto value=next_u64();if(value>=threshold)return static_cast<std::size_t>(value%n);}}
void GameSession::stable_shuffle(std::vector<CardInstance>& values){for(std::size_t i=values.size();i>1;--i){auto j=bounded_random(i);std::swap(values[i-1],values[j]);}}
int GameSession::effective_cost(int owner,const HandCard& h)const{
 const auto& d=card(h.card_id);std::int64_t c=std::max<std::int64_t>(0,static_cast<std::int64_t>(d.cost)+h.cost_delta);
 if(d.spell_damage_cost_reduction>0){
  const auto dealt=state_.players[owner].spell_damage_dealt_this_turn;
  const auto coefficient=d.spell_damage_cost_reduction;
  // Compare before multiplication: a saturated damage counter cannot overflow cost arithmetic.
  c=dealt>=(c+coefficient-1)/coefficient?0:c-dealt*coefficient;
 }
 if(is_spell(d))c=std::max<std::int64_t>(0,c-state_.players[owner].spell_discount);
 if(is_minion(d)&&d.race=="DEMON")c=std::max<std::int64_t>(0,c-state_.players[owner].demon_discount);
 return static_cast<int>(std::min<std::int64_t>(c,std::numeric_limits<int>::max()));
}
int GameSession::spell_damage_for(int owner)const{int amount=0;for(const auto& minion:state_.players[owner].board){if(minion.silenced)continue;const auto& definition=card(minion.card_id);amount+=definition.spell_damage;if(minion.health<minion.max_health)amount+=definition.damaged_spell_damage;}return amount;}
void GameSession::update_held_card_spell_progress(int owner){for(auto& held:state_.players[owner].hand){const auto& d=card(held.card_id);const auto ability=ability_of(d);if(ability==Ability::HeldSpellCostReduction){++held.counters["spells_played_from_hand"];held.cost_delta-=d.spell_cost_reduction_per_cast;continue;}if(d.held_spell_threshold<=0)continue;const int progress=++held.counters["held_spell_threshold"];if(progress>=d.held_spell_threshold){const auto transformed=d.transform_card;held.card_id=transformed;held.counters.erase("held_spell_threshold");held.attack=card(transformed).attack;held.health=card(transformed).health;held.max_health=card(transformed).health;held.lifesteal=card(transformed).lifesteal;}}}
int GameSession::hero_entity_id(int owner){return owner+1;} int GameSession::owner_from_hero_id(int id){return id-1;}
std::vector<int> GameSession::legal_targets(const CardDefinition& d,int owner)const{
 auto a=ability_of(d);bool minion_only=a==Ability::MinionDamageGenerate||a==Ability::LifestealDamage||a==Ability::Backstab;
 bool enemy_only=false;bool friendly_only=false;bool damaged_only=false; // Backstab and Drain Soul permit friendly minions too.
 if(a==Ability::EffectComposition)for(const auto& e:d.effects){if((e.kind==EffectKind::Damage&&e.target==TargetSelector::ExplicitMinion)||e.kind==EffectKind::DestroyMinion||e.kind==EffectKind::HealMinionToFull)minion_only=true;if(e.target==TargetSelector::ExplicitEnemyCharacter||e.target==TargetSelector::ExplicitDamagedEnemyMinion)enemy_only=true;if(e.target==TargetSelector::ExplicitFriendlyMinion)friendly_only=true;if(e.target==TargetSelector::ExplicitDamagedEnemyMinion)damaged_only=true;}
 std::vector<int> out;
 for(int p=0;p<2;++p)for(const auto& m:state_.players[p].board){if((enemy_only||friendly_only)&&p==owner&&enemy_only)continue;if(friendly_only&&p!=owner)continue;if(damaged_only&&m.health>=m.max_health)continue;if(a==Ability::Backstab&&m.health!=m.max_health)continue;out.push_back(m.entity_id);}
 if(!minion_only){if(enemy_only)out.push_back(hero_entity_id(1-owner));else{out.push_back(hero_entity_id(0));out.push_back(hero_entity_id(1));}}
 return out;
}
std::vector<Action> GameSession::legal_actions()const{
 if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);
 std::vector<Action> out;if(state_.result)return out;if(state_.pending_choice){const auto& choice=*state_.pending_choice;const auto count=choice.continuation==ContinuationKind::AddSelectedCardToHand?choice.card_options.size():choice.options.size();for(std::size_t i=0;i<count;++i)out.push_back({ActionType::ChooseCard,-1,-1,choice.continuation==ContinuationKind::AddSelectedCardToHand?-1:choice.options[i],static_cast<int>(i)});return out;}
 int p=state_.active;const auto& me=state_.players[p];const auto& foe=state_.players[1-p];out.push_back({ActionType::EndTurn});
 for(std::size_t i=0;i<me.hand.size();++i){const auto& h=me.hand[i];const auto& d=card(h.card_id);if(d.support_state=="UNSUPPORTED")throw UnsupportedSimulationError("unsupported card is available to the active player");const int cost=effective_cost(p,h);if(d.prepare&&h.prepare_locked_turn<0&&me.mana>0&&cost>0){Action prepare;prepare.type=ActionType::PrepareCard;prepare.hand_index=static_cast<int>(i);out.push_back(prepare);}if(h.prepare_locked_turn==state_.turn_number||cost>me.mana||(is_minion(d)&&me.board.size()>=7)||(is_secret(d)&&(me.secrets.size()>=5||std::any_of(me.secrets.begin(),me.secrets.end(),[&](const auto& active){return active.card_id==d.card_id;}))))continue;
 auto a=ability_of(d);bool targeted=a==Ability::TargetDamage||a==Ability::MinionDamageGenerate||a==Ability::FreezeDamage||a==Ability::LifestealDamage||a==Ability::Backstab;if(a==Ability::EffectComposition)targeted=std::any_of(d.effects.begin(),d.effects.end(),[](const auto& e){return (e.kind==EffectKind::Damage&&(e.target==TargetSelector::ExplicitCharacter||e.target==TargetSelector::ExplicitEnemyCharacter||e.target==TargetSelector::ExplicitMinion))||e.kind==EffectKind::DestroyMinion||e.kind==EffectKind::Heal||e.kind==EffectKind::HealMinionToFull||(e.kind==EffectKind::Freeze&&(e.target==TargetSelector::ExplicitCharacter||e.target==TargetSelector::ExplicitEnemyCharacter));});if(targeted){for(int t:legal_targets(d,p))out.push_back({ActionType::PlayCard,static_cast<int>(i),-1,t});}else out.push_back({ActionType::PlayCard,static_cast<int>(i)});
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
  if(a.type==ActionType::PlayCard||a.type==ActionType::PrepareCard){const auto& h=state_.players[actor].hand.at(static_cast<std::size_t>(a.hand_index));const auto& d=card(h.card_id);fill_card(a,d);a.card_cost=effective_cost(actor,h);if(a.type==ActionType::PlayCard){a.shatter_original_card_id=h.shatter_original_card_id;if(h.shatter_fragment==ShatterFragment::Left)a.shatter_fragment="LEFT";else if(h.shatter_fragment==ShatterFragment::Right)a.shatter_fragment="RIGHT";else if(h.shatter_fragment==ShatterFragment::Solo)a.shatter_fragment="SOLO";if(h.shatter_partner_entity_id>=0){auto partner=std::find_if(state_.players[actor].hand.begin(),state_.players[actor].hand.end(),[&](const auto& item){return item.entity_id==h.shatter_partner_entity_id;});if(partner!=state_.players[actor].hand.end())a.shatter_partner_hand_position=partner->zone_position;}if(a.target_entity_id>=0)fill_target(a,a.target_entity_id);}}
  else if(a.type==ActionType::Attack){fill_source(a,a.attacker_entity_id);fill_target(a,a.target_entity_id);}
  else if(a.type==ActionType::HeroPower){fill_card(a,card("HERO_08bp"));a.card_type="HERO_POWER";a.card_cost=2;if(a.target_entity_id>=0)fill_target(a,a.target_entity_id);}
  else if(a.type==ActionType::ChooseCard&&state_.pending_choice){const auto& choice=*state_.pending_choice;if(choice.continuation==ContinuationKind::AddSelectedCardToHand){const auto& d=card(choice.card_options.at(static_cast<std::size_t>(a.choice_index)));a.choice_card_id=d.card_id;a.choice_card_type=d.card_type;a.choice_card_cost=std::max(0,d.cost+choice.choice_cost_delta);a.choice_card_attack=d.attack;a.choice_card_health=d.health;}else{int id=choice.options.at(static_cast<std::size_t>(a.choice_index));fill_target(a,id);for(const auto& m:state_.players[choice.owner].board)if(m.entity_id==id){const auto& d=card(m.card_id);a.choice_card_id=d.card_id;a.choice_card_type=d.card_type;a.choice_card_cost=d.cost;a.choice_card_attack=d.attack;a.choice_card_health=d.health;break;}}}
 }
 return actions;
}
void GameSession::draw(int p,int count){auto& me=state_.players[p];for(int i=0;i<count;++i){if(me.deck.empty()){++me.fatigue;deal_damage(-1,hero_entity_id(p),me.fatigue,DamageKind::Fatigue,p);continue;}auto instance=std::move(me.deck.front());me.deck.erase(me.deck.begin());enter_hand(p,std::move(instance));}update_zone_positions(p,Zone::Deck);update_zone_positions(p,Zone::Hand);}
void GameSession::draw_from_deck(int p,int count,DeckDrawFilter filter){if(filter==DeckDrawFilter::Any){draw(p,count);return;}auto& me=state_.players[p];for(int n=0;n<count&&!state_.result;++n){std::vector<std::size_t> candidates;for(std::size_t i=0;i<me.deck.size();++i){const auto& d=card(me.deck[i].card_id);const bool matches=filter==DeckDrawFilter::Spell?is_spell(d):filter==DeckDrawFilter::FireSpell?is_spell(d)&&d.spell_school=="FIRE":false;if(matches)candidates.push_back(i);}if(candidates.empty())break;const auto selected=candidates[static_cast<std::size_t>(bounded_random(candidates.size()))];auto instance=std::move(me.deck[selected]);me.deck.erase(me.deck.begin()+static_cast<std::ptrdiff_t>(selected));enter_hand(p,std::move(instance));}update_zone_positions(p,Zone::Deck);update_zone_positions(p,Zone::Hand);update_result();}
int GameSession::deal_damage(int source,int target,int amount,DamageKind kind,int controller,bool lifesteal,DamageAttribution attribution){
 if(attribution==DamageAttribution::DirectSpell&&(kind!=DamageKind::Spell||controller<0||controller>=2))throw std::logic_error("DirectSpell requires Spell damage and a valid controller");
 if(amount<=0)return 0;
 const int hero=owner_from_hero_id(target);int dealt=0;
 if(hero>=0&&hero<2){auto& h=state_.players[hero];const int absorbed=std::min(h.armor,amount);h.armor-=absorbed;h.hero_health-=amount-absorbed;dealt=amount;}
 else for(auto& side:state_.players)for(auto& m:side.board)if(m.entity_id==target){
  if(m.immune)return 0;
  if(m.divine_shield){m.divine_shield=false;trace_event("DAMAGE_PREVENTED target="+std::to_string(target));return 0;}
  m.health=static_cast<int>(std::max<std::int64_t>(-2147483647LL,static_cast<std::int64_t>(m.health)-amount));dealt=amount;
 }
 if(dealt>0){trace_event("DAMAGE source="+std::to_string(source)+" target="+std::to_string(target)+" amount="+std::to_string(dealt));
  if(attribution==DamageAttribution::DirectSpell){
   auto& total=state_.players[controller].spell_damage_dealt_this_turn;
   total+=std::min<std::int64_t>(dealt,std::numeric_limits<std::int64_t>::max()-total);
   trace_event("DIRECT_SPELL_DAMAGE_TURN controller="+std::to_string(controller)+" total="+std::to_string(total));
  }
  if(lifesteal&&controller>=0&&controller<2)state_.players[controller].hero_health=std::min(30,state_.players[controller].hero_health+dealt);
  if(kind==DamageKind::Spell)record_spell_damage_event(controller,dealt);
 }
 return dealt;
}
namespace {
const std::vector<std::string> history_types={"BEAST","DEMON","DRAENEI","DRAGON","ELEMENTAL","MECHANICAL","MURLOC","NAGA","PIRATE","QUILBOAR","TOTEM","UNDEAD"};
std::vector<std::string> played_types(const CardDefinition& d){
 std::vector<std::string> types;
 for(const auto& type:d.minion_types){
  if(type=="ALL"){types=history_types;break;}
  if(std::find(history_types.begin(),history_types.end(),type)==history_types.end())throw UnsupportedSimulationError("unreviewed minion history type: "+type);
  types.push_back(type);
 }
 std::sort(types.begin(),types.end());types.erase(std::unique(types.begin(),types.end()),types.end());return types;
}
}
void GameSession::record_minion_play(int owner,const CardDefinition& d){
 auto& history=state_.players[owner].current_turn_minion_types_played;
 std::vector<std::string> types;try{types=played_types(d);}catch(const UnsupportedSimulationError& e){state_.unsupported=e.what();throw;}
 history.insert(history.end(),types.begin(),types.end());
 std::sort(history.begin(),history.end());history.erase(std::unique(history.begin(),history.end()),history.end());
}
bool GameSession::kindred_qualified(int owner,const CardDefinition& d)const{
 const auto& previous=state_.players[owner].previous_turn_minion_types_played;
 for(const auto& type:played_types(d))if(std::find(previous.begin(),previous.end(),type)!=previous.end())return true;
 return false;
}
void GameSession::validate_instance_copy_v1(const CardInstance& s,int owner,Zone expected){
 const auto& d=card(s.card_id);
 const bool invalid=!is_minion(d)||s.owner!=owner||s.controller!=owner||s.zone!=expected||
  s.attack!=d.attack||s.max_health!=d.health||s.health!=s.max_health||s.health<=0||
  s.cost_delta!=0||s.spell_damage_bonus!=0||!s.enchantments.empty()||!s.counters.empty()||
  s.frozen||s.freeze_expire_owner_turn!=0||s.silenced||s.divine_shield||s.taunt||s.lifesteal||s.immune||s.stealth||s.rush||s.rush_only||
  !s.shatter_original_card_id.empty()||s.shatter_partner_entity_id!=-1||s.shatter_fragment!=ShatterFragment::None||s.shatter_consumed||
  s.prepare_locked_turn!=-1||s.durability!=0||s.current_durability!=0||s.can_attack||s.has_attacked_this_turn||
  d.spell_damage!=0||d.damaged_spell_damage!=0||d.rush||d.taunt||d.lifesteal||state_.pending_choice.has_value()||!state_.deathrattles.empty();
 bool pending_death=false;for(const auto& p:state_.players)for(const auto& m:p.board)pending_death|=m.health<=0;
 if(invalid||pending_death){state_.unsupported="INSTANCE_COPY_V1: unreviewed source state";throw UnsupportedSimulationError(*state_.unsupported);}
 if(expected==Zone::Board&&(state_.players[owner].board.empty()||state_.players[owner].board.back().entity_id!=s.entity_id)){
  state_.unsupported="INSTANCE_COPY_V1: non-rightmost source";throw UnsupportedSimulationError(*state_.unsupported);
 }
}
void GameSession::summon_instance_copy_v1(int owner,int entity){
 auto& board=state_.players[owner].board;
 const auto found=std::find_if(board.begin(),board.end(),[&](const auto& s){return s.entity_id==entity;});
 if(found==board.end()){state_.unsupported="INSTANCE_COPY_V1: source unavailable";throw UnsupportedSimulationError(*state_.unsupported);}
 validate_instance_copy_v1(*found,owner,Zone::Board);
 if(board.size()>=7)return;
 CardInstance copy;
 // Explicit field policy: COPY reviewed state, NEW_IDENTITY handles,
 // RECOMPUTE ownership/placement/provenance, RESET summon bookkeeping.
 // Every other member retains its guarded default; never copy the struct.
 copy.card_id=found->card_id;copy.attack=found->attack;copy.health=found->health;copy.max_health=found->max_health;
 copy.entity_id=state_.next_entity_id++;copy.owner=owner;copy.controller=owner;copy.zone=Zone::Board;
 copy.zone_position=static_cast<int>(board.size());copy.provenance="INSTANCE_COPY_V1";
 copy.can_attack=false;copy.has_attacked_this_turn=false;assign_activation_sequence(copy);
 const auto copy_entity=copy.entity_id;board.push_back(std::move(copy));update_zone_positions(owner,Zone::Board);
 trace_event("INSTANCE_COPY_V1 source="+std::to_string(entity)+" copy="+std::to_string(copy_entity));
}
void GameSession::summon_fixed(int owner,const std::string& id,int count){
 const auto& definition=card(id);
 if(!is_minion(definition)||definition.support_state=="UNSUPPORTED"){
  state_.unsupported="unsupported fixed summon dependency: "+id;
  throw UnsupportedSimulationError(*state_.unsupported);
 }
 auto& board=state_.players[owner].board;
 for(int n=0;n<count&&board.size()<7;++n){
  auto instance=make_instance(id,owner,Zone::Board,"FIXED_SUMMON");
  instance.can_attack=instance.rush;instance.rush_only=instance.rush;
  assign_activation_sequence(instance);board.push_back(std::move(instance));
  trace_event("FIXED_SUMMON card="+id+" entity="+std::to_string(board.back().entity_id));
 }
 update_zone_positions(owner,Zone::Board);
}
void GameSession::transform_board(int owner,int entity,const std::string& id){
 const auto& definition=card(id);if(definition.support_state=="UNSUPPORTED"){state_.unsupported="unsupported Transform outcome: "+id;throw UnsupportedSimulationError(*state_.unsupported);}
 for(auto& instance:state_.players[owner].board)if(instance.entity_id==entity){
  auto replacement=make_instance(id,owner,Zone::Board,"TRANSFORM");replacement.entity_id=instance.entity_id;replacement.owner=instance.owner;replacement.controller=instance.controller;replacement.zone_position=instance.zone_position;
  replacement.has_attacked_this_turn=instance.has_attacked_this_turn;replacement.can_attack=false;assign_activation_sequence(replacement);instance=std::move(replacement);return;
 }
}
void GameSession::freeze_character(int id){int owner=owner_from_hero_id(id);if(owner>=0&&owner<2){auto& p=state_.players[owner];const bool chance_now=owner==state_.active&&!p.hero_attacked;const int expiration=p.turns_started+(chance_now?0:1);p.hero_frozen=true;p.hero_freeze_expire_turn=std::max(p.hero_freeze_expire_turn,expiration);return;}for(int p=0;p<2;++p)for(auto& m:state_.players[p].board)if(m.entity_id==id){const bool chance_now=p==state_.active&&m.can_attack&&!m.has_attacked_this_turn;const int expiration=state_.players[p].turns_started+(chance_now?0:1);m.frozen=true;m.freeze_expire_owner_turn=std::max(m.freeze_expire_owner_turn,expiration);return;}}
void GameSession::recompute_hero_attack(int owner){auto& p=state_.players[owner];p.hero_attack=(owner==state_.active&&p.weapon?p.weapon->attack:0)+p.hero_temp_attack;}
int GameSession::random_index(std::size_t n){return static_cast<int>(bounded_random(n));}
void GameSession::begin_discover(int owner,const CardDefinition& source){std::vector<std::string> pool;for(const auto& [id,d]:*catalog_->definitions_){if(!d.collectible||!d.battlecry||!is_minion(d))continue;if(d.card_class!="NEUTRAL"&&d.card_class!=state_.players[owner].player_class)continue;pool.push_back(id);}std::sort(pool.begin(),pool.end());if(pool.size()<static_cast<std::size_t>(source.choice_count))throw UnsupportedSimulationError("complete pinned Discover pool has fewer options than the card requests");PendingChoice choice;choice.owner=owner;choice.choice_cost_delta=source.choice_cost_delta;choice.continuation=ContinuationKind::AddSelectedCardToHand;for(int i=0;i<source.choice_count;++i){const auto remaining=pool.size()-static_cast<std::size_t>(i);const auto picked=static_cast<std::size_t>(i)+bounded_random(remaining);std::swap(pool[static_cast<std::size_t>(i)],pool[picked]);choice.card_options.push_back(pool[static_cast<std::size_t>(i)]);}trace_event("CHOICE_BEGIN source="+source.card_id+" options="+std::to_string(choice.card_options.size()));state_.pending_choice=std::move(choice);}
void GameSession::summon_from_deck(int owner,int max_cost,int count,bool rush){for(int n=0;n<count&&state_.players[owner].board.size()<7;++n){auto& p=state_.players[owner];auto& deck=p.deck;std::vector<std::size_t> pool;for(std::size_t i=0;i<deck.size();++i){const auto& d=card(deck[i].card_id);if(is_minion(d)&&d.cost<=max_cost)pool.push_back(i);}if(pool.empty())break;auto index=bounded_random(pool.size());auto instance=std::move(deck[pool[index]]);deck.erase(deck.begin()+static_cast<std::ptrdiff_t>(pool[index]));if(card(instance.card_id).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="dynamic pool selected an unsupported outcome; simulation branch invalid";instance.zone=Zone::Board;instance.controller=owner;instance.attack=card(instance.card_id).attack;instance.health=card(instance.card_id).health;instance.max_health=instance.health;instance.rush=rush;instance.rush_only=rush;instance.can_attack=rush;instance.provenance="DECK_SUMMON";assign_activation_sequence(instance);p.board.push_back(std::move(instance));update_zone_positions(owner,Zone::Deck);update_zone_positions(owner,Zone::Board);}}

int GameSession::evaluate_spell_damage(const SpellEffectContext& context,int base_amount){
 // A new instruction is not a trigger/death-processing boundary. Do not guess
 // whether a pending mortal aura still contributes to a subsequent instruction.
 if(context.contract==DamageEvaluationContract::CurrentAtStep){
  for(const auto& source:state_.players[context.owner].board){
   const auto& definition=card(source.card_id);
   if(source.health<=0&&!source.silenced&&(definition.spell_damage>0||definition.damaged_spell_damage>0)){
    state_.unsupported="damage-boundary v1: mortally wounded Spell Damage source before instruction";
    throw UnsupportedSimulationError(*state_.unsupported);
   }
  }
 }
 const int board_bonus=spell_damage_for(context.owner);
 const int amount=base_amount+board_bonus+context.persistent_bonus;
 trace_event("DAMAGE_BOUNDARY version="+std::to_string(damage_boundary_contract_version)+
  " contract="+(context.contract==DamageEvaluationContract::CurrentAtStep?std::string("CURRENT_AT_STEP"):std::string("MISSILE_TOTAL"))+
  " source="+std::to_string(context.source_entity)+" base="+std::to_string(base_amount)+
  " board="+std::to_string(board_bonus)+" persistent="+std::to_string(context.persistent_bonus)+" amount="+std::to_string(amount));
 return amount;
}
void GameSession::resolve_spell(const CardDefinition& d,int owner,int target,int card_spell_damage,int source_entity){
 trace_event("EFFECT_BEGIN card="+d.card_id);
 const auto a=ability_of(d);
 const SpellEffectContext context{owner,source_entity,card_spell_damage,
  a==Ability::RandomMissiles?DamageEvaluationContract::MissileTotal:DamageEvaluationContract::CurrentAtStep};
 int spell_damage_dealt=0;
 auto hit=[&](int id,bool freeze,bool lifesteal){const int dealt=deal_damage(source_entity,id,evaluate_spell_damage(context,d.damage),DamageKind::Spell,owner,lifesteal,DamageAttribution::DirectSpell);if(freeze)freeze_character(id);return dealt;};
 switch(a){
  case Ability::CoinMana:state_.players[owner].mana=std::min(10,state_.players[owner].mana+1);break;
  case Ability::TargetDamage:spell_damage_dealt=hit(target,false,false);break;
  case Ability::MinionDamageGenerate:spell_damage_dealt=hit(target,false,false);if(!d.generated_card.empty()&&state_.players[owner].hand.size()<10){auto generated=make_instance(d.generated_card,owner,Zone::Hand,"GENERATED");if(card(d.generated_card).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="generated an unsupported card outcome; simulation branch invalid";enter_hand(owner,std::move(generated));}break;
  case Ability::FreezeDamage:spell_damage_dealt=hit(target,true,false);break;
  case Ability::LifestealDamage:spell_damage_dealt=hit(target,false,true);break;
  case Ability::Backstab:spell_damage_dealt=hit(target,false,false);break;
  case Ability::NextSpellDiscount:state_.players[owner].spell_discount=std::max(state_.players[owner].spell_discount,2);break;
  case Ability::Discover:begin_discover(owner,d);break;
  case Ability::EffectComposition:spell_damage_dealt=resolve_effects(d,context,target);break;
  case Ability::RandomMissiles:{const int missile_count=evaluate_spell_damage(context,d.damage);for(int n=0;n<missile_count;++n){std::vector<int> pool{hero_entity_id(1-owner)};for(const auto& m:state_.players[1-owner].board)if(m.health>0)pool.push_back(m.entity_id);int pick=pool[static_cast<std::size_t>(random_index(pool.size()))];spell_damage_dealt+=deal_damage(source_entity,pick,1,DamageKind::Spell,owner,false,DamageAttribution::DirectSpell);}break;}
  case Ability::None:throw UnsupportedSimulationError("vanilla/no-effect spell cannot be resolved as an effect spell");
  default:throw UnsupportedSimulationError("effect handler is not implemented for selected card");
 }
 (void)spell_damage_dealt; // Individual successful packets publish damage events.
 trace_event("EFFECT_END card="+d.card_id);
}
int GameSession::resolve_effects(const CardDefinition& d,const SpellEffectContext& context,int target){
 trace_event("EFFECT_BEGIN card="+d.card_id);int total_damage=0;
 const int owner=context.owner;
 const auto kind=is_spell(d)?DamageKind::Spell:DamageKind::Effect;
 bool previous_discard_succeeded=false;
 for(const auto& e:d.effects){if(e.requires_previous_discard&&!previous_discard_succeeded){previous_discard_succeeded=false;continue;}previous_discard_succeeded=false;switch(e.kind){
  case EffectKind::Damage:{
   const int amount=is_spell(d)?evaluate_spell_damage(context,e.amount):e.amount;
   std::vector<int> targets;
   if(e.target==TargetSelector::ExplicitCharacter||e.target==TargetSelector::ExplicitEnemyCharacter||e.target==TargetSelector::ExplicitMinion)targets.push_back(target);
   else if(e.target==TargetSelector::EnemyMinions||e.target==TargetSelector::EnemyCharacters){
    if(e.target==TargetSelector::EnemyCharacters)targets.push_back(hero_entity_id(1-owner));
    for(const auto& m:state_.players[1-owner].board)targets.push_back(m.entity_id);
   }else if(e.target==TargetSelector::RandomEnemyMinion){
    // Pending deaths can change the candidate set through removals/deathrattles.
    // Their boundary relative to random selection is not reviewed in v1.
    for(const auto& side:state_.players)for(const auto& m:side.board)if(m.health<=0){
     state_.unsupported="damage-boundary v1: pending board death before random minion selection";
     throw UnsupportedSimulationError(*state_.unsupported);
    }
    for(const auto& m:state_.players[1-owner].board)if(m.health>0)targets.push_back(m.entity_id);
    if(!targets.empty()){const int picked=targets[static_cast<std::size_t>(random_index(targets.size()))];targets={picked};}
   }else if(e.target==TargetSelector::AllCharacters){
    targets={hero_entity_id(0),hero_entity_id(1)};for(const auto& side:state_.players)for(const auto& m:side.board)targets.push_back(m.entity_id);
   }else if(e.target==TargetSelector::AllMinions){
    for(const auto& side:state_.players)for(const auto& m:side.board)if(m.health>0)targets.push_back(m.entity_id);
   }else if(e.target==TargetSelector::SelfHero){
    targets.push_back(hero_entity_id(owner));
   }else throw UnsupportedSimulationError("invalid selector for Damage effect");
   // One area instruction uses one evaluated amount for all its packets.
   for(int id:targets)total_damage+=deal_damage(context.source_entity,id,amount,kind,owner,e.lifesteal,is_spell(d)?DamageAttribution::DirectSpell:DamageAttribution::None);
   if(d.damage_outcome_condition!=DamageOutcomeCondition::None){if(targets.size()!=1||targets.front()!=target)throw UnsupportedSimulationError("damage outcome v1 requires exactly the selected minion target");int current_health=0;int target_owner=-1;bool found=false;for(const auto& side:state_.players)for(const auto& minion:side.board)if(minion.entity_id==target){current_health=minion.health;target_owner=minion.owner;found=true;}if(!found)throw UnsupportedSimulationError("damage outcome target left the board before its outcome check");const bool condition_met=d.damage_outcome_condition==DamageOutcomeCondition::Always||(d.damage_outcome_condition==DamageOutcomeCondition::MortallyWounded?current_health<=0:current_health>0);trace_event(std::string("DAMAGE_OUTCOME condition=")+(condition_met?"MET":"NOT_MET")+" target="+std::to_string(target)+" health="+std::to_string(current_health));if(condition_met){if(d.damage_outcome_followup==DamageOutcomeFollowup::DrawSelf)draw(owner,1);else if(d.damage_outcome_followup==DamageOutcomeFollowup::HealEnemyHero){auto& enemy_hero=state_.players[1-owner].hero_health;enemy_hero=std::min(30,enemy_hero+d.damage_outcome_amount);}else if(d.damage_outcome_followup==DamageOutcomeFollowup::DrawTargetOwner){if(target_owner<0||target_owner>=2)throw UnsupportedSimulationError("target owner is outside the two-player session");draw(target_owner,1);}trace_event("DAMAGE_OUTCOME_FOLLOWUP applied");}}
   break;
  }
  case EffectKind::Draw:draw(owner,e.amount);break;
  case EffectKind::GainArmor:state_.players[owner].armor+=e.amount;break;
  case EffectKind::ModifyHeroAttack:state_.players[owner].hero_temp_attack+=e.amount;recompute_hero_attack(owner);break;
  case EffectKind::Freeze:freeze_character(target);break;
  case EffectKind::SummonFixed:{int count=e.amount;if(e.summon_condition==SummonCondition::HoldingDragon){const auto& hand=state_.players[owner].hand;const bool holding_dragon=std::any_of(hand.begin(),hand.end(),[&](const auto& held){const auto& types=card(held.card_id).minion_types;return std::find(types.begin(),types.end(),"DRAGON")!=types.end();});if(holding_dragon)count+=e.conditional_extra_count;}summon_fixed(owner,e.summon_card,count);break;}
  case EffectKind::BuffFriendlyMinions:{for(auto& minion:state_.players[owner].board)if(minion.health>0){minion.attack+=e.amount;minion.health+=e.amount;minion.max_health+=e.amount;}trace_event("FRIENDLY_MINIONS_BUFF amount="+std::to_string(e.amount));break;}
  case EffectKind::DiscardRandomSpell:{std::vector<std::size_t> candidates;const auto& hand=state_.players[owner].hand;for(std::size_t i=0;i<hand.size();++i){const auto& definition=card(hand[i].card_id);const bool school_matches=e.discard_school==DiscardSpellSchool::Nature?definition.spell_school=="NATURE":definition.spell_school=="FIRE";if(is_spell(definition)&&school_matches)candidates.push_back(i);}if(!candidates.empty()){const auto selected=candidates[bounded_random(candidates.size())];const auto& discarded_definition=card(hand[selected].card_id);if(std::any_of(discarded_definition.required_mechanics.begin(),discarded_definition.required_mechanics.end(),[](const auto& mechanic){return mechanic=="INVISIBLEDEATHRATTLE"||mechanic=="DISCARD_TRIGGER";}))throw UnsupportedSimulationError("selected discarded spell has an unsupported discard trigger");CardInstance discarded=std::move(state_.players[owner].hand[selected]);state_.players[owner].hand.erase(state_.players[owner].hand.begin()+static_cast<std::ptrdiff_t>(selected));move_to_graveyard(owner,std::move(discarded));update_zone_positions(owner,Zone::Hand);previous_discard_succeeded=true;trace_event("RANDOM_SPELL_DISCARDED school="+(e.discard_school==DiscardSpellSchool::Nature?std::string("NATURE"):std::string("FIRE")));}else trace_event("RANDOM_SPELL_DISCARD_EMPTY");break;}
  case EffectKind::DestroyMinion:{if(e.target!=TargetSelector::ExplicitDamagedEnemyMinion&&e.target!=TargetSelector::ExplicitFriendlyMinion)throw UnsupportedSimulationError("DestroyMinion requires a side-constrained minion target");bool found=false;for(auto& side:state_.players)for(auto& minion:side.board)if(minion.entity_id==target){minion.health=0;found=true;}if(!found)throw UnsupportedSimulationError("DestroyMinion target is no longer on the board");trace_event("MINION_DESTROYED entity="+std::to_string(target));break;}
  case EffectKind::Heal:{if(e.target!=TargetSelector::ExplicitCharacter)throw UnsupportedSimulationError("Heal requires an explicit character target");if(target==hero_entity_id(0)||target==hero_entity_id(1)){auto& health=state_.players[owner_from_hero_id(target)].hero_health;health=std::min(30,health+e.amount);}else{bool found=false;for(auto& side:state_.players)for(auto& minion:side.board)if(minion.entity_id==target){if(minion.health<=0)throw UnsupportedSimulationError("cannot heal a minion already pending death");minion.health=std::min(minion.max_health,minion.health+e.amount);found=true;}if(!found)throw UnsupportedSimulationError("Heal target is no longer a character");}break;}
  case EffectKind::HealMinionToFull:{if(e.target!=TargetSelector::ExplicitMinion)throw UnsupportedSimulationError("HealMinionToFull requires an explicit minion target");bool found=false;for(auto& side:state_.players)for(auto& minion:side.board)if(minion.entity_id==target){if(minion.health<=0)throw UnsupportedSimulationError("cannot heal a minion already pending death");minion.health=minion.max_health;found=true;}if(!found)throw UnsupportedSimulationError("HealMinionToFull target is no longer a minion");break;}
 }}trace_event("EFFECT_END card="+d.card_id);return total_damage;
}
void GameSession::record_spell_damage_event(int owner,int amount){if(amount<=0)return;for(auto& source:state_.players[owner].board){const auto& definition=card(source.card_id);if(source.silenced||ability_of(definition)!=Ability::SpellDamageGainsAttack||source.counters["spell_damage_attack_turn"]==state_.turn_number)continue;source.counters["spell_damage_attack_turn"]=state_.turn_number;source.attack+=definition.spell_damage_attack;trace_event("SPELL_DAMAGE_TRIGGER card="+source.card_id+" entity="+std::to_string(source.entity_id)+" attack="+std::to_string(source.attack));}}
void GameSession::resolve_play(int index,int target){
 auto& p=state_.players[state_.active];
 const auto& held=p.hand.at(static_cast<std::size_t>(index));if(card(held.card_id).kindred_copy_contract=="INSTANCE_COPY_V1")validate_instance_copy_v1(held,state_.active,Zone::Hand);CardInstance instance=std::move(p.hand.at(static_cast<std::size_t>(index)));trace_event("ZONE_MOVE entity="+std::to_string(instance.entity_id)+" card="+instance.card_id+" from=HAND to=PLAY");
 const auto d=card(instance.card_id);p.mana-=effective_cost(state_.active,instance);
 p.hand.erase(p.hand.begin()+index);update_zone_positions(state_.active,Zone::Hand);update_shatter_links(state_.active);
 if(is_spell(d)&&p.spell_discount>0)p.spell_discount=0;
 if(is_minion(d)&&d.race=="DEMON"&&p.demon_discount>0)p.demon_discount=0;
 if(is_minion(d)){
  const int played_entity=instance.entity_id;
  instance.zone=Zone::Board;instance.controller=state_.active;instance.zone_position=static_cast<int>(p.board.size());
  instance.attack=d.attack;instance.health=d.health;instance.max_health=d.health;assign_activation_sequence(instance);instance.can_attack=d.rush;instance.rush=d.rush;instance.rush_only=d.rush;instance.lifesteal=d.lifesteal;instance.has_attacked_this_turn=false;p.board.push_back(std::move(instance));
  record_minion_play(state_.active,d);if(d.kindred_copy_contract=="INSTANCE_COPY_V1"&&kindred_qualified(state_.active,d))summon_instance_copy_v1(state_.active,played_entity);auto a=ability_of(d);if(a==Ability::DestroyEnemyWeapon||a==Ability::NextDemonDiscount||a==Ability::RecruiterSummonRush||a==Ability::CastRandomSecrets||a==Ability::SpellDamageHandDeck||(a==Ability::EffectComposition&&!d.effects.empty()))state_.triggers.push_back({TriggerKind::Battlecry,state_.active,played_entity,d.card_id,target});
  state_.triggers.push_back({TriggerKind::SecretWindow,state_.active,played_entity,d.card_id,played_entity,EventWindow::OpponentPlaysMinion});update_zone_positions(state_.active,Zone::Board);
 } else if(is_weapon(d)){
  if(p.weapon)move_to_graveyard(state_.active,std::move(*p.weapon));instance.zone=Zone::Weapon;instance.controller=state_.active;instance.zone_position=0;p.weapon=std::move(instance);recompute_hero_attack(state_.active);
 } else if(is_spell(d)){
  update_held_card_spell_progress(state_.active);++p.spells_cast_this_turn;
  const bool countered=resolve_secret_window(EventWindow::OpponentCastsSpell,state_.active);
  if(!countered){if(is_secret(d))activate_secret(std::move(instance));else if(ability_of(d)==Ability::ReinforcementAura){TimedEffect effect{d.card_id,d.duration>0?d.duration:3,d.pool_max_cost>0?d.pool_max_cost:2,d.pool_count>0?d.pool_count:1};effect.activation_sequence=state_.next_event_sequence++;p.timed_effects.push_back(std::move(effect));}else resolve_spell(d,state_.active,target,instance.spell_damage_bonus,instance.entity_id);}
  if(!is_secret(d)||countered)move_to_graveyard(state_.active,std::move(instance));
 } else throw UnsupportedSimulationError("unsupported card type selected for play");
 stabilize();
}
bool GameSession::resolve_secret_instance(int secret_owner,int entity_id,EventWindow window,int subject){
 auto& secrets=state_.players[secret_owner].secrets;
 auto found=std::find_if(secrets.begin(),secrets.end(),[&](const auto& s){return s.entity_id==entity_id;});
 if(found==secrets.end())return false;
 const auto d=card(found->card_id);
 const std::string trigger=d.secret_trigger;
 if(secret_window_of(trigger)!=window)return false;
 // Recheck eligibility before consuming a Secret: earlier reactions may remove its subject.
 const auto effect=secret_effect_of(d);
 const auto& enemy=state_.players[1-secret_owner].board;
 if(effect==SecretEffect::FlamesOfInfinity&&std::none_of(enemy.begin(),enemy.end(),[](const auto& m){return m.health>0;}))return false;
 if((effect==SecretEffect::ExplosiveRunes||effect==SecretEffect::MysticMisdirection)&&std::none_of(enemy.begin(),enemy.end(),[&](const auto& m){return m.entity_id==subject&&m.health>0;}))return false;
 CardInstance secret=std::move(*found);secrets.erase(found);for(std::size_t i=0;i<secrets.size();++i)secrets[i].zone_position=static_cast<int>(i);
 move_to_graveyard(secret_owner,std::move(secret));trace_event("SECRET_RESOLVE card="+d.card_id+" window="+trigger);
 if(secret_effect_of(d)==SecretEffect::Counterspell)return true;
 if(secret_effect_of(d)==SecretEffect::IceBarrier){state_.players[secret_owner].armor+=8;return false;}
 if(secret_effect_of(d)==SecretEffect::EnemyAreaDamage){for(const auto& source:state_.players[secret_owner].board){const auto& source_def=card(source.card_id);if(source.health<=0&&!source.silenced&&(source_def.spell_damage>0||source_def.damaged_spell_damage>0)){state_.unsupported="enemy-area Secret damage: unresolved pending Spell Damage source at trigger";throw UnsupportedSimulationError(*state_.unsupported);}}const auto amount=d.damage+spell_damage_for(secret_owner);std::vector<int> targets{hero_entity_id(1-secret_owner)};for(const auto& minion:state_.players[1-secret_owner].board)if(minion.health>0)targets.push_back(minion.entity_id);for(const int enemy:targets)deal_damage(entity_id,enemy,amount,DamageKind::Spell,secret_owner,false,DamageAttribution::DirectSpell);return false;}
 if(secret_effect_of(d)==SecretEffect::OasisAlly){
  if(state_.players[secret_owner].board.size()<7){if(card("CORE_CS2_033").support_state=="UNSUPPORTED"){state_.unsupported="Oasis Ally requires unsupported Water Elemental Freeze-on-damage";throw UnsupportedSimulationError(*state_.unsupported);}auto elemental=make_instance("CORE_CS2_033",secret_owner,Zone::Board,"SECRET");assign_activation_sequence(elemental);elemental.can_attack=false;state_.players[secret_owner].board.push_back(std::move(elemental));update_zone_positions(secret_owner,Zone::Board);}return false;
 }
 if(secret_effect_of(d)==SecretEffect::MysticMisdirection){
  auto& enemy=state_.players[1-secret_owner].board;auto attacker=std::find_if(enemy.begin(),enemy.end(),[&](const auto& m){return m.entity_id==subject;});
  if(attacker!=enemy.end()){transform_board(1-secret_owner,subject,"CS2_tk1");trace_event("SECRET_TRANSFORM entity="+std::to_string(subject)+" token=CS2_tk1");return true;}
  return false;
 }
 if(secret_effect_of(d)==SecretEffect::ExplosiveRunes){
  auto& enemy=state_.players[1-secret_owner].board;auto target=std::find_if(enemy.begin(),enemy.end(),[&](const auto& m){return m.entity_id==subject;});
  if(target!=enemy.end()&&target->health>0){const int excess=std::max(0,6-target->health);deal_damage(entity_id,subject,6,DamageKind::Spell,secret_owner,false,DamageAttribution::DirectSpell);if(excess>0)deal_damage(entity_id,hero_entity_id(1-secret_owner),excess,DamageKind::Spell,secret_owner,false,DamageAttribution::DirectSpell);}return false;
 }
 if(secret_effect_of(d)==SecretEffect::FlamesOfInfinity){
  auto& enemy=state_.players[1-secret_owner].board;std::vector<int> targets;int highest=0;for(const auto& minion:enemy)if(minion.health>0){if(minion.health>highest){highest=minion.health;targets.clear();}if(minion.health==highest)targets.push_back(minion.entity_id);}if(!targets.empty())deal_damage(entity_id,targets[bounded_random(targets.size())],2147483647,DamageKind::Spell,secret_owner);return false;
 }
 throw std::logic_error("unreachable configured Secret effect: "+d.secret_effect);
}
bool GameSession::resolve_secret_window(EventWindow window,int event_owner,int subject){
 const int secret_owner=1-event_owner;auto& secrets=state_.players[secret_owner].secrets;std::vector<std::pair<std::uint64_t,int>> eligible;

 for(const auto& secret:secrets)if(secret_window_of(card(secret.card_id).secret_trigger)==window)eligible.emplace_back(secret.activation_sequence,secret.entity_id);
 std::sort(eligible.begin(),eligible.end());for(const auto& [sequence,id]:eligible){(void)sequence;if(resolve_secret_instance(secret_owner,id,window,subject))return true;}return false;
}
bool GameSession::resolve_attack_secret_windows(int attacker_owner,int attacker_entity_id,bool hero_attack,int target){
 const int defender=1-attacker_owner;std::vector<std::pair<std::uint64_t,std::pair<int,EventWindow>>> eligible;const bool target_is_hero=target==hero_entity_id(defender);
 for(const auto& secret:state_.players[defender].secrets){const auto trigger=secret_window_of(card(secret.card_id).secret_trigger);EventWindow window;
  if(target_is_hero&&trigger==EventWindow::FriendlyHeroAttacked)window=EventWindow::FriendlyHeroAttacked;
  else if(!target_is_hero&&trigger==EventWindow::FriendlyMinionAttacked)window=EventWindow::FriendlyMinionAttacked;
  else if(!hero_attack&&trigger==EventWindow::EnemyMinionAttacks)window=EventWindow::EnemyMinionAttacks;
  else continue;eligible.emplace_back(secret.activation_sequence,std::make_pair(secret.entity_id,window));}
 std::sort(eligible.begin(),eligible.end(),[](const auto& a,const auto& b){return a.first<b.first;});for(const auto& item:eligible)if(resolve_secret_instance(defender,item.second.first,item.second.second,item.second.second==EventWindow::EnemyMinionAttacks?attacker_entity_id:target))return true;return false;
}
void GameSession::resolve_end_turn_reactions(int owner){
 struct Reaction{std::uint64_t sequence;int kind;int entity;std::string card;};std::vector<Reaction> reactions;
 for(const auto& m:state_.players[owner].board){const auto a=ability_of(card(m.card_id));if(a==Ability::EndTurnEnemyAreaDamage||a==Ability::EndTurnEnemyHeroDamage)reactions.push_back({m.activation_sequence,0,m.entity_id,m.card_id});}
 for(const auto& effect:state_.players[owner].timed_effects)reactions.push_back({effect.activation_sequence,1,0,effect.card_id});
 for(const auto& secret:state_.players[1-owner].secrets)if(secret_window_of(card(secret.card_id).secret_trigger)==EventWindow::OpponentTurnEnds)reactions.push_back({secret.activation_sequence,2,secret.entity_id,secret.card_id});
 std::stable_sort(reactions.begin(),reactions.end(),[](const auto& a,const auto& b){return a.sequence<b.sequence;});
 for(const auto& reaction:reactions){if(reaction.kind==0){auto& board=state_.players[owner].board;auto source=std::find_if(board.begin(),board.end(),[&](const auto& m){return m.entity_id==reaction.entity;});if(source==board.end()||source->health<=0)continue;const auto d=card(source->card_id);if(ability_of(d)==Ability::EndTurnEnemyAreaDamage){auto enemies=state_.players[1-owner].board;for(const auto& e:enemies)if(e.health>0)deal_damage(source->entity_id,e.entity_id,d.damage,DamageKind::Effect,owner);deal_damage(source->entity_id,hero_entity_id(1-owner),d.damage,DamageKind::Effect,owner);}else if(ability_of(d)==Ability::EndTurnEnemyHeroDamage)deal_damage(source->entity_id,hero_entity_id(1-owner),d.damage,DamageKind::Effect,owner);trace_event("END_TURN_REACTION card="+d.card_id+" sequence="+std::to_string(reaction.sequence));}
  else if(reaction.kind==1){auto& effects=state_.players[owner].timed_effects;auto effect=std::find_if(effects.begin(),effects.end(),[&](const auto& x){return x.activation_sequence==reaction.sequence;});if(effect==effects.end())continue;summon_from_deck(owner,effect->max_cost,effect->count,false);if(--effect->turns_remaining<=0)effects.erase(effect);}
  else resolve_secret_instance(1-owner,reaction.entity,EventWindow::OpponentTurnEnds,-1);
 }
}
void GameSession::resolve_trigger(const Trigger& t){int owner=t.owner;trace_event(std::string(t.kind==TriggerKind::Deathrattle?"DEATHRATTLE":"TRIGGER_RESOLVE")+" card="+t.card_id+" entity="+std::to_string(t.entity_id));
 if(t.kind==TriggerKind::SecretWindow){resolve_secret_window(t.window,owner,t.target_entity_id);return;}
 if(t.kind==TriggerKind::Battlecry&&ability_of(card(t.card_id))==Ability::SpellDamageHandDeck){const auto& d=card(t.card_id);auto& player=state_.players[owner];auto grant=[&](auto& zone){for(auto& instance:zone)if(is_spell(card(instance.card_id)))instance.spell_damage_bonus+=d.spell_damage_grant;};grant(player.hand);grant(player.deck);return;}
if(t.kind==TriggerKind::Battlecry){const auto& d=card(t.card_id);switch(ability_of(d)){case Ability::CastRandomSecrets:{if(state_.players[owner].spells_cast_this_turn>0){std::vector<std::string> pool;for(const auto& [id,candidate]:*catalog_->definitions_)if(candidate.collectible&&candidate.card_class=="MAGE"&&candidate.secret)pool.push_back(id);std::sort(pool.begin(),pool.end());auto expected=d.reviewed_random_secret_pool;std::sort(expected.begin(),expected.end());if(expected.empty()||pool!=expected)throw UnsupportedSimulationError("random Secret predicate does not match the reviewed pinned membership");for(int n=0;n<d.random_cast_count;++n){const auto& id=pool[static_cast<std::size_t>(random_index(pool.size()))];const auto& secret_def=card(id);if(secret_def.support_state=="UNSUPPORTED"){state_.unsupported="random Mage Secret outcome is unsupported: "+id;throw UnsupportedSimulationError(*state_.unsupported);}++state_.players[owner].spells_cast_this_turn;const bool countered=resolve_secret_window(EventWindow::OpponentCastsSpell,owner);if(!countered)activate_secret(make_instance(id,owner,Zone::Secret,"CAST_RANDOM"));}}break;}case Ability::DestroyEnemyWeapon:{auto& foe=state_.players[1-owner];if(foe.weapon){auto destroyed=std::move(*foe.weapon);foe.weapon.reset();move_to_graveyard(1-owner,std::move(destroyed));recompute_hero_attack(1-owner);}break;}case Ability::NextDemonDiscount:state_.players[owner].demon_discount=std::max(2,state_.players[owner].demon_discount);break;case Ability::RecruiterSummonRush:summon_from_deck(owner,d.pool_max_cost>0?d.pool_max_cost:2,d.pool_count>0?d.pool_count:2,true);break;case Ability::EffectComposition:resolve_effects(d,SpellEffectContext{owner,t.entity_id,0,DamageEvaluationContract::CurrentAtStep},t.target_entity_id);break;default:throw UnsupportedSimulationError("missing Battlecry handler for supported card");}return;}
 if(t.kind==TriggerKind::Deathrattle){const auto& d=card(t.card_id);if(ability_of(d)==Ability::DeathrattleGenerate&&!d.generated_card.empty()&&state_.players[owner].hand.size()<10){auto generated=make_instance(d.generated_card,owner,Zone::Hand,"GENERATED");if(card(d.generated_card).support_state=="UNSUPPORTED"&&!state_.unsupported)state_.unsupported="deathrattle generated an unsupported card outcome; simulation branch invalid";enter_hand(owner,std::move(generated));}else if(ability_of(d)==Ability::DeathrattleDraw)draw_from_deck(owner,d.deathrattle_draw_count,d.deck_draw_filter);return;}
 if(t.kind==TriggerKind::AfterHeroAttack){auto board=state_.players[owner].board;for(const auto& m:board)if(ability_of(card(m.card_id))==Ability::HeroAttackDraw)draw(owner);return;}
 if(t.kind==TriggerKind::EndTurn){resolve_end_turn_reactions(owner);return;}
}
void GameSession::stabilize(){
 for(;;){
  while(!state_.triggers.empty()){auto t=state_.triggers.front();state_.triggers.pop_front();resolve_trigger(t);}
  struct Death{int owner;CardInstance instance;};std::vector<Death> deaths;
  for(int owner=0;owner<2;++owner){auto& board=state_.players[owner].board;for(auto i=board.begin();i!=board.end();){if(i->health>0){++i;continue;}deaths.push_back({owner,std::move(*i)});i=board.erase(i);}update_zone_positions(owner,Zone::Board);}
  std::stable_sort(deaths.begin(),deaths.end(),[](const auto& a,const auto& b){return a.instance.activation_sequence<b.instance.activation_sequence;});
  for(auto& death:deaths){auto& dead=death.instance;trace_event("DEATH entity="+std::to_string(dead.entity_id)+" card="+dead.card_id);const auto ability=ability_of(card(dead.card_id));if(!dead.silenced&&(ability==Ability::DeathrattleGenerate||ability==Ability::DeathrattleDraw))state_.deathrattles.push_back({TriggerKind::Deathrattle,death.owner,dead.entity_id,dead.card_id});move_to_graveyard(death.owner,std::move(dead));}
  while(!state_.deathrattles.empty()){auto t=state_.deathrattles.front();state_.deathrattles.pop_front();resolve_trigger(t);}
  if(deaths.empty()&&state_.triggers.empty()&&state_.deathrattles.empty())break;
 }
 update_result();
}
void GameSession::apply_action(const Action& a){auto legal=legal_actions();if(std::none_of(legal.begin(),legal.end(),[&](const Action& candidate){return candidate.execution_equal(a);}))throw std::invalid_argument("action is not legal in the current position");
 trace_event(std::string("ACTION type=")+trace_action_name(a.type)+(a.card_id.empty()?std::string{}:" card="+a.card_id));
 if(a.type==ActionType::ChooseCard){auto choice=*state_.pending_choice;if(choice.continuation==ContinuationKind::AddSelectedCardToHand){const auto& card_id=choice.card_options.at(static_cast<std::size_t>(a.choice_index));trace_event("CHOICE_RESOLVE card="+card_id);const auto& selected=card(card_id);if(selected.support_state=="UNSUPPORTED"){state_.unsupported="Discover selected unsupported outcome "+card_id+"; simulation branch invalid";throw UnsupportedSimulationError(*state_.unsupported);}auto instance=make_instance(card_id,choice.owner,Zone::Hand,"DISCOVERED");instance.cost_delta+=choice.choice_cost_delta;enter_hand(choice.owner,std::move(instance));}else{int id=choice.options.at(static_cast<std::size_t>(a.choice_index));trace_event("CHOICE_RESOLVE entity="+std::to_string(id));for(auto& m:state_.players[choice.owner].board)if(m.entity_id==id){++m.attack;++m.health;++m.max_health;}}state_.pending_choice.reset();stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
  if(a.type==ActionType::PrepareCard){auto& player=state_.players[state_.active];auto& prepared=player.hand.at(static_cast<std::size_t>(a.hand_index));const int spend=std::min(player.mana,std::max(1,effective_cost(state_.active,prepared)-1));if(spend<1)throw std::logic_error("Prepare action was advertised without spendable mana");trace_event("PREPARE card="+prepared.card_id+" hand_position="+std::to_string(a.hand_index)+" mana_spent="+std::to_string(spend)+" reduction="+std::to_string(spend+1));player.mana-=spend;prepared.cost_delta-=spend+1;prepared.prepare_locked_turn=state_.turn_number;return;}
 if(a.type==ActionType::PlayCard){resolve_play(a.hand_index,a.target_entity_id);if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::Attack){int owner=state_.active;bool hero=a.attacker_entity_id==hero_entity_id(owner);int attack=0;bool attacker_lifesteal=false;if(hero){auto& p=state_.players[owner];attack=p.hero_attack;p.hero_attacked=true;if(p.weapon){--p.weapon->durability;if(p.weapon->durability<=0){auto broken=std::move(*p.weapon);p.weapon.reset();move_to_graveyard(owner,std::move(broken));}else p.weapon->current_durability=p.weapon->durability;}recompute_hero_attack(owner);}else for(auto& m:state_.players[owner].board)if(m.entity_id==a.attacker_entity_id){attack=m.attack;attacker_lifesteal=m.lifesteal;m.can_attack=false;m.has_attacked_this_turn=true;}
  if(resolve_attack_secret_windows(owner,a.attacker_entity_id,hero,a.target_entity_id)){stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
  if(hero){if(state_.players[owner].hero_health<=0){stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}}
  else{const auto& board=state_.players[owner].board;const auto attacker=std::find_if(board.begin(),board.end(),[&](const auto& minion){return minion.entity_id==a.attacker_entity_id&&minion.health>0;});if(attacker==board.end()){stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}}
  int retaliation=0;bool defender_lifesteal=false;
  if(a.target_entity_id!=hero_entity_id(1-owner))for(const auto& m:state_.players[1-owner].board)if(m.entity_id==a.target_entity_id){retaliation=m.attack;defender_lifesteal=m.lifesteal;}
  deal_damage(a.attacker_entity_id,a.target_entity_id,attack,DamageKind::Combat,owner,attacker_lifesteal);
  deal_damage(a.target_entity_id,a.attacker_entity_id,retaliation,DamageKind::Combat,1-owner,defender_lifesteal);
  if(hero)state_.players[owner].hero_attacked=true;if(hero)state_.triggers.push_back({TriggerKind::AfterHeroAttack,owner});stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::HeroPower){auto& p=state_.players[state_.active];p.mana-=2;p.hero_power_used_this_turn=true;deal_damage(hero_entity_id(state_.active),a.target_entity_id,1,DamageKind::HeroPower,state_.active);stabilize();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);return;}
 if(a.type==ActionType::EndTurn){int ending=state_.active;state_.triggers.push_back({TriggerKind::EndTurn,ending});stabilize();if(state_.result)return;auto& old=state_.players[ending];old.previous_turn_minion_types_played=std::move(old.current_turn_minion_types_played);old.current_turn_minion_types_played.clear();old.hero_temp_attack=0;old.hero_attack=0;old.hero_attacked=false;old.spell_discount=0;if(old.hero_frozen&&old.turns_started>=old.hero_freeze_expire_turn){old.hero_frozen=false;old.hero_freeze_expire_turn=0;}for(auto& m:old.board)if(m.frozen&&old.turns_started>=m.freeze_expire_owner_turn){m.frozen=false;m.freeze_expire_owner_turn=0;}for(auto& player:state_.players)player.spell_damage_dealt_this_turn=0;state_.active=1-ending;++state_.turn_number;auto& next=state_.players[state_.active];next.spells_cast_this_turn=0;++next.turns_started;next.max_mana=std::min(10,next.max_mana+1);next.mana=next.max_mana;next.hero_attacked=false;next.hero_power_used_this_turn=false;for(auto& m:next.board){m.can_attack=!m.frozen;m.rush_only=false;m.has_attacked_this_turn=false;}recompute_hero_attack(state_.active);draw(state_.active);update_result();if(state_.unsupported)throw UnsupportedSimulationError(*state_.unsupported);}
}
bool GameSession::is_complete()const{return state_.result.has_value();}
void GameSession::validate_invariants()const{
 std::unordered_set<int> ids;
 auto check_zone=[&](int owner,Zone expected,const std::vector<CardInstance>& cards){for(std::size_t i=0;i<cards.size();++i){const auto& c=cards[i];if(!ids.insert(c.entity_id).second)throw std::logic_error("duplicate entity instance ID");if(c.owner<0||c.owner>1||c.controller!=owner||c.zone!=expected||c.zone_position!=static_cast<int>(i))throw std::logic_error("entity zone ownership/position mismatch");if(c.prepare_locked_turn>state_.turn_number||(c.prepare_locked_turn>=0&&!card(c.card_id).prepare))throw std::logic_error("Prepare lock is inconsistent with the card or current turn");if(expected==Zone::Board&&c.health<=0)throw std::logic_error("dead entity remains targetable on board");if(expected==Zone::Hand){if(c.shatter_fragment==ShatterFragment::None){if(c.shatter_partner_entity_id!=-1||!c.shatter_original_card_id.empty())throw std::logic_error("unlinked hand card has Shatter metadata");}else{if(!c.shatter_consumed||c.shatter_original_card_id.empty())throw std::logic_error("Shatter fragment lacks source metadata");const auto& source=card(c.shatter_original_card_id);if(c.shatter_fragment==ShatterFragment::Solo){if(c.shatter_partner_entity_id!=-1||(c.card_id!=source.shatter_left_card&&c.card_id!=source.shatter_right_card))throw std::logic_error("solo Shatter fragment is inconsistent");}else{const auto partner=std::find_if(cards.begin(),cards.end(),[&](const auto& item){return item.entity_id==c.shatter_partner_entity_id;});if(partner==cards.end()||partner->shatter_original_card_id!=c.shatter_original_card_id||partner->shatter_partner_entity_id!=c.entity_id)throw std::logic_error("Shatter partner link is not reciprocal");const bool left=c.shatter_fragment==ShatterFragment::Left;if((left&&c.card_id!=source.shatter_left_card)||(!left&&c.card_id!=source.shatter_right_card)||partner->shatter_fragment!=(left?ShatterFragment::Right:ShatterFragment::Left))throw std::logic_error("Shatter fragment role does not match its source");}}}}};
 for(int p=0;p<2;++p){const auto& x=state_.players[p];if(x.hand.size()>10||x.board.size()>7)throw std::logic_error("zone capacity invariant violated");if(x.max_mana<0||x.max_mana>10||x.mana<0||x.mana>10)throw std::logic_error("mana invariant violated");check_zone(p,Zone::Deck,x.deck);check_zone(p,Zone::Hand,x.hand);check_zone(p,Zone::Board,x.board);check_zone(p,Zone::Secret,x.secrets);check_zone(p,Zone::Graveyard,x.graveyard);if(x.weapon){const auto& w=*x.weapon;if(!ids.insert(w.entity_id).second||w.zone!=Zone::Weapon||w.owner!=p||w.zone_position!=0)throw std::logic_error("weapon instance identity/zone invariant violated");}}
 std::unordered_set<std::uint64_t> sequences;for(const auto& player:state_.players){for(const auto& source:player.board)if(source.activation_sequence==0||source.activation_sequence>=state_.next_event_sequence||!sequences.insert(source.activation_sequence).second)throw std::logic_error("active board source activation sequence is invalid");for(const auto& source:player.secrets)if(source.activation_sequence==0||source.activation_sequence>=state_.next_event_sequence||!sequences.insert(source.activation_sequence).second)throw std::logic_error("active Secret activation sequence is invalid");for(const auto& source:player.timed_effects)if(source.activation_sequence==0||source.activation_sequence>=state_.next_event_sequence||!sequences.insert(source.activation_sequence).second)throw std::logic_error("active timed effect activation sequence is invalid");}if(state_.result&&!legal_actions().empty())throw std::logic_error("terminal state has gameplay actions");
}
bool GameSession::is_valid()const{return !state_.unsupported.has_value();}
std::optional<std::string> GameSession::unsupported_outcome()const{return state_.unsupported;}
std::optional<std::string> GameSession::result()const{return state_.result;}
bool GameSession::needs_choice()const{return state_.pending_choice.has_value();}
std::vector<int> GameSession::choice_options()const{return state_.pending_choice?state_.pending_choice->options:std::vector<int>{};}
std::unique_ptr<GameSession> GameSession::clone()const{return std::make_unique<GameSession>(*this);}
void GameSession::set_trace_enabled(bool enabled){state_.trace_enabled=enabled;if(!enabled)state_.trace.clear();}
const std::vector<std::string>& GameSession::diagnostic_trace()const{return state_.trace;}
std::uint64_t GameSession::seed()const{return seed_;}
void GameSession::begin_prototype_choice(int max_attack){if(state_.result||state_.pending_choice)throw std::logic_error("choice unavailable");PendingChoice p;p.owner=state_.active;for(const auto& m:state_.players[p.owner].board)if(m.attack<=max_attack)p.options.push_back(m.entity_id);if(p.options.empty())throw std::logic_error("state produced no choice candidates");state_.pending_choice=std::move(p);}
Observation GameSession::observation(int perspective)const{
 if(perspective<0||perspective>1)throw std::invalid_argument("perspective must be 0 or 1");
 const int other=1-perspective;Observation o;o.turn_number=state_.turn_number;o.active_player=state_.active==perspective?"SELF":"OPPONENT";
 auto base_card=[&](const std::string& id){const auto& d=card(id);ObservedCard x;x.card_id=d.card_id;x.card_type=d.card_type;x.card_class=d.card_class;x.race=d.race;x.cost=d.cost;x.attack=d.attack;x.health=d.health;x.durability=d.durability;x.lifesteal=d.lifesteal;return x;};
 auto convert=[&](int owner){const auto& p=state_.players[owner];ObservedPlayer x;x.current_turn_minion_types_played=p.current_turn_minion_types_played;x.previous_turn_minion_types_played=p.previous_turn_minion_types_played;x.player_class=p.player_class;x.hero_health=std::max(0,p.hero_health);x.armor=p.armor;x.hero_attack=p.hero_attack;x.max_mana=p.max_mana;x.available_mana=p.mana;x.deck_size=static_cast<int>(p.deck.size());x.hand_size=static_cast<int>(p.hand.size());x.fatigue=p.fatigue;x.secret_count=static_cast<int>(p.secrets.size());x.spell_damage=spell_damage_for(owner);x.hero_power_ready=p.player_class=="MAGE"&&!p.hero_power_used_this_turn;x.hero_frozen=p.hero_frozen;x.spells_cast_this_turn=p.spells_cast_this_turn;x.spell_discount=p.spell_discount;x.demon_discount=p.demon_discount;x.hero_freeze_turns_remaining=p.hero_frozen?std::max(0,p.hero_freeze_expire_turn-p.turns_started)+1:0;for(const auto& effect:p.timed_effects){auto item=base_card(effect.card_id);item.effect_turns_remaining=effect.turns_remaining;x.active_effects.push_back(std::move(item));}
  if(p.player_class=="MAGE"){auto hp=base_card("HERO_08bp");hp.card_type="HERO_POWER";hp.current_cost=2;hp.current_attack=0;hp.current_health=0;x.hero_power=hp;}
  if(p.weapon){auto w=base_card(p.weapon->card_id);w.current_cost=w.cost;w.current_attack=p.weapon->attack;w.current_health=p.weapon->health;w.current_durability=p.weapon->durability;x.weapon=w;}
  for(const auto& m:p.board){auto b=base_card(m.card_id);b.freeze_turns_remaining=m.frozen?std::max(0,m.freeze_expire_owner_turn-p.turns_started)+1:0;if(ability_of(card(m.card_id))==Ability::SpellDamageGainsAttack){const auto consumed=m.counters.find("spell_damage_attack_turn");b.trigger_remaining=consumed!=m.counters.end()&&consumed->second==state_.turn_number?0:1;}b.current_cost=b.cost;b.current_attack=m.attack;b.current_health=m.health;b.current_durability=m.durability;b.board_position=m.zone_position;b.entity_id=m.entity_id;b.can_attack=m.can_attack;b.rush=m.rush;b.frozen=m.frozen;b.taunt=m.taunt&&!m.silenced;b.divine_shield=m.divine_shield;b.lifesteal=m.lifesteal;b.stealth=m.stealth;b.silenced=m.silenced;b.immune=m.immune;b.max_health=m.max_health;x.board.push_back(std::move(b));}return x;};
 o.self_player=convert(perspective);o.opponent=convert(other);for(const auto& secret:state_.players[perspective].secrets)o.self_player.known_secrets.push_back(secret.card_id);
 for(const auto& h:state_.players[perspective].hand){auto item=base_card(h.card_id);item.prepare_used=h.prepare_locked_turn>=0;const auto progress=h.counters.find("held_spell_threshold");item.held_spell_progress=progress==h.counters.end()?0:progress->second;item.current_cost=effective_cost(perspective,h);item.current_spell_damage=h.spell_damage_bonus;item.entity_id=h.entity_id;item.shatter_original_card_id=h.shatter_original_card_id;item.prepare_locked=h.prepare_locked_turn==state_.turn_number;if(h.shatter_fragment==ShatterFragment::Left)item.shatter_fragment="LEFT";else if(h.shatter_fragment==ShatterFragment::Right)item.shatter_fragment="RIGHT";else if(h.shatter_fragment==ShatterFragment::Solo)item.shatter_fragment="SOLO";if(h.shatter_partner_entity_id>=0){auto partner=std::find_if(state_.players[perspective].hand.begin(),state_.players[perspective].hand.end(),[&](const auto& other){return other.entity_id==h.shatter_partner_entity_id;});if(partner!=state_.players[perspective].hand.end())item.shatter_partner_hand_position=partner->zone_position;}o.self_hand.push_back(std::move(item));}
 if(state_.pending_choice){const auto& choice=*state_.pending_choice;o.pending_choice_owner=choice.owner==perspective?"SELF":"OPPONENT";if(choice.owner==perspective){if(choice.continuation==ContinuationKind::AddSelectedCardToHand){for(const auto& id:choice.card_options){auto item=base_card(id);item.current_cost=std::max(0,item.cost+choice.choice_cost_delta);o.pending_choice_options.push_back(std::move(item));}}else for(int id:choice.options)for(const auto& m:state_.players[choice.owner].board)if(m.entity_id==id){auto item=base_card(m.card_id);item.current_attack=m.attack;item.current_health=m.health;item.board_position=m.zone_position;o.pending_choice_options.push_back(std::move(item));}}}
 o.self_hand_known_count=static_cast<int>(o.self_hand.size());return o;
}
void GameSession::update_result(){bool a=state_.players[0].hero_health<=0,b=state_.players[1].hero_health<=0;if(a&&b)state_.result="DRAW";else if(a)state_.result="PLAYER2_WIN";else if(b)state_.result="PLAYER1_WIN";}
} // namespace manaengine
