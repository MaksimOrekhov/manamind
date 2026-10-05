// Included by native_tests.cpp after damage_group_tests.hpp.
// Phase 4I.1: Arcane Barrage (TIME_855) bounded targeting contract, reference topology T2 (the explicit primary completes
// with its reactions, then the two extras are sampled and damaged as one ApplyAll group). Expected values come from the
// accepted rules-evidence report, not from the implementation: selections are re-derived from raw bounded_random draws on a
// clone, plus one golden derived by hand from the existing mt19937_64 seed-7 vector. The TEST_RANDOM_DISTINCT_* spells are
// genericity controls and carry no Hearthstone rules evidence.
#include <cmath>
#include <functional>
namespace {
constexpr int enemy_hero=2; // hero_entity_id(1): the opponent of player 0
const std::set<EvidenceConstraint> barrage_debt{EvidenceConstraint::ArcaneBarrageTargetingContractUnverified};
int arcane_barrage_group_count=0;
constexpr std::size_t no_row=static_cast<std::size_t>(-1);

struct DamageRow{int target=-1,amount=0;};
std::vector<DamageRow> damage_rows(const GameSession& s){
 std::vector<DamageRow> rows;
 for(const auto& row:s.diagnostic_trace()){if(row.rfind("DAMAGE source=",0)!=0)continue;rows.push_back({std::stoi(row.substr(row.find(" target=")+8)),std::stoi(row.substr(row.find(" amount=")+8))});}
 return rows;
}
std::size_t first_row(const GameSession& s,const std::string& prefix){const auto& rows=s.diagnostic_trace();for(std::size_t i=0;i<rows.size();++i)if(rows[i].rfind(prefix,0)==0)return i;return no_row;}
std::size_t last_row(const GameSession& s,const std::string& prefix){const auto& rows=s.diagnostic_trace();for(std::size_t i=rows.size();i-->0;)if(rows[i].rfind(prefix,0)==0)return i;return no_row;}
// Ordering predicates require both rows to exist, so an absent row can never satisfy them.
bool row_before(const GameSession& s,const std::string& earlier,const std::string& later){const auto a=first_row(s,earlier),b=first_row(s,later);return a!=no_row&&b!=no_row&&a<b;}
bool rows_after_all(const GameSession& s,const std::string& later,const std::string& earlier_prefix){const auto a=first_row(s,later),b=last_row(s,earlier_prefix);return a!=no_row&&b!=no_row&&a>b;}
std::size_t count_rows(const GameSession& s,const std::string& prefix){std::size_t n=0;for(const auto& row:s.diagnostic_trace())if(row.rfind(prefix,0)==0)++n;return n;}
// Entity ids chosen by the last random-distinct instruction, in selection order.
std::vector<int> selection_ids(const GameSession& s){
 std::vector<int> ids;const auto at=last_row(s,"RANDOM_DISTINCT_SELECTION");if(at==no_row)return ids;
 const auto& row=s.diagnostic_trace()[at];std::string list=row.substr(row.find(" selected=")+10);
 std::size_t from=0;while(from<list.size()){const auto comma=list.find(',',from);ids.push_back(std::stoi(list.substr(from,comma==std::string::npos?std::string::npos:comma-from)));if(comma==std::string::npos)break;from=comma+1;}
 return ids;
}
int selection_candidates(const GameSession& s){const auto at=last_row(s,"RANDOM_DISTINCT_SELECTION");if(at==no_row)return -1;const auto& row=s.diagnostic_trace()[at];return std::stoi(row.substr(row.find(" candidates=")+12));}
// Number of raw u64 RNG values consumed between two states (all draws here use bounds <=10, so one bounded_random is one u64).
std::size_t rng_draws_since(const GameSession& before,const GameSession& after){
 auto probe=TestAccess::diagnostic_snapshot(after);const auto want=TestAccess::rng_values(probe,3);
 for(std::size_t draws=0;draws<=8;++draws){auto b=TestAccess::diagnostic_snapshot(before);(void)TestAccess::rng_values(b,static_cast<int>(draws));if(TestAccess::rng_values(b,3)==want)return draws;}
 return no_row;
}
// Independent partial Fisher-Yates replay over raw bounded_random draws: draw i is bounded_random(n-i), then swap/select.
std::vector<int> replay_selection(GameSession& replay,std::vector<int> candidates,std::size_t count){
 const std::size_t n=candidates.size();count=std::min(count,n);
 std::vector<std::size_t> bounds;for(std::size_t i=0;i<count;++i)bounds.push_back(n-i);
 const auto draws=TestAccess::bounded_values(replay,bounds);std::vector<int> selected;
 for(std::size_t i=0;i<count;++i){std::swap(candidates[i],candidates[i+draws[i]]);selected.push_back(candidates[i]);}
 return selected;
}
std::set<int> as_set(const std::vector<int>& values){return {values.begin(),values.end()};}
bool catalog_accepts(std::vector<CardDefinition> defs){try{CardCatalog c(std::move(defs));}catch(const std::invalid_argument&){return false;}return true;}
std::string catalog_rejection(std::vector<CardDefinition> defs){try{CardCatalog c(std::move(defs));}catch(const std::invalid_argument& e){return e.what();}return {};}
std::vector<CardDefinition> catalog_with_variant(const std::string& id,const std::function<void(CardDefinition&)>& edit){
 auto defs=catalog();CardDefinition variant;for(const auto& d:defs)if(d.card_id=="TIME_855")variant=d;
 variant.card_id=id;edit(variant);defs.push_back(std::move(variant));return defs;
}

void test_barrage_candidate_counts_targets_and_constraint(){ // BB01 BB02 BB03 BB04 BB18(native half)
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int m=TestAccess::minion(s,1,"TEST_FILLER",1,10);TestAccess::minion(s,0,"TEST_FILLER",1,10);
  std::set<int> targets;for(const auto& a:s.semantic_legal_actions())if(a.type==ActionType::PlayCard&&a.card_id=="TIME_855")targets.insert(a.target_entity_id);
  check(targets==std::set<int>{m,enemy_hero},"BB18 Barrage is a generic targeted PlayCard on enemy characters only (no friendly minion, no own hero)");
  auto before=TestAccess::diagnostic_snapshot(s);s.apply_action(play_card_on(s,"TIME_855",m));const auto rows=damage_rows(s);
  check(s.is_valid()&&TestAccess::player(s,1).board[0].health==7&&TestAccess::player(s,1).hero_health==28,"BB01 M takes the primary once, the hero takes the single extra");
  check(rows.size()==2&&rows[0].target==m&&rows[0].amount==3&&rows[1].target==enemy_hero&&rows[1].amount==2,"BB01 primary 3 on M exactly once, then one extra 2 on the hero");
  check(selection_candidates(s)==1&&selection_ids(s)==std::vector<int>{enemy_hero},"BB01 n=1: the primary is excluded by identity, so the hero is the only candidate");
  check(rng_draws_since(before,s)==1,"BB01 n=1 consumes exactly one sampler draw");
  check(s.evidence_constraints()==barrage_debt,"BB01 the targeting constraint is present");}
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int m=TestAccess::minion(s,1,"TEST_FILLER",1,10);auto before=TestAccess::diagnostic_snapshot(s);
  s.apply_action(play_card_on(s,"TIME_855",enemy_hero));const auto rows=damage_rows(s);
  check(s.is_valid()&&TestAccess::player(s,1).hero_health==27&&TestAccess::player(s,1).board[0].health==8,"BB02 hero takes the primary, the lone minion takes one extra");
  check(rows.size()==2&&rows[0].target==enemy_hero&&rows[0].amount==3&&rows[1].target==m&&rows[1].amount==2,"BB02 no repeat: primary on the hero, one extra on the minion");
  check(rng_draws_since(before,s)==1&&s.evidence_constraints()==barrage_debt,"BB02 one draw, constraint present");}
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");auto before=TestAccess::diagnostic_snapshot(s);
  s.apply_action(play_card_on(s,"TIME_855",enemy_hero));const auto rows=damage_rows(s);
  check(s.is_valid()&&TestAccess::player(s,1).hero_health==27&&rows.size()==1&&rows[0].target==enemy_hero&&rows[0].amount==3,"BB03 n=0: hero takes the primary and no extra packet exists");
  check(rng_draws_since(before,s)==0,"BB03 n=0 consumes zero sampler draws");
  check(selection_candidates(s)==0&&selection_ids(s).empty()&&count_rows(s,"GROUP_MUTATIONS_COMPLETE")==1&&count_rows(s,"DAMAGE_BOUNDARY")==1,"BB03 n=0 opens no extras group and evaluates no extras amount");
  check(s.evidence_constraints()==barrage_debt&&s.unsupported_outcome()==std::nullopt,"BB03 constraint still present (instruction executed), branch valid");}
 {auto base=game();TestAccess::reset(base);base.set_trace_enabled(true);TestAccess::hand(base,0,"TIME_855");std::vector<int> minions;for(int i=0;i<4;++i)minions.push_back(TestAccess::minion(base,1,"TEST_FILLER",1,20));const int primary=minions[1];
  const std::set<int> pool{enemy_hero,minions[0],minions[2],minions[3]};std::set<int> reached;bool ok=true,constrained=true,two_draws=true;
  for(std::uint64_t seed=0;seed<240;++seed){auto s=base.clone();TestAccess::rng_seed(*s,seed);s->apply_action(play_card_on(*s,"TIME_855",primary));const auto rows=damage_rows(*s);
   ok=ok&&rows.size()==3&&rows[0].target==primary&&rows[0].amount==3&&rows[1].amount==2&&rows[2].amount==2&&rows[1].target!=rows[2].target&&rows[1].target!=primary&&rows[2].target!=primary&&pool.count(rows[1].target)&&pool.count(rows[2].target);
   ok=ok&&as_set({rows[1].target,rows[2].target})==as_set(selection_ids(*s));for(std::size_t i=1;i<rows.size();++i)reached.insert(rows[i].target);
   constrained=constrained&&s->evidence_constraints()==barrage_debt&&s->is_valid();auto fresh=base.clone();TestAccess::rng_seed(*fresh,seed);two_draws=two_draws&&rng_draws_since(*fresh,*s)==2;}
  check(ok,"BB04 n>=2 sweep: exactly two distinct extras, never the primary, always from {hero, other minions}");check(reached==pool,"BB04 the enemy hero and every other minion are reachable as extras");
  check(constrained,"BB04 constraint present on every n>=2 cast, branch valid");check(two_draws,"BB04 n>=2 consumes exactly two sampler draws");}
 arcane_barrage_group_count++;
}
void test_barrage_distribution_and_rng_replay(){ // BB05 BB15
 for(const int others:{2,5}){ // candidates = hero + others (n = 3 and 6)
  auto base=game();TestAccess::reset(base);base.set_trace_enabled(true);TestAccess::hand(base,0,"TIME_855");std::vector<int> minions;for(int i=0;i<=others;++i)minions.push_back(TestAccess::minion(base,1,"TEST_FILLER",1,20));
  const int n=others+1;const int seeds=3000;std::map<std::pair<int,int>,int> pairs;std::map<int,int> marginal,first;
  for(std::uint64_t seed=0;seed<static_cast<std::uint64_t>(seeds);++seed){auto s=base.clone();TestAccess::rng_seed(*s,seed);s->apply_action(play_card_on(*s,"TIME_855",minions[0]));const auto picked=selection_ids(*s);
   ++pairs[{std::min(picked[0],picked[1]),std::max(picked[0],picked[1])}];++marginal[picked[0]];++marginal[picked[1]];++first[picked[0]];}
  const double pair_mean=seeds*2.0/(n*(n-1)),marginal_mean=seeds*2.0/n,first_mean=seeds*1.0/n;const double pair_tolerance=6.0*std::sqrt(pair_mean),marginal_tolerance=6.0*std::sqrt(marginal_mean),first_tolerance=6.0*std::sqrt(first_mean);
  bool pairs_ok=static_cast<int>(pairs.size())==n*(n-1)/2,marginal_ok=static_cast<int>(marginal.size())==n,first_ok=static_cast<int>(first.size())==n;
  for(const auto& [key,count]:pairs)pairs_ok=pairs_ok&&std::abs(count-pair_mean)<=pair_tolerance;for(const auto& [key,count]:marginal)marginal_ok=marginal_ok&&std::abs(count-marginal_mean)<=marginal_tolerance;for(const auto& [key,count]:first)first_ok=first_ok&&std::abs(count-first_mean)<=first_tolerance;
  check(pairs_ok,"BB05 every unordered pair of eligible candidates is reachable and equally frequent within 6 sigma (n="+std::to_string(n)+")");
  check(marginal_ok,"BB05 each eligible candidate is selected with probability 2/n within 6 sigma (n="+std::to_string(n)+")");
  check(first_ok,"BB05 the first selection is uniform over the candidates within 6 sigma (n="+std::to_string(n)+")");}
 // BB15 independent replay across many seeds: raw draws on a clone predict selected entities, selection order and RNG position.
 {auto base=game();TestAccess::reset(base);base.set_trace_enabled(true);TestAccess::hand(base,0,"TIME_855");std::vector<int> minions;for(int i=0;i<5;++i)minions.push_back(TestAccess::minion(base,1,"TEST_FILLER",1,20));
  bool order_ok=true,position_ok=true;
  for(std::uint64_t seed=0;seed<80;++seed){auto s=base.clone();TestAccess::rng_seed(*s,seed);auto replay=s->clone();
   const auto predicted=replay_selection(*replay,{enemy_hero,minions[0],minions[2],minions[3],minions[4]},2); // stable order: hero, then board left to right, primary removed
   s->apply_action(play_card_on(*s,"TIME_855",minions[1]));order_ok=order_ok&&selection_ids(*s)==predicted;position_ok=position_ok&&TestAccess::rng_values(*s,3)==TestAccess::rng_values(*replay,3);}
  check(order_ok,"BB15 independently replayed bounded_random(n-i) draws predict exact selected entities and their order");check(position_ok,"BB15 the RNG stream sits exactly after those draws (min(k,n) draws, no reroll)");}
 // Hand-derived golden: mt19937_64 seed 7 starts 13915952638675311015, 17511516338625233250. Hero primary, four minions
 // [A,B,C,D]: draw0=r0%4=3 swaps A and D -> D first; draw1=r1%3=0 keeps B at slot 1 -> B second.
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");std::vector<int> m;for(int i=0;i<4;++i)m.push_back(TestAccess::minion(s,1,"TEST_FILLER",1,20));TestAccess::rng_seed(s,7);
  const std::uint64_t r0=13915952638675311015ULL,r1=17511516338625233250ULL;std::vector<int> c=m;const std::size_t d0=r0%4,d1=r1%3;std::swap(c[0],c[d0]);const int first=c[0];std::swap(c[1],c[1+d1]);const int second=c[1];
  check(d0==3&&d1==0&&first==m[3]&&second==m[1],"golden arithmetic: seed 7 selects the fourth then the second minion");
  s.apply_action(play_card_on(s,"TIME_855",enemy_hero));check(selection_ids(s)==std::vector<int>{m[3],m[1]},"BB15 golden: engine selection equals the hand-derived partial Fisher-Yates result for seed 7");}
 arcane_barrage_group_count++;
}
void test_barrage_spell_damage_and_prevention(){ // BB06 BB07
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");TestAccess::minion(s,0,"CORE_EX1_012",1,1);TestAccess::minion(s,0,"CORE_EX1_012",1,1);const int m=TestAccess::minion(s,1,"TEST_FILLER",1,20);TestAccess::minion(s,1,"TEST_FILLER",1,20);
  s.apply_action(play_card_on(s,"TIME_855",m));const auto rows=damage_rows(s);
  check(rows.size()==3&&rows[0].target==m&&rows[0].amount==5&&rows[1].amount==4&&rows[2].amount==4,"BB06 +2 Spell Damage: primary 5 and each extra 4");
  check(TestAccess::player(s,1).hero_health==26&&TestAccess::player(s,1).board[0].health==15&&TestAccess::player(s,1).board[1].health==16,"BB06 enemy health reflects 5/4/4");
  check(count_rows(s,"DAMAGE_BOUNDARY")==2&&last_row(s,"DAMAGE_BOUNDARY")>first_row(s,"DAMAGE_BOUNDARY"),"BB06 exactly two amount evaluations, one per instruction");
  bool current_at_step=true,missile_total=false;for(const auto& row:s.diagnostic_trace())if(row.rfind("DAMAGE_BOUNDARY",0)==0){current_at_step=current_at_step&&row.find("contract=CURRENT_AT_STEP")!=std::string::npos;missile_total=missile_total||row.find("MISSILE_TOTAL")!=std::string::npos;}
  check(current_at_step&&!missile_total,"BB06 CURRENT_AT_STEP, never MISSILE_TOTAL");}
 bool prevented_ok=true,same_selection=true,same_draws=true,shield_selected=false,immune_selected=false,hero_selected=false;
 for(std::uint64_t seed=0;seed<64;++seed){
  auto build=[&](bool prevented){auto g=std::make_unique<GameSession>(game());TestAccess::reset(*g);g->set_trace_enabled(true);TestAccess::hand(*g,0,"TIME_855");TestAccess::minion(*g,1,"TEST_FILLER",1,20);TestAccess::minion(*g,1,"TEST_FILLER",1,5);TestAccess::minion(*g,1,"TEST_FILLER",1,5);if(prevented){TestAccess::set_divine_shield(*g,1,1,true);TestAccess::set_immune(*g,1,2,true);}TestAccess::rng_seed(*g,seed);return g;};
  auto shielded=build(true),control=build(false);auto before=build(true);const int primary=TestAccess::player(*shielded,1).board[0].entity_id,shield=TestAccess::player(*shielded,1).board[1].entity_id,immune=TestAccess::player(*shielded,1).board[2].entity_id;
  shielded->apply_action(play_card_on(*shielded,"TIME_855",primary));control->apply_action(play_card_on(*control,"TIME_855",primary));
  const auto picked=selection_ids(*shielded);same_selection=same_selection&&picked==selection_ids(*control)&&picked.size()==2;same_draws=same_draws&&rng_draws_since(*before,*shielded)==2&&rng_draws_since(*before,*shielded)==rng_draws_since(*before,*control);
  const auto rows=damage_rows(*shielded);std::size_t expected_rows=1;
  for(int id:picked){
   if(id==shield){shield_selected=true;prevented_ok=prevented_ok&&TestAccess::player(*shielded,1).board[1].health==5&&!TestAccess::player(*shielded,1).board[1].divine_shield&&damage_trace_index(*shielded,"DAMAGE_PREVENTED target="+std::to_string(shield))<shielded->diagnostic_trace().size();}
   else if(id==immune){immune_selected=true;prevented_ok=prevented_ok&&TestAccess::player(*shielded,1).board[2].health==5&&TestAccess::player(*shielded,1).board[2].immune;}
   else{hero_selected=true;++expected_rows;prevented_ok=prevented_ok&&TestAccess::player(*shielded,1).hero_health==28;}
  }
  prevented_ok=prevented_ok&&rows.size()==expected_rows&&std::none_of(rows.begin(),rows.end(),[&](const DamageRow& r){return r.target==immune||r.target==shield;});
 }
 check(shield_selected&&immune_selected&&hero_selected,"BB07 sweep reaches Divine Shield, Immune and hero extras");
 check(prevented_ok,"BB07 prevented extras consume their slot: shield pops without damage, Immune keeps its health, no extra event for them");
 check(same_selection,"BB07 selection is identical with and without prevention (no reroll, no retarget)");check(same_draws,"BB07 prevention does not change the number of sampler draws");
 arcane_barrage_group_count++;
}
void test_barrage_mortality_and_outer_boundary(){ // BB08 BB09 BB10
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int murmy=TestAccess::minion(s,1,"CORE_ULD_723",1,1),other=TestAccess::minion(s,1,"TEST_FILLER",1,20);
  s.apply_action(play_card_on(s,"TIME_855",murmy));const auto rows=damage_rows(s);const auto& board=TestAccess::player(s,1).board;const auto returned=std::find_if(board.begin(),board.end(),[](const auto& m){return m.card_id=="CORE_ULD_723";});
  check(selection_candidates(s)==2&&as_set(selection_ids(s))==std::set<int>{enemy_hero,other},"BB08 lethal primary: the dying Reborn minion is excluded by identity and mortality");
  check(returned!=board.end()&&returned->entity_id!=murmy&&returned->health==1&&!returned->reborn,"BB08 Reborn returns as a new identity with fresh state");
  check(std::none_of(rows.begin(),rows.end(),[&](const DamageRow& r){return r.target==returned->entity_id;})&&rows.size()==3,"BB08 the returned entity is never selected or damaged by the extras");
  check(rows_after_all(s,"DEATH entity="+std::to_string(murmy),"DAMAGE source=")&&row_before(s,"RANDOM_DISTINCT_SELECTION","DEATH entity="+std::to_string(murmy)),"BB08 the return happens only at the outer boundary, after every Barrage packet");}
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::deck(s,1,{"TEST_FILLER","TEST_FILLER"});TestAccess::hand(s,0,"TIME_855");const int rattle=TestAccess::minion(s,1,"TEST_DEATHRATTLE_DRAW_TWO",2,2),primary=TestAccess::minion(s,1,"TEST_FILLER",1,20);
  s.apply_action(play_card_on(s,"TIME_855",primary));
  check(as_set(selection_ids(s))==std::set<int>{enemy_hero,rattle}&&TestAccess::player(s,1).board.size()==1,"BB09 lethal extra: the Deathrattle minion dies after the spell");
  check(rows_after_all(s,"DEATH entity="+std::to_string(rattle),"DAMAGE source=")&&row_before(s,"DEATH entity="+std::to_string(rattle),"DEATHRATTLE_RESOLVE"),"BB09 mortality stays pending until the outer boundary; no inner death drain");
  check(TestAccess::player(s,1).hand.size()==2,"BB09 the Deathrattle resolves exactly once, after the spell");}
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int murmy=TestAccess::minion(s,1,"CORE_ULD_723",1,1);
  s.apply_action(play_card_on(s,"TIME_855",enemy_hero));const auto& board=TestAccess::player(s,1).board;
  check(board.size()==1&&board[0].card_id=="CORE_ULD_723"&&board[0].entity_id!=murmy&&board[0].health==1&&!board[0].reborn,"BB09 Reborn extra returns with a new identity at the outer boundary");
  check(rows_after_all(s,"DEATH entity="+std::to_string(murmy),"DAMAGE source="),"BB09 the Reborn extra stays in play until every packet has resolved");}
 // BB10 PRIMITIVE CONTRACT COVERAGE: not a reachable Barrage position. Barrage excludes a lethal primary by identity, so a
 // pre-existing mortally wounded enemy is only constructible by calling the selector primitive directly.
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);const int l1=TestAccess::minion(s,1,"TEST_FILLER",1,5),mortal=TestAccess::minion(s,1,"TEST_FILLER",1,5),l2=TestAccess::minion(s,1,"TEST_FILLER",1,5);TestAccess::set_health(s,1,1,0);
  auto before=TestAccess::diagnostic_snapshot(s);EffectStep step=effect(EffectKind::Damage,TargetSelector::RandomDistinctEnemyCharacters,2);step.random_count=3;
  TestAccess::random_distinct(s,"TIME_855",0,step,-1);const auto picked=selection_ids(s);
  check(as_set(picked)==std::set<int>{enemy_hero,l1,l2}&&picked.size()==3&&selection_candidates(s)==3,"BB10 primitive: the mortally wounded entity is neither selected nor counted in n");
  const auto rows=damage_rows(s);
  check(rng_draws_since(before,s)==3&&TestAccess::player(s,1).board[1].health==0&&std::none_of(rows.begin(),rows.end(),[&](const DamageRow& r){return r.target==mortal;}),"BB10 primitive: three draws for three living candidates, the mortal entity takes no packet");}
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::minion(s,1,"TEST_FILLER",1,5);TestAccess::set_health(s,1,0,0);auto before=TestAccess::diagnostic_snapshot(s);
  EffectStep step=effect(EffectKind::Damage,TargetSelector::RandomDistinctEnemyMinions,2);step.random_count=2;TestAccess::random_distinct(s,"TIME_855",0,step,-1);
  check(selection_candidates(s)==0&&rng_draws_since(before,s)==0&&damage_rows(s).empty()&&s.evidence_constraints().empty(),"BB10 primitive: only mortal candidates means n=0, zero draws, no packet");}
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);const int a=TestAccess::minion(s,1,"TEST_FILLER",1,5),b=TestAccess::minion(s,1,"TEST_FILLER",1,5);
  EffectStep step=effect(EffectKind::Damage,TargetSelector::RandomDistinctEnemyCharacters,1);step.random_count=3;step.exclude_previous_target=true;TestAccess::random_distinct(s,"TIME_855",0,step,a);
  check(as_set(selection_ids(s))==std::set<int>{enemy_hero,b}&&selection_candidates(s)==2,"primitive: the excluded explicit target leaves the pool by identity");}
 arcane_barrage_group_count++;
}
void test_barrage_reactions_and_clone_determinism(){ // BB11 BB13
 const auto pool=test_pool({"GENERATED_SUPPORTED_A","GENERATED_SUPPORTED_B"});const auto& ids=pool.card_ids;
 { // consumer as the primary: its generation completes before the extras are sampled (reference topology T2)
  auto s=game_with_pool(pool,501);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int c=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5),m=TestAccess::minion(s,1,"TEST_FILLER",1,20);
  auto twin=s.clone();auto before=TestAccess::diagnostic_snapshot(s);auto replay=s.clone();const auto generated=TestAccess::bounded_values(*replay,{2});const auto predicted=replay_selection(*replay,{enemy_hero,m},2);
  s.apply_action(play_card_on(s,"TIME_855",c));twin->apply_action(play_card_on(*twin,"TIME_855",c));
  check(s.is_valid()&&TestAccess::player(s,1).board[0].health==2&&TestAccess::player(s,1).hand.size()==1&&TestAccess::player(s,1).hand[0].card_id==ids[generated[0]],"BB11 consumer primary: it takes the packet once and generates the card drawn first");
  check(selection_ids(s)==predicted&&rng_draws_since(before,s)==3,"BB11 sampler progression follows the generation draw: three draws, selection equals the replay");
  check(row_before(s,"DAMAGE_REACTION","RANDOM_DISTINCT_SELECTION"),"BB11/T2 the primary's reaction completes before the extras are selected");
  check(s.diagnostic_trace()==twin->diagnostic_trace()&&TestAccess::rng_values(s,3)==TestAccess::rng_values(*twin,3)&&TestAccess::player(s,1).hand[0].card_id==TestAccess::player(*twin,1).hand[0].card_id,"BB11 a clone resolves the same cast identically (trace, RNG, generated card)");}
 { // consumer as the only extra
  auto s=game_with_pool(pool,502);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int c=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);auto before=TestAccess::diagnostic_snapshot(s);auto replay=s.clone();const auto draws=TestAccess::bounded_values(*replay,{1,2});
  s.apply_action(play_card_on(s,"TIME_855",enemy_hero));
  check(s.is_valid()&&selection_ids(s)==std::vector<int>{c}&&TestAccess::player(s,1).board[0].health==3&&TestAccess::player(s,1).hero_health==27&&TestAccess::player(s,1).hand.size()==1&&TestAccess::player(s,1).hand[0].card_id==ids[draws[1]],"BB11 consumer extra: selected, damaged once, reacts with the draw that follows the selection draw");
  check(rng_draws_since(before,s)==2&&row_before(s,"RANDOM_DISTINCT_SELECTION","DAMAGE_REACTION"),"BB11 selection precedes the extras group reaction; no reroll");}
 { // two consumers as extras: selection order differs from event order, which follows entry sequence (reviewed minion-entry order)
  bool entry_order=true,selection_replayed=true,generation_in_entry_order=true;
  for(std::uint64_t seed=0;seed<16;++seed){auto s=game_with_pool(pool,seed);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int older=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5),newer=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);
   auto replay=s.clone();const auto predicted=replay_selection(*replay,{older,newer},2);const auto gen=TestAccess::bounded_values(*replay,{2,2});s.apply_action(play_card_on(s,"TIME_855",enemy_hero));
   selection_replayed=selection_replayed&&selection_ids(s)==predicted;entry_order=entry_order&&damage_trace_index(s,"consumer="+std::to_string(older))<damage_trace_index(s,"consumer="+std::to_string(newer))&&damage_trace_index(s,"consumer="+std::to_string(newer))<s.diagnostic_trace().size();
   generation_in_entry_order=generation_in_entry_order&&TestAccess::player(s,1).hand.size()==2&&TestAccess::player(s,1).hand[0].card_id==ids[gen[0]]&&TestAccess::player(s,1).hand[1].card_id==ids[gen[1]];}
  check(selection_replayed,"BB11 two consumer extras: the sampler order equals the replay");check(entry_order&&generation_in_entry_order,"BB11 minion-only extras reuse the reviewed entry-sequence event order for their reactions");}
 { // Raincaller: one reaction family needs no ordering contract; attack gain once, extras still sampled
  auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");TestAccess::minion(s,0,"CATA_487",1,4);const int p=TestAccess::minion(s,1,"TEST_FILLER",1,20),m=TestAccess::minion(s,1,"TEST_FILLER",1,20);auto before=TestAccess::diagnostic_snapshot(s);
  s.apply_action(play_card_on(s,"TIME_855",p));
  check(s.is_valid()&&TestAccess::player(s,0).board[0].attack==3&&count_rows(s,"SPELL_DAMAGE_TRIGGER")==1,"BB13 Raincaller gains Attack exactly once across primary and extras");
  check(row_before(s,"SPELL_DAMAGE_TRIGGER","RANDOM_DISTINCT_SELECTION")&&as_set(selection_ids(s))==std::set<int>{enemy_hero,m}&&rng_draws_since(before,s)==2,"BB13 the primary's reaction completes first, extras are still sampled with two draws");
  check(TestAccess::player(s,0).spell_damage_dealt_this_turn==7&&TestAccess::player(s,1).hero_health==28,"BB13 three packets counted (3+2+2)");}
 arcane_barrage_group_count++;
}
void test_barrage_fail_closed_paths(){ // BB12 BB14
 {const auto pool=test_pool({"GENERATED_SUPPORTED_A","GENERATED_SUPPORTED_B"});auto s=game_with_pool(pool,601);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int primary=TestAccess::minion(s,1,"TEST_FILLER",1,20),consumer=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);auto before=TestAccess::diagnostic_snapshot(s);auto replay=s.clone();const auto predicted=replay_selection(*replay,{enemy_hero,consumer},2);
  check(fails_closed(s,[&]{s.apply_action(play_card_on(s,"TIME_855",primary));}),"BB12 generation consumer beside a hero extra fails closed");
  check(as_set(predicted)==std::set<int>{enemy_hero,consumer},"BB12 setup: both candidates are selected (n=2, k=2)");
  check(TestAccess::player(s,1).board[0].health==17,"BB12 the primary-step mutation already executed under T2 and is retained diagnostically");
  check(TestAccess::player(s,1).hero_health==30&&TestAccess::player(s,1).board[1].health==5&&TestAccess::player(s,1).hand.empty(),"BB12 the guard fires before any mutation of the extras group: no hero damage, no consumer damage, no generation");
  check(s.unsupported_outcome().value_or("").find("reactive combat/hero-area/compound ordering is not reviewed")!=std::string::npos,"BB12 the first unsupported reason is the existing scalar guard");
  check(rng_draws_since(before,s)==2&&s.evidence_constraints()==barrage_debt,"BB12 only the two selection draws were consumed (no reroll); the reached-instruction constraint is retained");check_poisoned_surface(s,"BB12");}
 { // BB14 unresolved Fire pool as the primary: the failure precedes the extras instruction entirely
  auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int plume=TestAccess::minion(s,1,"CATA_488t",1,5);auto before=TestAccess::diagnostic_snapshot(s);
  check(fails_closed(s,[&]{s.apply_action(play_card_on(s,"TIME_855",plume));}),"BB14 unresolved Fire pool fails the primary's reaction");
  check(s.unsupported_outcome().value_or("").find("pool identity is not loaded")!=std::string::npos&&TestAccess::player(s,1).board[0].health==2&&TestAccess::player(s,1).hero_health==30,"BB14 first reason kept, primary mutation retained, extras never reached");
  check(rng_draws_since(before,s)==0&&s.evidence_constraints().empty()&&first_row(s,"RANDOM_DISTINCT_SELECTION")==no_row,"BB14/BB17 no RNG, no reroll, and no constraint when the extras instruction is never reached");check_poisoned_surface(s,"BB14 primary");}
 { // BB14 as the only extra: the selection draw happened, the group mutated, then the reaction failed
  auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");TestAccess::minion(s,1,"CATA_488t",1,5);auto before=TestAccess::diagnostic_snapshot(s);
  check(fails_closed(s,[&]{s.apply_action(play_card_on(s,"TIME_855",enemy_hero));}),"BB14 unresolved Fire pool fails the extras reaction");
  check(s.unsupported_outcome().value_or("").find("pool identity is not loaded")!=std::string::npos&&TestAccess::player(s,1).board[0].health==3&&TestAccess::player(s,1).hero_health==27,"BB14 all mutations retained, first reason kept");
  check(rng_draws_since(before,s)==1&&selection_ids(s).size()==1,"BB14 exactly one selection draw and no reroll after the unsupported outcome");check_poisoned_surface(s,"BB14 extra");}
 arcane_barrage_group_count++;
}
void test_barrage_reaction_kind_tripwire(){ // BB16
 // Compile-time half: TestAccess::barrage_topology_review has an exhaustive switch promoted to an error, so adding a
 // ReactionKind member stops this translation unit from building until the review below is redone.
 check(TestAccess::barrage_topology_review(TestAccess::ReactionKind::SelfTakesDamageV1)!=nullptr&&TestAccess::barrage_topology_review(TestAccess::ReactionKind::FirstSpellDamageAttackV1)!=nullptr,"BB16 both admitted damage reaction families are covered by the reviewed Arcane Barrage topology (T2)");
 check(std::string(TestAccess::barrage_topology_review(TestAccess::ReactionKind::SelfTakesDamageV1)).find("reads no enemy board")!=std::string::npos,"BB16 the reviewed families change neither the candidate set, enemy health nor caster Spell Damage");
 arcane_barrage_group_count++;
}
void test_barrage_constraint_scope(){ // BB17
 bool absent=true;
 { // Barrage in a deck, in a hand, and unrelated spells: no debt
  std::vector<std::string> deck(30,"TIME_855");GameSession drawn(deck,deck,catalog(),123,false,"MAGE","MAGE");absent=absent&&drawn.evidence_constraints().empty();
  auto s=game();TestAccess::reset(s);TestAccess::deck(s,1,{"TEST_FILLER"});TestAccess::hand(s,0,"TIME_855");TestAccess::hand(s,0,"CORE_CS2_029");TestAccess::minion(s,1,"TEST_FILLER",1,20);absent=absent&&s.evidence_constraints().empty();
  s.apply_action(play_card_on(s,"CORE_CS2_029",enemy_hero));absent=absent&&s.evidence_constraints().empty()&&s.is_valid();
  end_turn(s);absent=absent&&s.evidence_constraints().empty()&&s.is_valid();}
 { // countered before its effect
  auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TIME_855");const int m=TestAccess::minion(s,1,"TEST_FILLER",1,20);TestAccess::secret(s,1,"CORE_EX1_287");
  s.apply_action(play_card_on(s,"TIME_855",m));absent=absent&&s.is_valid()&&s.evidence_constraints().empty()&&TestAccess::player(s,1).board[0].health==20&&TestAccess::player(s,1).hero_health==30&&first_row(s,"RANDOM_DISTINCT_SELECTION")==no_row;}
 { // synthetic and unrelated random-distinct consumers, with and without a hero pool
  for(const std::string id:{"TEST_RANDOM_DISTINCT_MINIONS_3","TEST_RANDOM_DISTINCT_CHARACTERS_2"}){auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,id);for(int i=0;i<3;++i)TestAccess::minion(s,1,"TEST_FILLER",1,20);
   s.apply_action(play(s));absent=absent&&s.is_valid()&&s.evidence_constraints().empty()&&first_row(s,"RANDOM_DISTINCT_SELECTION")!=no_row;}}
 check(absent,"BB17 absent: Barrage only in a deck or hand, an unrelated spell, a countered Barrage, and unrelated random-distinct consumers (minion and hero pools)");
 bool present=true;
 for(int minions=0;minions<=3;++minions){ // n = 0, 1, 2, 3 candidates (cast on the hero) all carry the constraint and stay valid
  auto s=game();TestAccess::reset(s);TestAccess::hand(s,0,"TIME_855");for(int i=0;i<minions;++i)TestAccess::minion(s,1,"TEST_FILLER",1,20);s.apply_action(play_card_on(s,"TIME_855",enemy_hero));
  present=present&&s.evidence_constraints()==barrage_debt&&s.is_valid()&&s.clone()->evidence_constraints()==barrage_debt&&evidence_constraint_id(*s.evidence_constraints().begin())==std::string("ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED");}
 check(present,"BB17 present for n=0, 1, 2 and 3 candidates, branch valid, retained by clones, canonical string ID");
 check(std::string(evidence_constraint_id(EvidenceConstraint::ArcaneBarrageTargetingContractUnverified))=="ARCANE_BARRAGE_TARGETING_CONTRACT_UNVERIFIED","BB17 stable canonical ID");
 check(barrage_debt.size()==1,"BB17 topology adds no second constraint");
 arcane_barrage_group_count++;
}
void test_random_distinct_genericity_control(){ // BB19: no card-ID branch, same selector path, no promotion
 bool counts_ok=true,never_hero=true,no_debt=true,untargeted=true;std::set<int> reached;
 for(const int minions:{0,1,2,3,5}){
  for(std::uint64_t seed=0;seed<(minions==5?200u:1u);++seed){auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TEST_RANDOM_DISTINCT_MINIONS_3");std::vector<int> ids;for(int i=0;i<minions;++i)ids.push_back(TestAccess::minion(s,1,"TEST_FILLER",1,20));TestAccess::rng_seed(s,seed);auto before=TestAccess::diagnostic_snapshot(s);
   untargeted=untargeted&&play(s).target_entity_id<0;
   s.apply_action(play(s));const auto rows=damage_rows(s);const auto picked=selection_ids(s);const std::size_t expect=std::min<std::size_t>(3,static_cast<std::size_t>(minions));
   counts_ok=counts_ok&&rows.size()==expect&&picked.size()==expect&&as_set(picked).size()==expect&&rng_draws_since(before,s)==expect&&selection_candidates(s)==minions;
   never_hero=never_hero&&TestAccess::player(s,1).hero_health==30&&std::none_of(picked.begin(),picked.end(),[](int id){return id==enemy_hero;});no_debt=no_debt&&s.evidence_constraints().empty()&&s.is_valid();for(int id:picked)reached.insert(id);}}
 check(untargeted,"BB19 the synthetic spell is an untargeted generic PlayCard");check(counts_ok,"BB19 k=3 EnemyMinions: min(3,n) distinct packets and exactly min(3,n) draws for n=0,1,2,3,5");check(never_hero,"BB19 the minions-only selector never reaches the hero");
 check(no_debt,"BB19 the synthetic fixture raises no evidence constraint and promotes no real card");check(reached.size()==5,"BB19 all five minions are reachable (n=5 sweep)");
 // The same primitive serves the hero pool: no card-ID branch is needed to switch pools or exclusions.
 {auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::hand(s,0,"TEST_RANDOM_DISTINCT_CHARACTERS_2");TestAccess::minion(s,1,"TEST_FILLER",1,20);s.apply_action(play(s));
  check(as_set(selection_ids(s))==std::set<int>{enemy_hero,TestAccess::player(s,1).board[0].entity_id}&&s.evidence_constraints().empty(),"BB19 a hero-pool consumer with no declared constraint selects identically and records no debt");}
 {const auto& defs=catalog();CardDefinition barrage,synthetic;for(const auto& d:defs){if(d.card_id=="TIME_855")barrage=d;if(d.card_id=="TEST_RANDOM_DISTINCT_MINIONS_3")synthetic=d;}
  const auto& real=barrage.effects[1];const auto& control=synthetic.effects[0];
  check(real.kind==control.kind&&real.random_count==2&&control.random_count==3&&real.evidence_constraint.has_value()&&!control.evidence_constraint.has_value()&&!control.exclude_previous_target,"BB19 the real card and the control differ only in declared fields, the constraint being a declaration, not a card-ID branch");}
 arcane_barrage_group_count++;
}
void test_random_distinct_declaration_validation(){ // malformed declarative combinations fail closed at catalog load
 check(catalog_accepts(catalog_with_variant("TEST_BARRAGE_SHAPE",[](CardDefinition&){})),"V00 positive control: the Barrage-shaped declaration loads");
 for(const int k:{1,2,3})for(const auto selector:{TargetSelector::RandomDistinctEnemyCharacters,TargetSelector::RandomDistinctEnemyMinions})check(catalog_accepts(catalog_with_variant("TEST_RANDOM_K",[&](CardDefinition& d){d.effects={effect(EffectKind::Damage,selector,1)};d.effects[0].random_count=k;})),"V00 bounded k in 1..3 loads for both selectors without exclusion or constraint");
 struct Case{const char* label;const char* reason;std::function<void(CardDefinition&)> edit;};
 const std::vector<Case> bad={
  {"count 0 with a random-distinct selector","within 1..3",[](CardDefinition& d){d.effects[1].random_count=0;}},
  {"count 4","within 1..3",[](CardDefinition& d){d.effects[1].random_count=4;}},
  {"negative count","within 1..3",[](CardDefinition& d){d.effects[1].random_count=-1;}},
  {"random_count on an explicit selector","require a RandomDistinct selector",[](CardDefinition& d){d.effects[0].random_count=2;}},
  {"random_count on an area selector","require a RandomDistinct selector",[](CardDefinition& d){d.effects[1].target=TargetSelector::EnemyMinions;}},
  {"random_count on the single random-minion selector","require a RandomDistinct selector",[](CardDefinition& d){d.effects[1].target=TargetSelector::RandomEnemyMinion;}},
  {"exclude_previous_target on an ordinary selector","require a RandomDistinct selector",[](CardDefinition& d){d.effects[0].exclude_previous_target=true;}},
  {"evidence_constraint on an ordinary selector","require a RandomDistinct selector",[](CardDefinition& d){d.effects[0].evidence_constraint=EvidenceConstraint::ArcaneBarrageTargetingContractUnverified;}},
  {"random-distinct Freeze","",[](CardDefinition& d){d.effects[1].kind=EffectKind::Freeze;d.effects[1].amount=0;}},
  {"random-distinct Draw","",[](CardDefinition& d){d.effects[1].kind=EffectKind::Draw;}},
  {"exclusion with no earlier step","earlier explicit-target Damage step",[](CardDefinition& d){d.effects.erase(d.effects.begin());}},
  {"exclusion after an area step only","earlier explicit-target Damage step",[](CardDefinition& d){d.effects[0].target=TargetSelector::EnemyMinions;}},
  {"exclusion before the explicit step","earlier explicit-target Damage step",[](CardDefinition& d){std::swap(d.effects[0],d.effects[1]);}},
  {"exclusion after a non-Damage explicit step","earlier explicit-target Damage step",[](CardDefinition& d){d.effects[0].kind=EffectKind::Freeze;d.effects[0].amount=0;}},
  {"Lifesteal","positive non-Lifesteal Damage step on a spell",[](CardDefinition& d){d.effects[1].lifesteal=true;}},
  {"zero amount","positive non-Lifesteal Damage step on a spell",[](CardDefinition& d){d.effects[1].amount=0;}},
  {"minion Battlecry","positive non-Lifesteal Damage step on a spell",[](CardDefinition& d){d.card_type="MINION";d.cost=3;d.attack=1;d.health=1;d.battlecry=true;}},
  {"two random-distinct steps","at most one RandomDistinct",[](CardDefinition& d){d.effects.push_back(d.effects[1]);}},
  {"constraint outside the reviewed allowlist","outside the reviewed allowlist",[](CardDefinition& d){d.effects[1].evidence_constraint=EvidenceConstraint::DarkGiftSamplerUnverified;}},
  {"random-distinct Choose One mode","",[](CardDefinition& d){d.choose_one_a={d.effects[1]};d.choose_one_b={d.effects[1]};d.effects.clear();}},
 };
 for(const auto& c:bad){const auto reason=catalog_rejection(catalog_with_variant("TEST_BAD_RANDOM",c.edit));check(!reason.empty()&&reason.find(c.reason)!=std::string::npos,std::string("V rejected: ")+c.label+(reason.empty()?" (accepted!)":" -> "+reason));}
 // Reuse of ordinary selectors keeps their behavior: the new fields default to inert values on every existing step.
 check(EffectStep{}.random_count==0&&!EffectStep{}.exclude_previous_target&&!EffectStep{}.evidence_constraint.has_value(),"V default EffectStep carries no random-distinct semantics");
 arcane_barrage_group_count++;
}
void run_arcane_barrage_family(){
 arcane_barrage_group_count=0;
 test_barrage_candidate_counts_targets_and_constraint();test_barrage_distribution_and_rng_replay();test_barrage_spell_damage_and_prevention();test_barrage_mortality_and_outer_boundary();
 test_barrage_reactions_and_clone_determinism();test_barrage_fail_closed_paths();test_barrage_reaction_kind_tripwire();test_barrage_constraint_scope();test_random_distinct_genericity_control();test_random_distinct_declaration_validation();
}
}
