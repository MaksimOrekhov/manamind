#include "manaengine/engine.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <iomanip>
#include <sstream>
#include <unordered_set>

namespace manaengine {
namespace {
constexpr std::array<std::uint32_t, 64> kSha256 = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};

std::string sha256(const std::string& input) {
 std::vector<std::uint8_t> bytes(input.begin(),input.end());
 const std::uint64_t bit_length=static_cast<std::uint64_t>(bytes.size())*8;
 bytes.push_back(0x80);while(bytes.size()%64!=56)bytes.push_back(0);
 for(int shift=56;shift>=0;shift-=8)bytes.push_back(static_cast<std::uint8_t>(bit_length>>shift));
 std::array<std::uint32_t,8> h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
 for(std::size_t block=0;block<bytes.size();block+=64){
  std::array<std::uint32_t,64> w{};
  for(std::size_t i=0;i<16;++i){const auto j=block+i*4;w[i]=(std::uint32_t(bytes[j])<<24)|(std::uint32_t(bytes[j+1])<<16)|(std::uint32_t(bytes[j+2])<<8)|bytes[j+3];}
  for(std::size_t i=16;i<64;++i){const auto s0=std::rotr(w[i-15],7)^std::rotr(w[i-15],18)^(w[i-15]>>3);const auto s1=std::rotr(w[i-2],17)^std::rotr(w[i-2],19)^(w[i-2]>>10);w[i]=w[i-16]+s0+w[i-7]+s1;}
  auto [a,b,c,d,e,f,g,hh]=h;
  for(std::size_t i=0;i<64;++i){const auto s1=std::rotr(e,6)^std::rotr(e,11)^std::rotr(e,25);const auto ch=(e&f)^((~e)&g);const auto t1=hh+s1+ch+kSha256[i]+w[i];const auto s0=std::rotr(a,2)^std::rotr(a,13)^std::rotr(a,22);const auto maj=(a&b)^(a&c)^(b&c);const auto t2=s0+maj;hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}
  h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
 }
 std::ostringstream out;out<<std::hex<<std::setfill('0');for(auto value:h)out<<std::setw(8)<<value;return out.str();
}
const char* predicate_name(PoolPredicateKind kind){switch(kind){case PoolPredicateKind::StandardSpellSchool:return "STANDARD_SPELL_SCHOOL";case PoolPredicateKind::StandardSpellBaseCost:return "STANDARD_SPELL_BASE_COST";}/* NF-133:0 */ throw UnsupportedSimulationError(FailureCode::INVARIANT_VIOLATION, "unknown pool predicate kind");}
const char* class_policy_name(PoolClassPolicy policy){switch(policy){case PoolClassPolicy::AnyClass:return "ANY_CLASS";case PoolClassPolicy::NonNeutralClass:return "NON_NEUTRAL_CLASS";}/* NF-133:1 */ throw UnsupportedSimulationError(FailureCode::INVARIANT_VIOLATION, "unknown pool class policy");}
const char* exclusion_name(PoolExclusionKind kind){switch(kind){case PoolExclusionKind::Quest:return "QUEST";case PoolExclusionKind::Rune:return "RUNE";case PoolExclusionKind::NonGeneratable:return "NON_GENERATABLE";case PoolExclusionKind::ClassPolicy:return "CLASS_POLICY";case PoolExclusionKind::NeutralPolicy:return "NEUTRAL_POLICY";case PoolExclusionKind::EventPolicy:return "EVENT_POLICY";case PoolExclusionKind::Alias:return "ALIAS";case PoolExclusionKind::Ban:return "BAN";case PoolExclusionKind::Other:return "OTHER";}/* NF-133:2 */ throw UnsupportedSimulationError(FailureCode::INVARIANT_VIOLATION, "unknown pool exclusion category");}
const char* exclusion_status_name(PoolExclusionStatus status){switch(status){case PoolExclusionStatus::ReviewedExcluded:return "REVIEWED_EXCLUDED";case PoolExclusionStatus::Unresolved:return "UNRESOLVED";}/* NF-133:3 */ throw UnsupportedSimulationError(FailureCode::INVARIANT_VIOLATION, "unknown pool exclusion status");}
}

std::string pool_membership_sha256(const std::vector<std::string>& ids){std::string canonical;for(const auto& id:ids){canonical+=id;canonical.push_back('\n');}return sha256(canonical);}

std::string pool_predicate_rules_fingerprint(const PoolManifest& m){
 std::ostringstream canonical;canonical<<"schema="<<m.schema_version<<"\ncontract="<<m.contract_version<<"\npool="<<m.pool_id<<"\nprofile="<<m.format_profile_id<<"\nas_of="<<m.as_of_date<<"\npredicate="<<predicate_name(m.predicate.kind)<<"\nschool="<<m.predicate.school<<"\nbase_cost="<<m.predicate.base_cost<<"\nclass_policy="<<class_policy_name(m.predicate.class_policy)<<"\nmetadata_id="<<m.metadata_snapshot_id<<"\nmetadata_sha256="<<m.metadata_snapshot_sha256<<"\nmembership="<<m.sorted_membership_sha256<<"\n";
 for(const auto& exclusion:m.exclusions){canonical<<"exclusion="<<exclusion_name(exclusion.category)<<"|"<<exclusion_status_name(exclusion.status)<<"|"<<exclusion.rationale<<"|"<<exclusion.evidence_ref<<"\n";for(const auto& id:exclusion.card_ids)canonical<<"id="<<id<<"\n";}
 return sha256(canonical.str());
}

void validate_pool_manifest(const PoolManifest& m){
 if(m.schema_version!=1)/* NF-131:0 */ throw std::invalid_argument("unknown pool manifest schema version");
 if(m.contract_version!=1)/* NF-131:1 */ throw std::invalid_argument("unknown pool manifest contract version");
 if(m.membership_status!=PoolMembershipStatus::Candidate&&m.membership_status!=PoolMembershipStatus::MembershipReviewed&&m.membership_status!=PoolMembershipStatus::ReviewedInferred)/* NF-131:2 */ throw std::invalid_argument("unknown pool membership status");
 if(m.pool_id.empty()||m.format_profile_id.empty()||m.as_of_date.empty()||m.metadata_snapshot_id.empty()||m.metadata_snapshot_sha256.size()!=64)/* NF-131:3 */ throw std::invalid_argument("pool manifest identity is incomplete");
 if(m.predicate.kind==PoolPredicateKind::StandardSpellSchool){if(m.predicate.school.empty()||m.predicate.base_cost!=-1||m.predicate.class_policy!=PoolClassPolicy::AnyClass)/* NF-131:4 */ throw std::invalid_argument("invalid Standard spell-school predicate parameters");}
 else if(m.predicate.kind==PoolPredicateKind::StandardSpellBaseCost){if(!m.predicate.school.empty()||m.predicate.base_cost<0||m.predicate.base_cost>10)/* NF-131:5 */ throw std::invalid_argument("invalid Standard spell base-cost predicate parameters");(void)class_policy_name(m.predicate.class_policy);}
 else /* NF-131:6 */ throw std::invalid_argument("unknown pool predicate kind");
 if(!std::is_sorted(m.card_ids.begin(),m.card_ids.end())||std::adjacent_find(m.card_ids.begin(),m.card_ids.end())!=m.card_ids.end())/* NF-131:7 */ throw std::invalid_argument("pool membership must be sorted and unique");
 if(m.count<0||static_cast<std::size_t>(m.count)!=m.card_ids.size())/* NF-131:8 */ throw std::invalid_argument("pool manifest count mismatch");
 if(m.sorted_membership_sha256!=pool_membership_sha256(m.card_ids))/* NF-131:9 */ throw std::invalid_argument("pool manifest membership hash mismatch");
 std::unordered_set<std::string> excluded;bool unresolved_exclusion=false;bool inferred_fire_evidence=false;
 for(const auto& exclusion:m.exclusions){(void)exclusion_name(exclusion.category);(void)exclusion_status_name(exclusion.status);if(exclusion.rationale.empty())/* NF-131:10 */ throw std::invalid_argument("pool exclusion rationale is required");if(!std::is_sorted(exclusion.card_ids.begin(),exclusion.card_ids.end())||std::adjacent_find(exclusion.card_ids.begin(),exclusion.card_ids.end())!=exclusion.card_ids.end())/* NF-131:11 */ throw std::invalid_argument("pool exclusion IDs must be sorted and unique");if(exclusion.status==PoolExclusionStatus::Unresolved)unresolved_exclusion=true;if(m.membership_status==PoolMembershipStatus::ReviewedInferred&&exclusion.status==PoolExclusionStatus::Unresolved&&exclusion.category==PoolExclusionKind::NonGeneratable&&exclusion.evidence_ref=="reports/manaengine_fire_pool_20261005/FIRE_POOL_RUNTIME_MEMBERSHIP_AUDIT.md")inferred_fire_evidence=true;if(exclusion.status==PoolExclusionStatus::ReviewedExcluded){for(const auto& id:exclusion.card_ids){if(std::binary_search(m.card_ids.begin(),m.card_ids.end(),id)||!excluded.insert(id).second)/* NF-131:12 */ throw std::invalid_argument("reviewed excluded identity conflicts with pool membership/ledger");}}}
 if(m.membership_status==PoolMembershipStatus::MembershipReviewed&&unresolved_exclusion)/* NF-131:13 */ throw std::invalid_argument("MEMBERSHIP_REVIEWED pool cannot contain unresolved exclusion rows");
 if(m.membership_status==PoolMembershipStatus::ReviewedInferred){if(!unresolved_exclusion||!inferred_fire_evidence||m.training_eligible)/* NF-131:14 */ throw std::invalid_argument("REVIEWED_INFERRED pool requires explicit unresolved membership evidence and cannot be training-eligible");if(m.pool_id!="fire_spell_standard_253932_inferred_v1"||m.format_profile_id!="standard_full_20261001_v1"||m.as_of_date!="2026-10-01"||m.metadata_snapshot_id!="data/cards/source_snapshots/cards_collectible_20261001_enUS.json"||m.metadata_snapshot_sha256!="d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930"||m.count!=33||m.sorted_membership_sha256!="480f5971bdf90a339f08142a9f2e47c7650be1ddd6973241960885b20b3e0e87"||m.predicate.kind!=PoolPredicateKind::StandardSpellSchool||m.predicate.school!="FIRE"||m.predicate.class_policy!=PoolClassPolicy::AnyClass)/* NF-131:15 */ throw std::invalid_argument("REVIEWED_INFERRED Fire pool has the wrong pinned build/snapshot identity or membership");}
 if(m.predicate_rules_fingerprint!=pool_predicate_rules_fingerprint(m))/* NF-131:16 */ throw std::invalid_argument("pool manifest predicate/rules fingerprint mismatch");
 if(m.training_eligible&&(m.membership_status!=PoolMembershipStatus::MembershipReviewed||m.dependency_status!=PoolDependencyStatus::DependencyClosed))/* NF-131:17 */ throw std::invalid_argument("training eligibility requires reviewed membership and dependency closure");
}
void validate_dark_gift_option_manifest(const DarkGiftOptionManifest& m){
 if(m.schema_version!=1||m.contract_version!=1)/* NF-132:0 */ throw std::invalid_argument("unknown Dark Gift manifest version");
 if(m.manifest_id.empty()||m.source_metadata_id.empty()||m.source_metadata_sha256.size()!=64)/* NF-132:1 */ throw std::invalid_argument("Dark Gift manifest source identity is incomplete");
 auto valid_ids=[](const std::vector<std::string>& ids){return !ids.empty()&&std::all_of(ids.begin(),ids.end(),[](const std::string& id){return !id.empty();})&&std::is_sorted(ids.begin(),ids.end())&&std::adjacent_find(ids.begin(),ids.end())==ids.end();};
 if(!valid_ids(m.candidate_option_ids)||!valid_ids(m.launch_reviewed_option_ids))/* NF-132:2 */ throw std::invalid_argument("Dark Gift option IDs must be sorted, unique and nonempty");
 if(m.candidate_option_ids.size()!=12||m.launch_reviewed_option_ids.size()!=10)/* NF-132:3 */ throw std::invalid_argument("Dark Gift candidate/launch-reviewed membership count mismatch");
 for(const auto& id:m.launch_reviewed_option_ids)if(!std::binary_search(m.candidate_option_ids.begin(),m.candidate_option_ids.end(),id))/* NF-132:4 */ throw std::invalid_argument("launch-reviewed Dark Gift option is not a candidate");
 if(m.candidate_membership_sha256!=pool_membership_sha256(m.candidate_option_ids)||m.launch_reviewed_membership_sha256!=pool_membership_sha256(m.launch_reviewed_option_ids))/* NF-132:5 */ throw std::invalid_argument("Dark Gift option membership hash mismatch");
 if(m.runtime_membership_status!=DarkGiftRuntimeMembershipStatus::Unresolved||m.sampler_status!=DarkGiftSamplerStatus::Unverified||m.training_eligible)/* NF-132:6 */ throw std::invalid_argument("Dark Gift runtime/sampler uncertainty cannot be promoted here");
}

} // namespace manaengine
