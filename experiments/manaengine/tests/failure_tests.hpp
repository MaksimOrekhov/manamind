// Phase 4K.1b: production failure funnel, explicit codes and payload identity.
namespace {
template<class F> FailureRecord expect_failure(GameSession& s,FailureCode code,F&& operation){
 try{operation();}catch(const UnsupportedSimulationError& e){
  check(e.record().code==code,"typed failure exact code");
  check(e.record().kind()==failure_kind_of(code),"kind derived from code");
  check(s.failure().has_value()&&*s.failure()==e.record(),"thrown payload equals effective stored payload");
  check(!s.is_valid()&&s.unsupported_outcome()==std::optional<std::string>{e.what()},"compatibility detail and validity");
  return e.record();
 }
 check(false,"expected typed failure");return {};
}
void test_typed_native_failure_v1(){
 // T01/T02/T04/T05/T18: every code reaches the same production funnel without text classification.
 for(int value=1;value<=57;++value){auto s=game();TestAccess::reset(s);const auto code=static_cast<FailureCode>(value);
  const auto record=expect_failure(s,code,[&]{TestAccess::guarded(s,[&]{TestAccess::reject(s,code,"identical misleading diagnostic");});});
  check(std::string(failure_code_id(code))!="UNKNOWN_FAILURE_CODE","code table total");
  check(record.detail=="identical misleading diagnostic","detail untouched");
 }
 // T02/T03/T07: actual generation predicates and unsupported samples, with wrapper provenance.
 for(int mode=0;mode<3;++mode){auto pool=test_pool({mode==2?"TEST_UNSUPPORTED_FIRE_SPELL":"TEST_FIRE_SPELL"},mode==0?PoolMembershipStatus::Candidate:PoolMembershipStatus::MembershipReviewed);
  auto s=game_with_pool(pool);if(mode==1)for(int i=0;i<10;++i)TestAccess::hand(s,0,"TEST_FILLER");auto shadow=s.clone();if(mode==2)TestAccess::bounded_values(*shadow,{1});
  const auto code=mode==0?FailureCode::POOL_MEMBERSHIP_CANDIDATE_ONLY:mode==1?FailureCode::GENERATION_HAND_FULL_ORDER_UNREVIEWED:FailureCode::UNSUPPORTED_GENERATED_CARD;
  expect_failure(s,code,[&]{TestAccess::guarded(s,[&]{TestAccess::generate(s,0,pool.pool_id);});});
  check(TestAccess::rng_values(s,2)==TestAccess::rng_values(*shadow,2),"generation consumes only admitted sample, no reroll");
 }
 auto reaction=game_with_pool(test_pool({"TEST_FIRE_SPELL"},PoolMembershipStatus::Candidate));const int consumer=TestAccess::minion(reaction,0,"TEST_TAKES_DAMAGE",1,5);
 auto reaction_record=expect_failure(reaction,FailureCode::POOL_MEMBERSHIP_CANDIDATE_ONLY,[&]{TestAccess::guarded(reaction,[&]{TestAccess::packet_damage(reaction,-1,consumer,1,DamageKind::Effect);});});
 check(reaction_record.context.find("damage_group.reaction")!=std::string::npos&&TestAccess::frame_depth(reaction)==0,"typed reaction code survives wrapper and frame cleanup");
 auto mutation=game();TestAccess::reset(mutation);const int broken=TestAccess::minion(mutation,1,"TEST_FILLER",1,5);TestAccess::player(mutation,1).board[0].card_id="MISSING_CATALOG_ROW";
 auto mutation_record=expect_failure(mutation,FailureCode::CATALOG_REFERENCE_MISSING,[&]{TestAccess::guarded(mutation,[&]{TestAccess::packet_damage(mutation,-1,broken,1,DamageKind::Effect);});});
 check(mutation_record.context.find("damage_group.mutation")!=std::string::npos&&TestAccess::frame_depth(mutation)==0,"typed mutation code survives wrapper and frame cleanup");
 // T04: all three real budget guards are distinguishable and preserve effective records.
 for(int mode=0;mode<3;++mode){auto s=game();TestAccess::reset(s);const int target=TestAccess::minion(s,0,"TEST_FILLER",1,5);
  if(mode==0)TestAccess::damage_budget(s,4096);
  if(mode==1)for(int i=0;i<64;++i)TestAccess::open_area(s,{TestAccess::damage_packet(s,-1,target,0)});
  const auto code=mode==0?FailureCode::DAMAGE_WORK_BUDGET_EXCEEDED:mode==1?FailureCode::DAMAGE_DEPTH_BUDGET_EXCEEDED:FailureCode::DAMAGE_PACKET_BUDGET_EXCEEDED;
  expect_failure(s,code,[&]{TestAccess::guarded(s,[&]{if(mode==0)TestAccess::consume_work(s);else TestAccess::area(s,std::vector<TestAccess::DamagePacket>(mode==2?4097:1,TestAccess::damage_packet(s,-1,target,0)));});});
  check(TestAccess::frame_depth(s)==0&&TestAccess::player(s,0).board[0].health==5,"budget never truncates valid damage");
 }
 // NF-103 audited split: zero activation is structural; controller movement is unresolved rules.
 for(bool structural:{false,true}){auto s=game();TestAccess::reset(s);const int target=TestAccess::minion(s,0,"TEST_FILLER",1,5);
  if(structural)TestAccess::player(s,0).board[0].activation_sequence=0;else TestAccess::player(s,0).board[0].controller=1;
  expect_failure(s,structural?FailureCode::INVARIANT_VIOLATION:FailureCode::CONTROL_CHANGE_UNREVIEWED,[&]{TestAccess::guarded(s,[&]{TestAccess::packet_damage(s,-1,target,1,DamageKind::Effect);});});
 }
 // T17: a subsequent defect upgrades a soft coverage failure and retains its cause.
 auto upgrade=game();TestAccess::reset(upgrade);
 auto record=expect_failure(upgrade,FailureCode::UNEXPECTED_EXCEPTION,[&]{TestAccess::guarded(upgrade,[&]{
  TestAccess::record(upgrade,FailureCode::UNSUPPORTED_GENERATED_CARD,"first coverage cause");throw std::logic_error("original logic detail");});});
 check(record.context.find("UNSUPPORTED_GENERATED_CARD")!=std::string::npos&&record.context.find("first coverage cause")!=std::string::npos,"upgrade keeps prior coverage cause");
 check(record.detail.find("original logic detail")!=std::string::npos&&record.context.find("logic_error")!=std::string::npos,"std type and what survive conversion");
 const auto first_code=upgrade.failure()->code;const auto first_detail=upgrade.failure()->detail;
 TestAccess::record(upgrade,FailureCode::UNSUPPORTED_CARD_ENTERED_HAND,"later coverage cause");
 check(upgrade.failure()->code==first_code&&upgrade.failure()->detail==first_detail,"defect never downgraded");
 check(upgrade.failure()->context.find("later coverage cause")!=std::string::npos,"suppressed later cause remains diagnostic");
 // T06/T20: unknown and legacy exceptions are defects.
 auto unknown=game();TestAccess::reset(unknown);expect_failure(unknown,FailureCode::UNKNOWN_EXCEPTION,[&]{TestAccess::guarded(unknown,[]{throw 7;});});
 auto legacy=game();TestAccess::reset(legacy);expect_failure(legacy,FailureCode::LEGACY_UNTYPED,[&]{TestAccess::guarded(legacy,[]{throw UnsupportedSimulationError("legacy detail");});});
 // T16: the real C++ exception propagates while state is poisoned.
 auto resource=game();TestAccess::reset(resource);bool memory=false;
 try{TestAccess::guarded(resource,[&]{TestAccess::record(resource,FailureCode::POOL_IDENTITY_NOT_LOADED,"pool first");throw std::bad_alloc();});}catch(const std::bad_alloc&){memory=true;}
 check(memory&&!resource.is_valid()&&resource.failure()->code==FailureCode::RESOURCE_EXHAUSTED,"bad_alloc remains resource exception with defect poison");
 check(resource.failure()->context.find("pool first")!=std::string::npos,"resource upgrade retains preceding cause");
 // T09: every guarded accessor echoes the exact effective record, including context.
 for(int accessor=0;accessor<8;++accessor)expect_failure(upgrade,first_code,[&]{
  switch(accessor){case 0:(void)upgrade.observation();break;case 1:(void)upgrade.clone();break;case 2:(void)upgrade.legal_actions();break;
  case 3:(void)upgrade.result();break;case 4:(void)upgrade.is_complete();break;case 5:(void)upgrade.needs_choice();break;
  case 6:(void)upgrade.choice_options();break;default:upgrade.begin_prototype_choice();break;}
 });
 // T22: test-only validation is typed; production does not invoke it.
 for(int mode=0;mode<3;++mode){auto s=game();TestAccess::reset(s);TestAccess::hand(s,0,"TEST_FILLER");TestAccess::hand(s,0,"TEST_FILLER");TestAccess::invariant_corruption(s,mode);
  bool typed=false;try{s.validate_invariants();}catch(const UnsupportedSimulationError& e){typed=e.record().code==FailureCode::INVARIANT_VIOLATION;}
  check(typed&&s.is_valid(),"test-only const validator throws typed defect without mutating state");
 }
 // T08: active unsupported hand enumeration is typed and non-poisoning.
 auto unsupported_defs=catalog();auto unsupported=def("TEST_ENUM_UNSUPPORTED","MINION",1,1,1);unsupported.support_state="UNSUPPORTED";unsupported_defs.push_back(unsupported);
 std::vector<std::string> deck(30,"TEST_FILLER");GameSession enumeration(deck,deck,unsupported_defs,123,false,"MAGE","MAGE");TestAccess::reset(enumeration);TestAccess::hand(enumeration,0,"TEST_ENUM_UNSUPPORTED");
 bool enum_typed=false;try{(void)enumeration.legal_actions();}catch(const UnsupportedSimulationError& e){enum_typed=e.record().code==FailureCode::UNSUPPORTED_CARD_IN_ACTIVE_HAND;}
 check(enum_typed&&enumeration.is_valid(),"enumeration unavailable stays non-poisoning");
 // T06: supported LOCATION / no spell dispatcher are defects (old false negatives).
 for(bool location:{false,true}){auto defs=catalog();auto bad=def("TEST_MISSING_DISPATCH",location?"LOCATION":"SPELL",1,0,0,location?"NONE":"NEXT_DEMON_DISCOUNT");bad.support_state=location?"VERIFIED_VANILLA":"SUPPORTED";defs.push_back(bad);
  GameSession s(deck,deck,defs,123,false,"MAGE","MAGE");TestAccess::reset(s);TestAccess::hand(s,0,"TEST_MISSING_DISPATCH");
  expect_failure(s,FailureCode::MISSING_DISPATCH_HANDLER,[&]{s.apply_action(play(s));});
 }
}
}
