// Included by native_tests.cpp: test-only drivers over the production typed frames.
// Scripted child calls below add no production card or executable declaration.
namespace {
std::size_t damage_trace_index(const GameSession& s,const std::string& text){
 const auto& rows=s.diagnostic_trace();for(std::size_t i=0;i<rows.size();++i)if(rows[i].find(text)!=std::string::npos)return i;return rows.size();
}
template<class F> bool throws_unsupported(F&& f){try{f();}catch(const UnsupportedSimulationError&){return true;}return false;}
void check_poisoned_surface(GameSession& s,const std::string& label){
 check(!s.is_valid()&&s.unsupported_outcome().has_value(),label+": poisoned flag and first reason stay inspectable");
 check(throws_unsupported([&]{(void)s.observation(0);}),label+": observation refused");
 check(throws_unsupported([&]{(void)s.clone();}),label+": clone refused");
 check(throws_unsupported([&]{(void)s.legal_actions();}),label+": legal_actions refused");
 check(throws_unsupported([&]{(void)s.result();}),label+": result refused");
 check(throws_unsupported([&]{(void)s.is_complete();}),label+": is_complete refused");
 check(throws_unsupported([&]{(void)s.needs_choice();}),label+": needs_choice refused");
 check(throws_unsupported([&]{(void)s.choice_options();}),label+": choice_options refused");
 check(throws_unsupported([&]{s.begin_prototype_choice();}),label+": prototype choice refused");
 check(throws_unsupported([&]{Action a;a.type=ActionType::EndTurn;s.apply_action(a);}),label+": further action refused");
 (void)s.evidence_constraints();(void)s.diagnostic_trace();(void)s.seed();
}
void test_damage_group_failure_funnel(){ // remediation: T01/T02/T03 and the public action boundary
 auto v=game();TestAccess::reset(v);v.set_trace_enabled(true);TestAccess::hand(v,0,"CATA_488");v.apply_action(play_action_for(v,"CATA_488"));
 check(throws_unsupported([&]{end_turn(v);}),"T02 unresolved Fire pool fails the reaction stage");
 check(TestAccess::player(v,0).board[0].health==2&&TestAccess::player(v,0).board[2].health==2&&TestAccess::frame_depth(v)==0,"T02 both area mutations retained, frames unwound");
 check_poisoned_surface(v,"T02");check(!v.diagnostic_trace().empty(),"T02 diagnostic trace remains available");
 auto h=game();TestAccess::reset(h);TestAccess::deck(h,1,{"TEST_FILLER"});TestAccess::minion(h,0,"CATA_999",4,8);TestAccess::fixed_summon(h,0,"CATA_488");TestAccess::player(h,1).hero_health=4;
 check(throws_unsupported([&]{end_turn(h);}),"T01 reaction failure after lethal hero damage");
 check(TestAccess::player(h,1).hero_health==0,"T01 lethal hero damage retained diagnostically only");
 check_poisoned_surface(h,"T01 hero-dead");
 auto defs=catalog();auto bad=def("TEST_AREA_THEN_HEAL","SPELL",1,0,0,"EFFECT_COMPOSITION");bad.effects={effect(EffectKind::Damage,TargetSelector::EnemyMinions,1),effect(EffectKind::Heal,TargetSelector::ExplicitCharacter,1)};defs.push_back(bad);
 std::vector<std::string> deck(30,"TEST_FILLER");GameSession g(deck,deck,defs,123,false,"MAGE","MAGE");TestAccess::reset(g);TestAccess::hand(g,0,"TEST_AREA_THEN_HEAL");const int victim=TestAccess::minion(g,1,"POOL_LOW_A",1,1);
 check(throws_unsupported([&]{g.apply_action(play(g,victim));}),"T03 bare throw after area mutation");
 check(!g.is_valid()&&g.failure()->code==FailureCode::HEAL_MORTALLY_WOUNDED_UNREVIEWED&&g.unsupported_outcome().value_or("").find("cannot heal")!=std::string::npos,"T03 funnel poisons with a stable diagnostic carrying the original reason");
 check(TestAccess::player(g,1).board[0].health==0&&TestAccess::player(g,0).hand.empty()&&TestAccess::frame_depth(g)==0,"T03 mutation retained diagnostically");
 check_poisoned_surface(g,"T03");
 // A malformed synthetic Secret reaches std::invalid_argument only after the opponent's minion play mutates state.
 auto exception_defs=catalog();auto malformed_secret=def("TEST_POST_MUTATION_LOGIC_ERROR","SPELL",1,0,0);malformed_secret.secret=true;malformed_secret.secret_trigger="OPPONENT_PLAYS_MINION";malformed_secret.secret_effect="INVALID_TEST_EFFECT";exception_defs.push_back(malformed_secret);
 GameSession standard(deck,deck,exception_defs,124,false,"MAGE","MAGE");TestAccess::reset(standard);TestAccess::hand(standard,0,"TEST_POST_MUTATION_LOGIC_ERROR");standard.apply_action(play_action_for(standard,"TEST_POST_MUTATION_LOGIC_ERROR"));TestAccess::active(standard,1);TestAccess::player(standard,1).mana=10;TestAccess::hand(standard,1,"TEST_FILLER");
 auto standard_rng_shadow=standard.clone();const auto expected_standard_rng=TestAccess::rng_values(*standard_rng_shadow,3);bool normalized_logic_error=false;std::string original_reason;
 try{standard.apply_action(play_action_for(standard,"TEST_FILLER"));}catch(const UnsupportedSimulationError& e){normalized_logic_error=true;original_reason=e.what();}catch(...){ }
 check(normalized_logic_error&&original_reason.find("unknown Secret effect")!=std::string::npos,"T03 std::logic_error becomes native UnsupportedSimulationError with original reason");
 check(!standard.is_valid()&&TestAccess::player(standard,1).board.size()==1&&TestAccess::player(standard,1).hand.empty()&&TestAccess::frame_depth(standard)==0,"T03 post-mutation state retained and damage frames cleared");
 check(TestAccess::rng_values(standard,3)==expected_standard_rng,"T03 standard-exception normalization does not change RNG state");check_poisoned_surface(standard,"T03 standard exception");
 // RNG consumed before a later bare throw stays consumed.
 auto rdefs=catalog();auto rbad=def("TEST_RANDOM_THEN_HEAL","SPELL",1,0,0,"EFFECT_COMPOSITION");rbad.effects={effect(EffectKind::Damage,TargetSelector::RandomEnemyMinion,1),effect(EffectKind::Heal,TargetSelector::ExplicitCharacter,1)};rdefs.push_back(rbad);
 GameSession r(deck,deck,rdefs,123,false,"MAGE","MAGE");TestAccess::reset(r);TestAccess::hand(r,0,"TEST_RANDOM_THEN_HEAL");const int only=TestAccess::minion(r,1,"POOL_LOW_A",1,1);auto shadow=r.clone();TestAccess::bounded_values(*shadow,{1});
 check(throws_unsupported([&]{r.apply_action(play(r,only));})&&!r.is_valid(),"T03 random step then bare throw poisons");
 check(TestAccess::rng_values(r,3)==TestAccess::rng_values(*shadow,3),"T03 consumed RNG is preserved, never rerolled");
 // Illegal user input is rejected before mutation and does not poison.
 auto ill=game();TestAccess::reset(ill);TestAccess::minion(ill,0,"TEST_FILLER",1,4);Action bogus;bogus.type=ActionType::Attack;bogus.attacker_entity_id=9999;bogus.target_entity_id=2;
 bool rejected=false;try{ill.apply_action(bogus);}catch(const std::invalid_argument&){rejected=true;}
 check(rejected&&ill.is_valid()&&!ill.unsupported_outcome()&&TestAccess::player(ill,0).board[0].health==4&&!ill.legal_actions().empty(),"illegal input is not a simulated unsupported branch");
}
void test_damage_group_remediation_semantics(){
 // Mortal queued EOT source: the phase-model result is kept, but only as bounded evidence debt.
 for(int kind=0;kind<2;++kind)for(int mortal=1;mortal>=0;--mortal){
  auto s=game();TestAccess::reset(s);TestAccess::deck(s,1,{"TEST_FILLER"});TestAccess::minion(s,0,"CATA_488",4,8);
  TestAccess::minion(s,0,kind?"CATA_475":"CATA_999",kind?3:4,kind?(mortal?3:6):(mortal?3:4));TestAccess::player(s,1).hero_health=kind?2:4;end_turn(s);
  const std::string name=kind?"CATA_475":"CATA_999";
  check(s.is_valid()&&TestAccess::player(s,1).hero_health==0&&s.result()==std::optional<std::string>{"PLAYER1_WIN"},name+(mortal?" killed by an earlier source still resolves (previous engine skipped it): enemy hero 0, PLAYER1_WIN":" healthy control also resolves"));
  const std::set<EvidenceConstraint> expected=mortal?std::set<EvidenceConstraint>{EvidenceConstraint::MortalQueuedEotSourceUnverified}:std::set<EvidenceConstraint>{};
  check(s.evidence_constraints()==expected,name+(mortal?" mortal source carries MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED":" healthy source carries no debt"));
 }
 check(std::string(evidence_constraint_id(EvidenceConstraint::MortalQueuedEotSourceUnverified))=="MORTAL_QUEUED_EOT_SOURCE_UNVERIFIED","evidence constraint has a stable canonical ID");
 // Raincaller: a single reaction family needs no ordering contract.
 {auto s=game();TestAccess::reset(s);TestAccess::hand(s,0,"CORE_CS2_062");TestAccess::minion(s,0,"CATA_487",1,4);TestAccess::minion(s,1,"POOL_LOW_B",2,4);s.apply_action(play(s));
  check(s.is_valid()&&TestAccess::player(s,0).board[0].attack==3&&TestAccess::player(s,0).board[0].health==1&&TestAccess::player(s,0).hero_health==27&&TestAccess::player(s,1).hero_health==27&&TestAccess::player(s,1).board[0].health==1&&TestAccess::player(s,0).spell_damage_dealt_this_turn==12,"hero-containing Hellfire plus Raincaller is supported again: one attack gain, four counted packets");}
 {auto s=game();TestAccess::reset(s);TestAccess::hand(s,0,"CATA_489t2");TestAccess::minion(s,0,"CATA_487",1,4);TestAccess::minion(s,1,"POOL_LOW_B",2,9);s.apply_action(play(s));
  check(s.is_valid()&&TestAccess::player(s,0).board[0].attack==3&&TestAccess::player(s,1).hero_health==28&&TestAccess::player(s,1).board[0].health==7,"enemy-character Shatter fragment plus Raincaller is supported again");}
 {auto s=game();TestAccess::reset(s);TestAccess::active(s,0);const int a=TestAccess::minion(s,0,"TEST_FILLER",2,5,true);TestAccess::minion(s,0,"POOL_LOW_A",1,4);TestAccess::minion(s,1,"CATA_487",1,4);TestAccess::secret(s,1,"CORE_EX1_610");s.apply_action(attack(s,a,2));
  check(s.is_valid()&&TestAccess::player(s,1).board[0].attack==3&&TestAccess::player(s,0).hero_health==28&&TestAccess::player(s,1).hero_health==28,"Explosive Trap plus Raincaller on the Secret side is supported again");}
 {auto s=game();TestAccess::reset(s);TestAccess::secret(s,1,"CORE_LOOT_101");TestAccess::minion(s,1,"CATA_487",1,4);TestAccess::hand(s,0,"POOL_HIGH");s.apply_action(play_hand(s,0));
  check(s.is_valid()&&TestAccess::player(s,0).hero_health==27&&TestAccess::player(s,0).board.empty()&&TestAccess::player(s,1).board[0].attack==3,"Runes without Shield plus Raincaller: lethal minion packet and excess both counted, attack gain once");}
 {auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL","CORE_DS1_185"}));TestAccess::hand(s,0,"CORE_CS2_032");TestAccess::minion(s,0,"CATA_487",1,4);TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,9);s.apply_action(play(s));
  check(s.is_valid()&&TestAccess::player(s,0).board[0].attack==3&&TestAccess::player(s,1).board[0].health==4&&TestAccess::player(s,1).hand.size()==1,"minion area with one generation consumer plus Raincaller performs both reactions");}
 // Still guarded (narrowest): generation inside hero-area/combat/compound groups, and one entity being both reaction families.
 {auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL","CORE_DS1_185"}));TestAccess::hand(s,0,"CORE_CS2_062");TestAccess::minion(s,0,"CATA_487",1,4);TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);
  check(fails_closed(s,[&]{s.apply_action(play(s));}),"hero-area generation stays guarded even beside Raincaller");check(TestAccess::player(s,0).hero_health==30&&TestAccess::player(s,0).board[0].attack==1&&TestAccess::player(s,1).board[0].health==5,"guard precedes every mutation");}
 {auto defs=catalog();auto both=def("TEST_SELF_WATCHER","MINION",2,1,5,"SPELL_DAMAGE_GAINS_ATTACK");both.spell_damage_attack=2;both.takes_damage_pool_id="TEST_REVIEWED_POOL";both.takes_damage_cost_delta=-3;defs.push_back(both);
  auto shared=std::make_shared<CardCatalog>(defs,std::vector<PoolManifest>{test_pool({"TEST_FIRE_SPELL"})},"synthetic_test_snapshot",std::string(64,'a'));std::vector<std::string> deck(30,"TEST_FILLER");GameSession s(deck,deck,std::move(shared),123,false,"MAGE","MAGE");TestAccess::reset(s);
  const int self=TestAccess::minion(s,0,"TEST_SELF_WATCHER",1,5);check(fails_closed(s,[&]{TestAccess::packet_damage(s,-1,self,1,DamageKind::Spell);}),"a consumer that is also its own spell-damage watcher stays unsupported");}
 // Event order across sides follows entry sequence; expected draws are replayed independently of the engine.
 {auto pool=test_pool({"CORE_CS2_029","CORE_DS1_185","TEST_FIRE_SPELL"});pool.pool_id="fire_spell_standard_20261001_candidate_v1";pool.predicate_rules_fingerprint=pool_predicate_rules_fingerprint(pool);
  auto s=game_with_pool(pool,321);s.set_trace_enabled(true);TestAccess::deck(s,1,{"TEST_FILLER"});const int older=TestAccess::minion(s,1,"CATA_488t",2,5);TestAccess::hand(s,0,"CATA_488");s.apply_action(play_action_for(s,"CATA_488"));
  const int left=TestAccess::player(s,0).board[0].entity_id,right=TestAccess::player(s,0).board[2].entity_id;auto replay=s.clone();const auto draws=TestAccess::bounded_values(*replay,{3,3,3});
  end_turn(s);const std::vector<std::string> ids=pool.card_ids;
  check(damage_trace_index(s,"consumer="+std::to_string(older))<damage_trace_index(s,"consumer="+std::to_string(left))&&damage_trace_index(s,"consumer="+std::to_string(left))<damage_trace_index(s,"consumer="+std::to_string(right)),"cross-side area events follow entry sequence: older enemy Plume, then left, then right");
  check(TestAccess::player(s,1).hand.size()==2&&TestAccess::player(s,1).hand[0].card_id==ids[draws[0]]&&TestAccess::player(s,0).hand.size()==2&&TestAccess::player(s,0).hand[0].card_id==ids[draws[1]]&&TestAccess::player(s,0).hand[1].card_id==ids[draws[2]],"generated cards equal sequential RNG draws in entry order across both sides");}
}
void test_damage_group_area_barrier(){ // DG01/02/07/08
 auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));s.set_trace_enabled(true);
 const int older=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5),newer=TestAccess::minion(s,0,"TEST_TAKES_DAMAGE",1,5);
 TestAccess::area(s,{TestAccess::damage_packet(s,-1,newer,3),TestAccess::damage_packet(s,-1,older,3)});
 check(TestAccess::player(s,0).board[0].health==2&&TestAccess::player(s,1).board[0].health==2,"DG01 all area mutations precede reactions");
 check(TestAccess::player(s,0).hand.size()==1&&TestAccess::player(s,1).hand.size()==1,"DG01 independent controllers receive results");
 const auto barrier=damage_trace_index(s,"GROUP_MUTATIONS_COMPLETE group=1");
 const auto first=damage_trace_index(s,"DAMAGE_REACTION sequence=1 group=1");
 check(barrier<first,"DG01 ordered shared group mutation barrier precedes reaction");
 check(damage_trace_index(s,"consumer="+std::to_string(older))<damage_trace_index(s,"consumer="+std::to_string(newer)),"DG02 entry sequence overrides board/side input order");
 check(TestAccess::next_group(s)==2&&TestAccess::next_damage(s)==3,"DG01 group and event identities are independent");
 for(int prevention=0;prevention<3;++prevention){
  auto g=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));const int a=TestAccess::minion(g,0,"TEST_TAKES_DAMAGE",1,5),b=TestAccess::minion(g,1,"TEST_TAKES_DAMAGE",1,5);
  if(prevention!=1)TestAccess::set_divine_shield(g,0,0,true);else TestAccess::set_immune(g,0,0,true);
  TestAccess::area(g,{TestAccess::damage_packet(g,-1,a,prevention==2?0:3),TestAccess::damage_packet(g,-1,b,prevention==2?0:3)});
  check(TestAccess::player(g,0).board[0].health==5&&TestAccess::player(g,0).hand.empty(),"DG07/08 prevention emits no successful reaction");
  check(TestAccess::player(g,1).board[0].health==(prevention==2?5:2)&&TestAccess::player(g,1).hand.size()==(prevention==2?0:1),"DG07/08 prevented packet does not cancel other targets");
  check(TestAccess::player(g,0).board[0].divine_shield==(prevention==2),"DG08 zero leaves shield; positive packet consumes it");
 }
}
void test_damage_group_lethal_batches(){ // DG03/04/05/06/09
 for(int survivors=0;survivors<=1;++survivors){
  auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));const int a=TestAccess::minion(s,0,"TEST_TAKES_DAMAGE",1,2),b=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,survivors?5:2);auto before=s.clone();
  check(fails_closed(s,[&]{TestAccess::area(s,{TestAccess::damage_packet(s,-1,a,3),TestAccess::damage_packet(s,-1,b,3)});}),"DG03/04 lethal self consumer remains unsupported");
  check(TestAccess::player(s,0).board[0].health==-1&&TestAccess::player(s,1).board[0].health==(survivors?2:-1),"DG03/04 all mutations retained before lethal rejection");
  check(TestAccess::rng_values(s,2)==TestAccess::rng_values(*before,2)&&TestAccess::frame_depth(s)==0,"DG03/04 no generation RNG; safe unwind");
 }
 auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));const int mortal=TestAccess::minion(s,0,"TEST_FILLER",1,2),consumer=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);
 TestAccess::area(s,{TestAccess::damage_packet(s,-1,mortal,3),TestAccess::damage_packet(s,-1,consumer,3)});
 check(TestAccess::player(s,0).board[0].health==-1&&TestAccess::player(s,1).hand.size()==1,"DG05 mortal ordinary entity remains through surviving reaction");TestAccess::stabilize(s);check(TestAccess::player(s,0).board.empty(),"DG05 outer boundary owns removal");
 auto batch=game();TestAccess::reset(batch);batch.set_trace_enabled(true);
 for(int p=0;p<2;++p)TestAccess::deck(batch,p,{"TEST_FILLER","TEST_FILLER"});
 const int a=TestAccess::minion(batch,0,"TEST_DEATHRATTLE_DRAW_TWO",2,2),b=TestAccess::minion(batch,1,"TEST_DEATHRATTLE_DRAW_TWO",2,2);
 TestAccess::area(batch,{TestAccess::damage_packet(batch,-1,a,3),TestAccess::damage_packet(batch,-1,b,3)});
 check(TestAccess::player(batch,0).hand.empty()&&TestAccess::player(batch,1).hand.empty()&&TestAccess::player(batch,0).board.size()==1,"DG06 no Deathrattle or removal at group close");
 TestAccess::stabilize(batch);check(TestAccess::player(batch,0).hand.size()==2&&TestAccess::player(batch,1).hand.size()==2,"DG06 both FIFO Deathrattles follow batch removal");
 check(damage_trace_index(batch,"DEATH entity="+std::to_string(b))<damage_trace_index(batch,"DEATHRATTLE_RESOLVE"),"DG06 all deaths precede first Deathrattle");
 auto r=game();TestAccess::reset(r);const int old=TestAccess::minion(r,0,"CORE_ULD_723",1,1),ordinary=TestAccess::minion(r,1,"TEST_FILLER",1,4);
 TestAccess::area(r,{TestAccess::damage_packet(r,-1,old,3),TestAccess::damage_packet(r,-1,ordinary,3)});
 check(TestAccess::player(r,0).board[0].entity_id==old&&TestAccess::player(r,0).board[0].health==-2,"DG09 Reborn cannot enter during group");TestAccess::stabilize(r);
 check(TestAccess::player(r,0).board[0].entity_id!=old&&TestAccess::player(r,0).board[0].health==1&&!TestAccess::player(r,0).board[0].reborn&&TestAccess::player(r,1).board[0].health==1,"DG09 outer guarded Reborn keeps fresh identity");
}
void test_damage_group_nested_state(){ // DG10/11/12; test-only scripted continuation
 auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));s.set_trace_enabled(true);
 const int source=TestAccess::minion(s,0,"TEST_FILLER",1,1),a=TestAccess::minion(s,0,"TEST_TAKES_DAMAGE",1,5),b=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);
 const auto parent=TestAccess::open_area(s,{TestAccess::damage_packet(s,source,a,1),TestAccess::damage_packet(s,source,b,1)});
 TestAccess::next_damage_event(s,parent);
 // Inject child work at the parent's reaction continuation, without a new card mechanic.
 TestAccess::packet_damage(s,-1,source,1,DamageKind::Effect);
 check(TestAccess::frame_depth(s)==1&&TestAccess::player(s,0).board[0].health==0,"DG10 child mortal source remains in Play");
 TestAccess::close_area(s,parent);
 check(damage_trace_index(s,"GROUP_COMPLETE group=2")<damage_trace_index(s,"DAMAGE_REACTION sequence=2 group=1"),"DG11 child completes before next parent event");
 check(TestAccess::player(s,0).hand.size()==1&&TestAccess::player(s,1).hand.size()==1,"DG10 started group preserves captured source attribution");TestAccess::stabilize(s);
 check(TestAccess::player(s,0).board.size()==1,"DG10 source removal only at outer phase");
 for(int change=0;change<5;++change){
  auto g=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));const int x=TestAccess::minion(g,0,"TEST_TAKES_DAMAGE",1,5),y=TestAccess::minion(g,1,"TEST_TAKES_DAMAGE",1,5);
  const auto f=TestAccess::open_area(g,{TestAccess::damage_packet(g,-1,x,1),TestAccess::damage_packet(g,-1,y,1)});TestAccess::next_damage_event(g,f);auto rng=TestAccess::diagnostic_snapshot(g); // Privileged diagnostic copy, not resumable clone.
  if(change==0)TestAccess::player(g,1).board.clear();
  if(change==1)TestAccess::set_controller(g,1,0,0);
  if(change==2)TestAccess::set_silenced(g,1,0,true);
  if(change==3)TestAccess::player(g,1).board[0].card_id="CATA_488t";
  if(change==4)++TestAccess::player(g,1).board[0].activation_sequence;
  check(fails_closed(g,[&]{TestAccess::next_damage_event(g,f);}),"DG12 changed consumer rejected at event dispatch");
  check(TestAccess::rng_values(g,1)==TestAccess::rng_values(rng,1),"DG12 rejected identity consumes no next-generation RNG");
 }
 auto invalid_source=game();TestAccess::reset(invalid_source);const int src=TestAccess::minion(invalid_source,0,"TEST_FILLER",1,4),dst=TestAccess::minion(invalid_source,1,"TEST_FILLER",1,4);
 const auto f=TestAccess::open_area(invalid_source,{TestAccess::damage_packet(invalid_source,src,dst,1)});TestAccess::player(invalid_source,0).board.clear();
 check(fails_closed(invalid_source,[&]{TestAccess::next_damage_event(invalid_source,f);}),"DG10 actual source removal is guarded");
 auto later=game();TestAccess::reset(later);const int first=TestAccess::minion(later,1,"TEST_FILLER",1,5),second=TestAccess::minion(later,1,"TEST_FILLER",1,5);
 const auto pending=TestAccess::open_area(later,{TestAccess::damage_packet(later,-1,first,1,DamageKind::Spell),TestAccess::damage_packet(later,-1,second,1,DamageKind::Spell)});
 TestAccess::next_damage_event(later,pending);TestAccess::minion(later,0,"CATA_487",1,4);
 TestAccess::close_area(later,pending);
 check(TestAccess::player(later,0).board[0].attack==3,"event-start eligibility is rebuilt for a later event, not frozen for whole spell");
 check(TestAccess::player(later,0).board[0].health==4,"new entity never joins the parent area's frozen target set");
}
void test_damage_group_preflight_and_budgets(){ // DG18/23 and suspension/quiescence
 for(int bad=0;bad<4;++bad){
  auto s=game();TestAccess::reset(s);const int target=TestAccess::minion(s,0,"TEST_FILLER",1,5);auto before=s.clone();auto packet=TestAccess::damage_packet(s,-1,target,1);
  if(bad==0)packet.amount=-1;if(bad==1)packet.target.entry_sequence++;if(bad==2)packet.source_controller=3;
  check(fails_closed(s,[&]{TestAccess::area(s,bad==3?std::vector<TestAccess::DamagePacket>{packet,packet}:std::vector<TestAccess::DamagePacket>{packet});}),"DG23 invalid preflight is fail closed");
  check(TestAccess::player(s,0).board[0].health==5&&TestAccess::rng_values(s,1)==TestAccess::rng_values(*before,1),"DG23 no damage or RNG before invalid preflight");
 }
 auto modifier=game();TestAccess::reset(modifier);const int seer=TestAccess::minion(modifier,0,"END_022",1,3),enemy=TestAccess::minion(modifier,1,"TEST_FILLER",1,5);
 check(fails_closed(modifier,[&]{TestAccess::area(modifier,{TestAccess::damage_packet(modifier,-1,seer,1,DamageKind::Spell),TestAccess::damage_packet(modifier,-1,enemy,1,DamageKind::Spell)});}),"DG18 conditional own Spell Damage rejects at P0");
 check(TestAccess::player(modifier,0).board[0].health==3&&TestAccess::player(modifier,1).board[0].health==5,"DG18 no area damage precedes rejection");
 for(bool depth:{false,true}){auto s=game();TestAccess::reset(s);const int target=TestAccess::minion(s,0,"TEST_FILLER",1,5);if(depth){for(int i=0;i<64;++i)TestAccess::open_area(s,{TestAccess::damage_packet(s,-1,target,0)});}else TestAccess::damage_budget(s,4096);
  check(fails_closed(s,[&]{TestAccess::area(s,{TestAccess::damage_packet(s,-1,target,1)});}),"DG23 explicit depth/work exhaustion");check(TestAccess::player(s,0).board[0].health==5,"DG23 exhaustion cannot silently truncate damage");}
 auto q=game();TestAccess::reset(q);const int id=TestAccess::minion(q,0,"TEST_FILLER",1,5);const auto frame=TestAccess::open_area(q,{TestAccess::damage_packet(q,-1,id,0)});
 for(int access=0;access<4;++access){bool refused=false;try{if(access==0)(void)q.clone();if(access==1)(void)q.observation();if(access==2)(void)q.legal_actions();if(access==3)q.begin_prototype_choice();}catch(const UnsupportedSimulationError&){refused=true;}check(refused,"active frame cannot cross public boundary");}
 TestAccess::close_area(q,frame);check(q.clone()->is_valid(),"DG22 quiescent clone remains available");
 auto choice=game();TestAccess::reset(choice);const int c=TestAccess::minion(choice,0,"TEST_FILLER",1,5);TestAccess::damage_choice(choice);check(fails_closed(choice,[&]{TestAccess::packet_damage(choice,-1,c,1,DamageKind::Effect);}),"active Choice cannot enter damage work");
 auto death=game();TestAccess::reset(death);const int d=TestAccess::minion(death,0,"TEST_FILLER",1,5);TestAccess::open_area(death,{TestAccess::damage_packet(death,-1,d,0)});check(fails_closed(death,[&]{TestAccess::stabilize(death);}),"P5 requires no active damage frame");
}
void test_damage_group_rng_and_clone(){ // DG20/21/22
 for(int failure=0;failure<3;++failure){
  auto pool=test_pool({"TEST_FIRE_SPELL"},failure==0?PoolMembershipStatus::Candidate:PoolMembershipStatus::MembershipReviewed);auto s=game_with_pool(pool);if(failure==1)for(int i=0;i<10;++i)TestAccess::hand(s,0,"TEST_FILLER");
  const int a=TestAccess::minion(s,0,"TEST_TAKES_DAMAGE",1,5),b=TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);auto rng=s.clone();
  if(failure==2){TestAccess::player(s,0).board[0].card_id="CATA_488t";} // Its unchanged production candidate pool is not loaded.
  check(fails_closed(s,[&]{TestAccess::area(s,{TestAccess::damage_packet(s,-1,a,3),TestAccess::damage_packet(s,-1,b,3)});}),"DG20 unavailable/candidate/full-hand reaction fails");
  check(TestAccess::player(s,0).board[0].health==2&&TestAccess::player(s,1).board[0].health==2,"DG20 failure preserves whole area's mutations");check(TestAccess::rng_values(s,2)==TestAccess::rng_values(*rng,2),"DG20 fail before this generation RNG");
  const auto reason=s.unsupported_outcome();bool refused=false;try{(void)s.clone();}catch(const UnsupportedSimulationError&){refused=true;}check(refused&&s.unsupported_outcome()==reason,"invalid clone rejected without replacing first reason");
 }
 auto malformed=test_pool({"TEST_FIRE_SPELL"});++malformed.count;bool bad_manifest=false;try{(void)game_with_pool(malformed);}catch(const std::invalid_argument&){bad_manifest=true;}check(bad_manifest,"DG20 count/hash manifest rejected before session RNG");
 auto sampled=game_with_pool(test_pool({"TEST_UNSUPPORTED_FIRE_SPELL"}));const int a=TestAccess::minion(sampled,0,"TEST_TAKES_DAMAGE",1,5);auto rng=sampled.clone();TestAccess::bounded_values(*rng,{1});
 check(fails_closed(sampled,[&]{TestAccess::area(sampled,{TestAccess::damage_packet(sampled,-1,a,1)});}),"DG21 sampled unsupported outcome invalidates without reroll");check(TestAccess::rng_values(sampled,3)==TestAccess::rng_values(*rng,3),"DG21 consumed sampler RNG preserved");
 auto good=game_with_pool(test_pool({"TEST_FIRE_SPELL","CORE_CS2_029"}));good.set_trace_enabled(true);const int x=TestAccess::minion(good,0,"TEST_TAKES_DAMAGE",1,5),y=TestAccess::minion(good,1,"TEST_TAKES_DAMAGE",1,5);auto clone=good.clone();
 for(auto* session:{&good,clone.get()})TestAccess::area(*session,{TestAccess::damage_packet(*session,-1,y,1),TestAccess::damage_packet(*session,-1,x,1)});
 check(good.diagnostic_trace()==clone->diagnostic_trace()&&TestAccess::player(good,0).hand[0].card_id==TestAccess::player(*clone,0).hand[0].card_id,"DG22 deterministic complete trace and generated state");check(TestAccess::rng_values(good,4)==TestAccess::rng_values(*clone,4),"DG22 deterministic future RNG");
}
void test_damage_group_raincaller_accounting(){ // DG24
 auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);TestAccess::minion(s,0,"CATA_487",1,4);const int a=TestAccess::minion(s,1,"TEST_FILLER",1,8),b=TestAccess::minion(s,1,"TEST_FILLER",1,8);
 TestAccess::area(s,{TestAccess::damage_packet(s,-1,a,3,DamageKind::Spell),TestAccess::damage_packet(s,-1,b,3,DamageKind::Spell)});
 check(TestAccess::player(s,0).spell_damage_dealt_this_turn==6&&TestAccess::player(s,0).board[0].attack==3,"DG24 scalar accounting per packet; attack once per turn");check(damage_trace_index(s,"GROUP_MUTATIONS_COMPLETE")<damage_trace_index(s,"SPELL_DAMAGE_TRIGGER"),"DG24 Raincaller leaves scalar mutation path");
 TestAccess::packet_damage(s,-1,a,1,DamageKind::Effect);check(TestAccess::player(s,0).spell_damage_dealt_this_turn==6,"DG24 Effect is not DirectSpell");
 TestAccess::player(s,1).armor=5;TestAccess::packet_damage(s,-1,2,3,DamageKind::Spell,DamageAttribution::DirectSpell);check(TestAccess::player(s,1).armor==2&&TestAccess::player(s,0).spell_damage_dealt_this_turn==9,"DG24 armor-only successful spell damage counted");
 auto mixed=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));TestAccess::minion(mixed,0,"CATA_487",1,4);const int consumer=TestAccess::minion(mixed,1,"TEST_TAKES_DAMAGE",1,5);
 TestAccess::packet_damage(mixed,-1,consumer,1,DamageKind::Spell);
 check(mixed.is_valid()&&TestAccess::player(mixed,0).board[0].attack==3&&TestAccess::player(mixed,1).board[0].health==4&&TestAccess::player(mixed,1).hand.size()==1,"DG24 generation and Raincaller attack gain are independent: one packet performs both");
}
void test_damage_group_guarded_callers(){ // DG25/26; Bookkeeper/Runes full control retained in existing suite
 auto s=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));TestAccess::minion(s,0,"TEST_FILLER",1,5,true);TestAccess::minion(s,1,"TEST_TAKES_DAMAGE",1,5);auto before=s.clone();auto actions=s.legal_actions();const auto attack=std::find_if(actions.begin(),actions.end(),[](const auto& a){return a.type==ActionType::Attack;});check(attack!=actions.end(),"DG26 reactive combat setup is legal");
 check(fails_closed(s,[&]{s.apply_action(*attack);}),"DG26 reactive combat requires separate ordering contract");check(TestAccess::player(s,0).board[0].health==5&&TestAccess::player(s,1).board[0].health==5&&TestAccess::rng_values(s,1)==TestAccess::rng_values(*before,1),"DG26 guarded combat mutates neither damage packet nor RNG");
 auto runes=game_with_pool(test_pool({"TEST_FIRE_SPELL"}));TestAccess::secret(runes,1,"CORE_LOOT_101");TestAccess::hand(runes,0,"TEST_TAKES_DAMAGE");check(fails_closed(runes,[&]{runes.apply_action(play_hand(runes,0));}),"DG25 reactive Runes compound remains guarded");check(TestAccess::player(runes,0).board[0].health==5,"DG25 compound guard precedes minion damage");
 auto rain=game();TestAccess::reset(rain);TestAccess::secret(rain,1,"CORE_LOOT_101");TestAccess::minion(rain,1,"CATA_487",1,4);TestAccess::hand(rain,0,"TEST_FILLER");TestAccess::player(rain,0).hand[0].divine_shield=true;
 rain.apply_action(play_hand(rain,0));
 check(rain.is_valid()&&TestAccess::player(rain,0).hero_health==26&&!TestAccess::player(rain,0).board[0].divine_shield&&TestAccess::player(rain,0).board[0].health==2,"DG25 Runes keeps pre-hit excess with Shield and a Raincaller on the Secret side");
 check(TestAccess::player(rain,1).board[0].attack==3&&TestAccess::player(rain,1).spell_damage_dealt_this_turn==4,"DG25 only the successful excess packet is counted and triggers Raincaller once");
}
void test_damage_group_steps_and_missiles(){ // DG15/16/17/19; current mortality guards retained
 auto s=game();TestAccess::reset(s);s.set_trace_enabled(true);const int seer=TestAccess::minion(s,0,"END_022",1,3);TestAccess::minion(s,1,"TEST_FILLER",1,4);TestAccess::hand(s,0,"CATA_485");s.apply_action(play(s,seer));check(TestAccess::player(s,0).board[0].health==1&&TestAccess::player(s,1).board[0].health==1,"DG15 Sleet current Spell Damage at second instruction");check(damage_trace_index(s,"GROUP_COMPLETE group=1")<damage_trace_index(s,"GROUP_MUTATIONS_COMPLETE group=2"),"DG15 first group completes before second instruction");
 for(bool aura:{false,true}){auto g=game();TestAccess::reset(g);const int target=TestAccess::minion(g,aura?0:1,aura?"END_022":"TEST_FILLER",1,2);TestAccess::hand(g,0,"CATA_485");check(fails_closed(g,[&]{g.apply_action(play(g,target));}),"DG16/17 pending mortality guard not relaxed");}
 bool saw_mortal_hit=false;
 for(std::uint64_t seed=0;seed<32&&!saw_mortal_hit;++seed){auto g=game();TestAccess::reset(g);TestAccess::rng_seed(g,seed);g.set_trace_enabled(true);const int target=TestAccess::minion(g,1,"TEST_FILLER",1,1);TestAccess::hand(g,0,"EX1_277");g.apply_action(play(g));int hits=0,barriers=0;for(const auto& row:g.diagnostic_trace()){if(row.find("DAMAGE source=")==0&&row.find("target="+std::to_string(target)+" ")!=std::string::npos)++hits;if(row.find("GROUP_MUTATIONS_COMPLETE")==0)++barriers;}check(hits<=1&&barriers==3,"DG19 live missiles exclude mortal targets, complete three packet groups");saw_mortal_hit=hits==1;}
 check(saw_mortal_hit,"DG19 deterministic seed sweep reaches mortality control");
}
void run_damage_group_family(){test_damage_group_failure_funnel();test_damage_group_remediation_semantics();test_damage_group_area_barrier();test_damage_group_lethal_batches();test_damage_group_nested_state();test_damage_group_preflight_and_budgets();test_damage_group_rng_and_clone();test_damage_group_raincaller_accounting();test_damage_group_guarded_callers();test_damage_group_steps_and_missiles();}
}
