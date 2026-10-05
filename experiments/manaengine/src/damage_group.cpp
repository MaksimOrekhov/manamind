#include "manaengine/engine.hpp"
#include <algorithm>
#include <limits>
#include <unordered_set>

namespace manaengine {
namespace {
constexpr std::size_t max_damage_depth=64, max_damage_work=4096;
}
void GameSession::require_quiescent() const {
 if(state_.failure)/* NF-100:0 */ rethrow_stored();
 if(!state_.damage_frames.empty())/* NF-101:0 */ throw UnsupportedSimulationError(FailureCode::QUIESCENCE_VIOLATED, "damage group: public access requires quiescent state");
}
void GameSession::consume_damage_work(){
 if(++state_.damage_work>max_damage_work)/* NF-102:0 */ fail(FailureCode::DAMAGE_WORK_BUDGET_EXCEEDED, "damage group: action execution budget exhausted");
}
GameSession::EntityHandle GameSession::damage_target_handle(int target){
 const int hero=owner_from_hero_id(target);
 if(hero>=0&&hero<2)return {target,hero,0,{}};
 for(int owner=0;owner<2;++owner)for(const auto& m:state_.players[owner].board)if(m.entity_id==target){
  // Structural corruption is decisive even when ownership is also outside the reviewed boundary.
  if(m.activation_sequence==0)/* NF-103:0:structural */ fail(FailureCode::INVARIANT_VIOLATION, "damage group: target ownership/activation boundary");
  if(m.controller!=owner||m.owner!=owner)/* NF-103:0 */ fail(FailureCode::CONTROL_CHANGE_UNREVIEWED, "damage group: target ownership/activation boundary");
  return {target,owner,m.activation_sequence,m.card_id,m.silenced};
 }
 /* NF-104:0 */ fail(FailureCode::DAMAGE_TARGET_LOST, "damage group: target identity is not in Play");
}
GameSession::DamagePacketIntent GameSession::damage_intent(int source,int target,int amount,DamageKind kind,int controller,bool lifesteal,DamageAttribution attribution){
 return {source,controller,damage_target_handle(target),amount,kind,attribution,lifesteal};
}
// Only generation (SelfTakesDamageV1) is order-sensitive: it consumes RNG and fills a hand. The first-spell-damage
// attack gain touches neither, so a Raincaller reaction never needs an ordering contract by itself.
bool GameSession::has_self_damage_reaction(const DamagePacketIntent& packet) const {
 if(packet.amount<=0)return false;
 for(const auto& side:state_.players)for(const auto& m:side.board)if(m.entity_id==packet.target.entity_id){
  if(m.immune||m.divine_shield)return false;
  if(!m.silenced&&!card(m.card_id).takes_damage_pool_id.empty())return true;
 }
 return false;
}
void GameSession::guard_scalar_damage(const std::vector<DamagePacketIntent>& packets){
 for(const auto& packet:packets){
  if(packet.source_controller<0||packet.source_controller>1)/* NF-105:0 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: invalid scalar controller");
  if(has_self_damage_reaction(packet))/* NF-106:0 */ fail(FailureCode::DAMAGE_REACTION_ORDER_UNREVIEWED, "damage group: reactive combat/hero-area/compound ordering is not reviewed");
 }
}
void GameSession::guard_area_spell_modifiers(const std::vector<DamagePacketIntent>& packets){
 for(const auto& packet:packets)if(packet.kind==DamageKind::Spell&&packet.amount>0){
  for(const auto& m:state_.players[packet.source_controller].board)if(!m.silenced&&m.health<=0&&(card(m.card_id).spell_damage>0||card(m.card_id).damaged_spell_damage>0))
   /* NF-107:0 */ fail(FailureCode::SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED, "damage group: mortally wounded Spell Damage source before area");
  for(const auto& m:state_.players[packet.source_controller].board)if(m.entity_id==packet.target.entity_id&&!m.silenced&&!m.immune&&!m.divine_shield){
   const auto& d=card(m.card_id);
   // Static contribution stays captured for this instruction; deaths drain later.
   // Becoming damaged can activate a conditional contribution during creation.
   if(d.damaged_spell_damage>0&&m.health==m.max_health)
    /* NF-107:1 */ fail(FailureCode::SPELL_DAMAGE_SOURCE_BOUNDARY_UNREVIEWED, "damage group: conditional/mortal Spell Damage change inside area is not reviewed");
  }
 }
}
GameSession::PacketOutcome GameSession::apply_damage_packet(const DamagePacketIntent& packet){
 PacketOutcome out;out.intent=packet;
 if(packet.amount==0){out.prevention=Prevention::Zero;return out;}
 const int hero=owner_from_hero_id(packet.target.entity_id);
 if(hero>=0&&hero<2){
  auto& h=state_.players[hero];out.armor_delta=std::min(h.armor,packet.amount);h.armor-=static_cast<int>(out.armor_delta);
  const auto old=h.hero_health;h.hero_health=static_cast<int>(std::max<std::int64_t>(-2147483647LL,static_cast<std::int64_t>(old)-(packet.amount-out.armor_delta)));
  out.health_delta=static_cast<std::int64_t>(old)-h.hero_health;
 }else{
  bool found=false;
  for(auto& side:state_.players)for(auto& m:side.board)if(m.entity_id==packet.target.entity_id){
   found=true;
   if(m.immune){out.prevention=Prevention::Immune;return out;}
   if(m.divine_shield){m.divine_shield=false;out.prevention=Prevention::DivineShield;trace_event("DAMAGE_PREVENTED target="+std::to_string(m.entity_id));return out;}
   const int old=m.health;m.health=static_cast<int>(std::max<std::int64_t>(-2147483647LL,static_cast<std::int64_t>(old)-packet.amount));out.health_delta=static_cast<std::int64_t>(old)-m.health;
   const auto& d=card(m.card_id);
   if(out.health_delta>0&&!m.silenced&&!d.takes_damage_pool_id.empty())
    out.self_reaction=DamageReactionSnapshot{ReactionKind::SelfTakesDamageV1,packet.target,d.takes_damage_pool_id,d.takes_damage_cost_delta};
  }
  if(!found)/* NF-108:0 */ fail(FailureCode::DAMAGE_TARGET_LOST, "damage group: frozen target disappeared during mutation");
 }
 if(out.health_delta+out.armor_delta<=0)return out;
 out.reported_damage=packet.amount;out.event_sequence=state_.next_damage_sequence++;
 trace_event("DAMAGE source="+std::to_string(packet.source_entity)+" target="+std::to_string(packet.target.entity_id)+" amount="+std::to_string(packet.amount));
 if(packet.attribution==DamageAttribution::DirectSpell){
  auto& total=state_.players[packet.source_controller].spell_damage_dealt_this_turn;
  total+=std::min<std::int64_t>(out.reported_damage,std::numeric_limits<std::int64_t>::max()-total);
  trace_event("DIRECT_SPELL_DAMAGE_TURN controller="+std::to_string(packet.source_controller)+" total="+std::to_string(total));
 }
 // Reviewed scalar-only Lifesteal: fixed 30-health hero, no healing reactions.
 if(packet.lifesteal){auto& h=state_.players[packet.source_controller].hero_health;h=static_cast<int>(std::min<std::int64_t>(30,static_cast<std::int64_t>(h)+out.reported_damage));}
 return out;
}
std::size_t GameSession::open_damage_group(std::vector<DamagePacketIntent> packets,DamageDispatch dispatch,DamageEventOrder order){
 if(state_.failure)/* NF-109:0 */ rethrow_stored();
 if(state_.pending_choice)/* NF-110:0 */ fail(FailureCode::DAMAGE_REACTION_ORDER_UNREVIEWED, "damage group: active Choice/suspension is outside contract");
 if(state_.damage_frames.size()>=max_damage_depth)/* NF-111:0 */ fail(FailureCode::DAMAGE_DEPTH_BUDGET_EXCEEDED, "damage group: nested depth budget exhausted");
 if(dispatch!=DamageDispatch::ApplyAllThenReact&&dispatch!=DamageDispatch::SinglePacketThenReact)/* NF-112:0 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: unknown dispatch contract");
 if(order!=DamageEventOrder::MinionEntrySequence&&order!=DamageEventOrder::SingleTarget&&order!=DamageEventOrder::ScalarOnly)/* NF-112:1 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: unknown event order");
 if((dispatch==DamageDispatch::SinglePacketThenReact||order==DamageEventOrder::SingleTarget)&&packets.size()!=1)/* NF-112:2 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: single packet contract requires one target");
 if(packets.size()>max_damage_work||state_.damage_work>max_damage_work-packets.size())/* NF-113:0 */ fail(FailureCode::DAMAGE_PACKET_BUDGET_EXCEEDED, "damage group: packet buffer/action budget exhausted");
 if(state_.next_damage_group_id==std::numeric_limits<std::uint64_t>::max()||state_.next_damage_sequence>std::numeric_limits<std::uint64_t>::max()-packets.size())/* NF-114:0 */ fail(FailureCode::NUMERIC_RANGE_VIOLATION, "damage group: identity counter exhausted");
 std::unordered_set<int> targets;
 for(const auto& packet:packets){
  if(packet.source_controller<0||packet.source_controller>1||packet.amount<0||packet.source_entity< -1||packet.source_entity==0||packet.source_entity>=state_.next_entity_id)/* NF-115:0 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: invalid source/controller/amount");
  if(packet.kind!=DamageKind::Combat&&packet.kind!=DamageKind::Spell&&packet.kind!=DamageKind::Effect&&packet.kind!=DamageKind::HeroPower&&packet.kind!=DamageKind::Fatigue)/* NF-115:1 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: unknown damage kind");
  if(packet.attribution!=DamageAttribution::None&&packet.attribution!=DamageAttribution::DirectSpell&&packet.attribution!=DamageAttribution::ExternalSpellEffect)/* NF-115:2 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: unknown attribution");
  if(packet.attribution==DamageAttribution::DirectSpell&&packet.kind!=DamageKind::Spell)/* NF-115:3 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: DirectSpell requires Spell damage");
  const auto current=damage_target_handle(packet.target.entity_id);
  if(current.controller!=packet.target.controller||current.entry_sequence!=packet.target.entry_sequence||current.card_id!=packet.target.card_id||!targets.insert(current.entity_id).second)/* NF-115:4 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: duplicate or stale target");
  if(order==DamageEventOrder::MinionEntrySequence&&current.entry_sequence==0)/* NF-115:5 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: hero is outside minion-area order");
  const int source_hero=owner_from_hero_id(packet.source_entity);
  if(source_hero>=0&&source_hero<2&&source_hero!=packet.source_controller)/* NF-115:6 */ fail(FailureCode::INVALID_DAMAGE_PACKET, "damage group: source hero controller changed");
  for(const auto& side:state_.players)for(const auto& m:side.board)if(m.entity_id==packet.source_entity&&m.controller!=packet.source_controller)/* NF-116:0 */ fail(FailureCode::CONTROL_CHANGE_UNREVIEWED, "damage group: source controller changed");
 }
 if(order==DamageEventOrder::ScalarOnly)guard_scalar_damage(packets);
 if(dispatch==DamageDispatch::ApplyAllThenReact)guard_area_spell_modifiers(packets);
 if(order==DamageEventOrder::MinionEntrySequence)std::stable_sort(packets.begin(),packets.end(),[](const auto& a,const auto& b){return a.target.entry_sequence<b.target.entry_sequence;});
 DamageGroupFrame frame;frame.dispatch=dispatch;frame.order=order;frame.outcomes.reserve(packets.size());
 for(const auto& packet:packets)for(const auto& side:state_.players)for(const auto& m:side.board)if(m.entity_id==packet.source_entity)
  frame.board_sources.push_back({m.entity_id,m.controller,m.activation_sequence,m.card_id,m.silenced});
 frame.group_id=state_.next_damage_group_id++;frame.parent_group_id=state_.damage_frames.empty()?0:state_.damage_frames.back().group_id;
 const auto index=state_.damage_frames.size();state_.damage_frames.push_back(std::move(frame));
 try{
  for(const auto& packet:packets){consume_damage_work();auto result=apply_damage_packet(packet);state_.damage_frames[index].outcomes.push_back(std::move(result));}
  auto& current=state_.damage_frames[index];current.stage=DamageFrameStage::DispatchEvent;
  std::string marker="GROUP_MUTATIONS_COMPLETE group="+std::to_string(current.group_id)+" parent="+std::to_string(current.parent_group_id)+" events=";
  for(const auto& out:current.outcomes)if(out.event_sequence)marker+=std::to_string(out.event_sequence)+",";
  trace_event(std::move(marker));
 }/* NF-117:0 NF-117:1 */ catch(const UnsupportedSimulationError& e){state_.damage_frames.resize(index);record_failure(e.record());append_failure_context("damage_group.mutation depth="+std::to_string(index));rethrow_stored();}
 catch(...){state_.damage_frames.resize(index);append_failure_context("damage_group.mutation depth="+std::to_string(index));throw;}
 return index;
}
void GameSession::validate_damage_frame_sources(std::size_t index){
 for(const auto& source:/* NF-119:0 */ checked_at(state_.damage_frames, index, FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION).board_sources){
  const auto current=damage_target_handle(source.entity_id);
  if(current.controller!=source.controller||current.entry_sequence!=source.entry_sequence||current.card_id!=source.card_id||current.silenced!=source.silenced)
   /* NF-118:0 */ fail(FailureCode::DAMAGE_SOURCE_BOUNDARY_UNREVIEWED, "damage group: source lifetime/descriptor changed");
 }
}
void GameSession::dispatch_damage_event(std::size_t index){
 if(index+1!=state_.damage_frames.size())/* NF-120:0 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: child must finish before parent resumes");
 validate_damage_frame_sources(index);
 auto& frame=/* NF-119:1 */ checked_at(state_.damage_frames, index, FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION);
 if(frame.stage!=DamageFrameStage::DispatchEvent||frame.event_cursor>=frame.outcomes.size())/* NF-120:1 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: invalid event continuation");
 const PacketOutcome out=frame.outcomes[frame.event_cursor];frame.current_event_reactions.clear();frame.reaction_cursor=0;
 if(out.event_sequence){
  if(out.self_reaction)frame.current_event_reactions.push_back(*out.self_reaction);
  if(out.intent.kind==DamageKind::Spell)for(const auto& m:state_.players[out.intent.source_controller].board){
   const auto& d=card(m.card_id);const auto counter=m.counters.find("spell_damage_attack_turn");
   if(!m.silenced&&ability_of(d)==Ability::SpellDamageGainsAttack&&(counter==m.counters.end()||counter->second!=state_.turn_number))
    frame.current_event_reactions.push_back({ReactionKind::FirstSpellDamageAttackV1,{m.entity_id,m.controller,m.activation_sequence,m.card_id},{},d.spell_damage_attack});
  }
  // Generation and the Raincaller attack gain are independent; their relative order is unobservable.
  // The one unreviewed shape is the damaged consumer itself also being the first-spell-damage watcher.
  if(out.self_reaction)for(const auto& r:frame.current_event_reactions)if(r.kind==ReactionKind::FirstSpellDamageAttackV1&&r.consumer.entity_id==out.self_reaction->consumer.entity_id)
   /* NF-121:0 */ fail(FailureCode::DAMAGE_REACTION_ORDER_UNREVIEWED, "damage group: damaged consumer is also its own spell-damage watcher");
  std::stable_sort(frame.current_event_reactions.begin(),frame.current_event_reactions.end(),[](const auto& a,const auto& b){return a.consumer.entry_sequence<b.consumer.entry_sequence;});
 }
 frame.stage=DamageFrameStage::DispatchReaction;
 while(state_.damage_frames[index].reaction_cursor<state_.damage_frames[index].current_event_reactions.size()){
  consume_damage_work();const auto reaction=state_.damage_frames[index].current_event_reactions[state_.damage_frames[index].reaction_cursor];
  if(reaction.kind==ReactionKind::SelfTakesDamageV1){
   const auto current=damage_target_handle(reaction.consumer.entity_id);
   if(current.card_id!=reaction.consumer.card_id)/* NF-122:0 */ fail(FailureCode::DAMAGE_SOURCE_BOUNDARY_UNREVIEWED, "damage group: consumer descriptor changed");
   DamageOccurrence occurrence;occurrence.damage_source_entity_id=out.intent.source_entity;occurrence.damaged_entity_id=reaction.consumer.entity_id;occurrence.damaged_controller=reaction.consumer.controller;occurrence.damage_kind=out.intent.kind;occurrence.attribution=out.intent.attribution;occurrence.packet_amount=out.reported_damage;occurrence.actual_health_delta=out.health_delta;occurrence.damage_group_id=state_.damage_frames[index].group_id;occurrence.sequence=out.event_sequence;occurrence.consumer_activation_sequence=reaction.consumer.entry_sequence;occurrence.captured_pool_id=reaction.pool_id;occurrence.captured_cost_delta=reaction.value;
   resolve_damage_occurrence(occurrence);
  }else{
   bool found=false;
   for(auto& side:state_.players)for(auto& m:side.board)if(m.entity_id==reaction.consumer.entity_id){
    found=true;
    if(m.controller!=reaction.consumer.controller||m.activation_sequence!=reaction.consumer.entry_sequence||m.card_id!=reaction.consumer.card_id||m.silenced)/* NF-122:1 */ fail(FailureCode::DAMAGE_SOURCE_BOUNDARY_UNREVIEWED, "damage group: spell reaction lifetime/descriptor changed");
    if(card(m.card_id).spell_damage_attack!=reaction.value)/* NF-122:1:structural */ fail(FailureCode::INVARIANT_VIOLATION, "damage group: spell reaction lifetime/descriptor changed");
    m.counters["spell_damage_attack_turn"]=state_.turn_number;
    const auto attack=static_cast<std::int64_t>(m.attack)+reaction.value;
    if(attack>std::numeric_limits<int>::max()||attack<std::numeric_limits<int>::min())/* NF-123:0 */ fail(FailureCode::NUMERIC_RANGE_VIOLATION, "damage group: attack reaction overflow");
    m.attack=static_cast<int>(attack);trace_event("SPELL_DAMAGE_TRIGGER card="+m.card_id+" entity="+std::to_string(m.entity_id)+" attack="+std::to_string(m.attack));
   }
   if(!found)/* NF-122:2 */ fail(FailureCode::DAMAGE_SOURCE_BOUNDARY_UNREVIEWED, "damage group: spell reaction removed");
  }
  if(state_.failure)/* NF-124:0 */ rethrow_stored();
  if(state_.pending_choice)/* NF-125:0 */ fail(FailureCode::DAMAGE_REACTION_ORDER_UNREVIEWED, "damage group: unexpected Choice/suspension during reaction");
  if(index+1!=state_.damage_frames.size())/* NF-120:2 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: unfinished nested child");
  validate_damage_frame_sources(index);
  ++state_.damage_frames[index].reaction_cursor;
 }
 ++state_.damage_frames[index].event_cursor;state_.damage_frames[index].stage=DamageFrameStage::DispatchEvent;
}
int GameSession::close_damage_group(std::size_t index){
 if(index+1!=state_.damage_frames.size()||state_.damage_frames[index].event_cursor!=state_.damage_frames[index].outcomes.size())/* NF-120:3 */ fail(FailureCode::DAMAGE_FRAME_PROTOCOL_VIOLATION, "damage group: incomplete close");
 auto& frame=state_.damage_frames[index];frame.stage=DamageFrameStage::Complete;
 std::int64_t total=0;for(const auto& out:frame.outcomes)total+=out.reported_damage;
 trace_event("GROUP_COMPLETE group="+std::to_string(frame.group_id));state_.damage_frames.pop_back();
 return static_cast<int>(std::min<std::int64_t>(total,std::numeric_limits<int>::max()));
}
int GameSession::run_damage_group(std::vector<DamagePacketIntent> packets,DamageDispatch dispatch,DamageEventOrder order){
 const auto depth=state_.damage_frames.size();
 try{const auto index=open_damage_group(std::move(packets),dispatch,order);while(state_.damage_frames[index].event_cursor<state_.damage_frames[index].outcomes.size())dispatch_damage_event(index);return close_damage_group(index);}
 /* NF-126:0 NF-126:1 */ catch(const UnsupportedSimulationError& e){state_.damage_frames.resize(depth);record_failure(e.record());append_failure_context("damage_group.reaction depth="+std::to_string(depth));rethrow_stored();}
 catch(...){state_.damage_frames.resize(depth);append_failure_context("damage_group.reaction depth="+std::to_string(depth));throw;}
}
int GameSession::deal_damage(int source,int target,int amount,DamageKind kind,int controller,bool lifesteal,DamageAttribution attribution){
 return run_damage_group({damage_intent(source,target,amount,kind,controller,lifesteal,attribution)},DamageDispatch::SinglePacketThenReact,DamageEventOrder::SingleTarget);
}
} // namespace manaengine
