// Test-only pybind target: exercises the production funnel, never shipped in manaengine_native.
#include "manaengine/engine.hpp"
#include <pybind11/pybind11.h>
#include <memory>
namespace py=pybind11;
namespace manaengine {
struct TestAccess {
 static void probe(GameSession& s,const std::string& mode){s.execute_guarded([&]{
  s.record_failure({FailureCode::UNSUPPORTED_GENERATED_CARD,"earlier soft failure",{}});
  if(mode=="bad_alloc")throw std::bad_alloc();
  if(mode=="std_exception")throw std::logic_error("original std detail");
  if(mode=="unknown")throw 7;
  if(mode=="legacy")throw UnsupportedSimulationError("legacy detail");
  throw UnsupportedSimulationError(FailureCode::DAMAGE_WORK_BUDGET_EXCEEDED,"budget detail");
 });}
 static std::size_t frames(const GameSession& s){return s.state_.damage_frames.size();}
};
}
using namespace manaengine;
namespace {
std::unique_ptr<GameSession> last;
py::dict snapshot(){py::dict d;if(last&&last->failure()){const auto& f=*last->failure();d["kind"]=failure_kind_id(f.kind());d["code"]=failure_code_id(f.code);d["detail"]=f.detail;d["context"]=f.context;d["valid"]=last->is_valid();d["frames"]=TestAccess::frames(*last);}return d;}
void exercise(const std::string& mode){CardDefinition filler;filler.card_id="TEST_FILLER";filler.card_type="MINION";filler.attack=1;filler.health=1;filler.support_state="VERIFIED_VANILLA";filler.rules_contract_reviewed=true;
 CardDefinition power;power.card_id="HERO_08bp";power.card_type="HERO_POWER";power.ability="TARGET_DAMAGE";power.damage=1;power.cost=2;power.rules_contract_reviewed=true;power.support_state="SUPPORTED";
 const std::vector<std::string> deck(30,"TEST_FILLER");last=std::make_unique<GameSession>(deck,deck,std::vector<CardDefinition>{filler,power},31,false,"MAGE","MAGE");
 try{TestAccess::probe(*last,mode);}catch(const UnsupportedSimulationError&){return;}
}
}
PYBIND11_MODULE(manaengine_failure_probes,m){m.def("exercise",&exercise);m.def("snapshot",&snapshot);}
