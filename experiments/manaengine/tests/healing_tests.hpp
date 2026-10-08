#pragma once

#include <optional>

// Healing pipeline v1 (ENGINE-PRIMITIVE-1). Expected values are written from the printed card text and the
// Hearthstone healing rules (per-packet additive bonus, own maximum Health), never read back from a declaration.
namespace manaengine {
namespace {
constexpr int hero0 = 1, hero1 = 2;  // entity handles of the two heroes

std::vector<CardDefinition> healing_definitions() {
  auto c = catalog();
  auto moonwell = def("EDR_476", "SPELL", 6, 0, 0, "EFFECT_COMPOSITION");
  moonwell.effects = {effect(EffectKind::Damage, TargetSelector::EnemyCharacters, 4),
                      effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 4)};
  c.push_back(moonwell);
  auto nova = def("CORE_CS1_112", "SPELL", 3, 0, 0, "EFFECT_COMPOSITION");
  nova.effects = {effect(EffectKind::Damage, TargetSelector::EnemyMinions, 2),
                  effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 2)};
  c.push_back(nova);
  auto potion = def("CORE_CFM_604", "SPELL", 4, 0, 0, "EFFECT_COMPOSITION");
  potion.effects = {effect(EffectKind::Heal, TargetSelector::ExplicitFriendlyCharacter, 12),
                    effect(EffectKind::Draw, TargetSelector::Self, 1)};
  c.push_back(potion);
  auto cleric = def("CATA_216", "MINION", 4, 4, 5, "EFFECT_COMPOSITION");
  cleric.battlecry = true;
  cleric.effects = {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 2)};
  c.push_back(cleric);
  // Independent second consumers of the same contracts (design evidence only, not Standard cards).
  auto bonus_one = def("TEST_HEAL_BONUS_ONE", "MINION", 1, 1, 1, "EFFECT_COMPOSITION");
  bonus_one.battlecry = true;
  bonus_one.effects = {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 1)};
  c.push_back(bonus_one);
  auto bonus_three = def("TEST_HEAL_BONUS_THREE", "SPELL", 1, 0, 0, "EFFECT_COMPOSITION");
  bonus_three.effects = {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 3),
                         effect(EffectKind::Draw, TargetSelector::Self, 1)};
  c.push_back(bonus_three);
  auto mend_all = def("TEST_MEND_ALL", "SPELL", 2, 0, 0, "EFFECT_COMPOSITION");
  mend_all.effects = {effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 3)};
  c.push_back(mend_all);
  auto ls_area = def("TEST_LIFESTEAL_AREA", "SPELL", 3, 0, 0, "EFFECT_COMPOSITION");
  ls_area.effects = {effect(EffectKind::Damage, TargetSelector::EnemyMinions, 2, true)};
  c.push_back(ls_area);
  auto scorch_then_mend = def("TEST_DAMAGE_THEN_HEAL", "SPELL", 3, 0, 0, "EFFECT_COMPOSITION");
  scorch_then_mend.effects = {effect(EffectKind::Damage, TargetSelector::AllCharacters, 3),
                              effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 2)};
  c.push_back(scorch_then_mend);
  auto mend_then_scorch = def("TEST_HEAL_THEN_DAMAGE", "SPELL", 3, 0, 0, "EFFECT_COMPOSITION");
  mend_then_scorch.effects = {effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 2),
                              effect(EffectKind::Damage, TargetSelector::AllCharacters, 3)};
  c.push_back(mend_then_scorch);
  auto ls_minion = def("TEST_LS_MINION", "MINION", 2, 3, 4);
  ls_minion.lifesteal = true;
  ls_minion.required_mechanics = {"LIFESTEAL"};
  c.push_back(ls_minion);
  return c;
}

GameSession healing_game(std::uint64_t seed = 7) {
  std::vector<std::string> deck(30, "TEST_FILLER");
  GameSession s(deck, deck, healing_definitions(), seed, false, "MAGE", "MAGE");
  TestAccess::reset(s);
  return s;
}

template <class F>
std::optional<FailureCode> failure_of(F&& action) {
  try { action(); } catch (const UnsupportedSimulationError& e) { return e.record().code; }
  return std::nullopt;
}

bool catalog_rejects(CardDefinition bad) {
  auto definitions = healing_definitions();
  definitions.push_back(std::move(bad));
  try { CardCatalog catalog_under_test(std::move(definitions)); } catch (const std::invalid_argument&) { return true; }
  return false;
}

CardDefinition healing_card(const std::string& id, std::vector<EffectStep> effects, const std::string& type = "SPELL") {
  auto d = def(id, type, 1, type == "MINION" ? 1 : 0, type == "MINION" ? 1 : 0, "EFFECT_COMPOSITION");
  d.effects = std::move(effects);
  return d;
}

// Fixture: player 0 hero 20, board A (health 2 of max 5) and B (2/2 undamaged); player 1 hero 30, C 1/3 and D 2/6.
struct HealingBoard { int a, b, c, d; };
HealingBoard healing_board(GameSession& s) {
  TestAccess::player(s, 0).hero_health = 20;
  HealingBoard board{};
  board.a = TestAccess::minion(s, 0, "TEST_FILLER", 3, 5);
  TestAccess::set_health(s, 0, 0, 2);
  board.b = TestAccess::minion(s, 0, "TEST_FILLER", 2, 2);
  board.c = TestAccess::minion(s, 1, "TEST_FILLER", 1, 3);
  board.d = TestAccess::minion(s, 1, "TEST_FILLER", 2, 6);
  return board;
}

Action end_turn_action(GameSession& s) {
  for (const auto& a : s.legal_actions()) if (a.type == ActionType::EndTurn) return a;
  throw std::runtime_error("end turn action not found");
}

void play_cleric(GameSession& s, int player) {
  TestAccess::active(s, player);
  TestAccess::player(s, player).mana = 10;
  TestAccess::hand(s, player, "CATA_216");
  const int index = static_cast<int>(TestAccess::player(s, player).hand.size()) - 1;
  s.apply_action(play_hand(s, index));
}

void test_healing_area_and_damage_order() {
  // H01 Moonwell: damage first (enemy hero 30 -> 26, C 3 -> -1 pending death, D 6 -> 2), then every friendly character heals 4.
  auto s = healing_game();
  const auto board = healing_board(s);
  TestAccess::hand(s, 0, "EDR_476");
  s.apply_action(play_hand(s, 0));
  check(TestAccess::player(s, 1).hero_health == 26, "H01 Moonwell damages the enemy hero by 4");
  check(TestAccess::player(s, 1).board.size() == 1 && TestAccess::player(s, 1).board[0].entity_id == board.d && TestAccess::player(s, 1).board[0].health == 2,
        "H01 enemy minion C dies after the spell and D keeps 2 Health");
  check(TestAccess::player(s, 0).hero_health == 24, "H01 friendly hero 20 -> 24");
  check(TestAccess::player(s, 0).board[0].health == 5, "H01 damaged friendly minion heals 2 -> 5 and stops at its own maximum Health (5, not 6)");
  check(TestAccess::player(s, 0).board[1].health == 2, "H01 an undamaged friendly minion is unchanged");
  check(TestAccess::player(s, 0).hero_health == 24 && TestAccess::player(s, 0).armor == 0, "H01 healing never creates armor");

  // H02 Holy Nova: enemy minions only (the enemy hero is untouched), friendly characters heal 2.
  auto n = healing_game();
  healing_board(n);
  TestAccess::hand(n, 0, "CORE_CS1_112");
  n.apply_action(play_hand(n, 0));
  check(TestAccess::player(n, 1).hero_health == 30, "H02 Holy Nova does not damage the enemy hero");
  check(TestAccess::player(n, 1).board.size() == 2 && TestAccess::player(n, 1).board[0].health == 1 && TestAccess::player(n, 1).board[1].health == 4, "H02 enemy minions take 2 (C 3 -> 1, D 6 -> 4)");
  check(TestAccess::player(n, 0).hero_health == 22 && TestAccess::player(n, 0).board[0].health == 4 && TestAccess::player(n, 0).board[1].health == 2,
        "H02 friendly hero 20 -> 22, damaged minion 2 -> 4, undamaged minion unchanged");

  // H03 fully healed characters: nothing changes and the hero stays at its maximum.
  auto full = healing_game();
  TestAccess::minion(full, 0, "TEST_FILLER", 1, 4);
  TestAccess::hand(full, 0, "EDR_476");
  full.apply_action(play_hand(full, 0));
  check(TestAccess::player(full, 0).hero_health == 30 && TestAccess::player(full, 0).board[0].health == 4, "H03 full Health is not exceeded");
  auto near = healing_game();
  TestAccess::player(near, 0).hero_health = 29;
  TestAccess::hand(near, 0, "EDR_476");
  near.apply_action(play_hand(near, 0));
  check(TestAccess::player(near, 0).hero_health == 30, "H03 hero 29 + 4 restores only the missing 1 (maximum 30)");

  // H04 order: Damage then Heal kills a 3-Health friendly minion before the Heal -> the Heal sees a pending death and fails closed
  // without any partial mutation; Heal then Damage is legal and the minion simply dies afterwards.
  auto bad = healing_game();
  TestAccess::minion(bad, 0, "TEST_FILLER", 1, 3);
  TestAccess::hand(bad, 0, "TEST_DAMAGE_THEN_HEAL");
  const auto code = failure_of([&] { bad.apply_action(play_hand(bad, 0)); });
  check(code && *code == FailureCode::HEAL_MORTALLY_WOUNDED_UNREVIEWED, "H04 Heal after damage that leaves a friendly minion pending death fails closed");
  check(TestAccess::player(bad, 0).hero_health == 27, "H04 the rejected Heal leaves the already-damaged hero at 27 (atomic: no partial heal)");
  check(!bad.is_valid(), "H04 the session is poisoned, not silently repaired");
  auto good = healing_game();
  const int friendly = TestAccess::minion(good, 0, "TEST_FILLER", 1, 5);
  TestAccess::set_health(good, 0, 0, 4);
  TestAccess::minion(good, 0, "TEST_FILLER", 1, 3);
  const int enemy = TestAccess::minion(good, 1, "TEST_FILLER", 1, 6);
  TestAccess::hand(good, 0, "TEST_HEAL_THEN_DAMAGE");
  good.apply_action(play_hand(good, 0));
  check(TestAccess::player(good, 0).hero_health == 27, "H04 Heal at full Health then 3 damage leaves the hero at 27");
  check(TestAccess::player(good, 0).board.size() == 1 && TestAccess::player(good, 0).board[0].entity_id == friendly && TestAccess::player(good, 0).board[0].health == 2,
        "H04 Heal first: 4 -> 5 (maximum) then damage 3 -> 2; the 3-Health minion dies after the spell");
  check(TestAccess::player(good, 1).board[0].entity_id == enemy && TestAccess::player(good, 1).board[0].health == 3 && TestAccess::player(good, 1).hero_health == 27,
        "H04 damage to ALL_CHARACTERS also hits the enemy side");
}

void test_healing_single_target_and_friendly_restriction() {
  auto s = healing_game();
  const auto board = healing_board(s);
  TestAccess::hand(s, 0, "CORE_CFM_604");
  TestAccess::deck(s, 0, {"TEST_FILLER"});
  std::set<int> targets;
  for (const auto& a : s.legal_actions()) if (a.type == ActionType::PlayCard) targets.insert(a.target_entity_id);
  check(targets == std::set<int>({hero0, board.a, board.b}), "H05 Greater Healing Potion may target only the caster's hero and minions");

  // Executing against an enemy handle is rejected as illegal input before any mutation.
  Action forged = play_card_on(s, "CORE_CFM_604", board.a);
  forged.target_entity_id = board.c;
  bool illegal = false;
  try { s.apply_action(forged); } catch (const std::exception&) { illegal = true; }
  check(illegal && s.is_valid() && TestAccess::player(s, 1).board.size() == 2, "H05 a forged enemy target is rejected without mutation");
  auto probe = healing_game();
  const auto probe_board = healing_board(probe);
  const auto execution = failure_of([&] { TestAccess::spell(probe, "CORE_CFM_604", probe_board.c); });
  check(execution && *execution == FailureCode::LEGALITY_EXECUTION_MISMATCH, "H05 the executor independently refuses a non-friendly target");

  s.apply_action(play_card_on(s, "CORE_CFM_604", board.a));
  check(TestAccess::player(s, 0).board[0].health == 5, "H06 restoring 12 stops at the minion's own maximum Health (5)");
  check(TestAccess::player(s, 0).hero_health == 20 && TestAccess::player(s, 0).hand.size() == 1, "H06 the other hero is untouched and exactly one card is drawn after the heal");
  auto hero_target = healing_game();
  TestAccess::player(hero_target, 0).hero_health = 15;
  TestAccess::hand(hero_target, 0, "CORE_CFM_604");
  TestAccess::deck(hero_target, 0, {"TEST_FILLER"});
  hero_target.apply_action(play_card_on(hero_target, "CORE_CFM_604", hero0));
  check(TestAccess::player(hero_target, 0).hero_health == 27, "H06 hero 15 + 12 = 27");
  auto capped = healing_game();
  TestAccess::player(capped, 0).hero_health = 25;
  TestAccess::hand(capped, 0, "CORE_CFM_604");
  TestAccess::deck(capped, 0, {"TEST_FILLER"});
  capped.apply_action(play_card_on(capped, "CORE_CFM_604", hero0));
  check(TestAccess::player(capped, 0).hero_health == 30, "H06 overhealing is capped at the hero maximum of 30");

  // H07 existing single-target Heal keeps its reviewed behaviour for either side while the caster has no bonus.
  auto flash = healing_game();
  const int foe = TestAccess::minion(flash, 1, "TEST_FILLER", 1, 6);
  TestAccess::set_health(flash, 1, 0, 2);
  TestAccess::hand(flash, 0, "CORE_AT_055");
  flash.apply_action(play_card_on(flash, "CORE_AT_055", foe));
  check(TestAccess::player(flash, 1).board[0].health == 6, "H07 Flash Heal on an enemy minion without any bonus still restores (2 + 5 capped at 6)");
}

void test_healing_bonus_stacking_ownership_and_persistence() {
  // H08 stacking: every source adds, and the total applies to each packet. Moonwell on a hero at 10 with Health to spare.
  const std::vector<std::pair<std::vector<std::string>, int>> setups = {
      {{}, 14}, {{"CATA_216"}, 16}, {{"CATA_216", "CATA_216"}, 18}, {{"CATA_216", "TEST_HEAL_BONUS_ONE"}, 17}};
  for (const auto& [sources, expected] : setups) {
    auto s = healing_game();
    TestAccess::player(s, 0).hero_health = 10;
    for (const auto& source : sources) {
      TestAccess::player(s, 0).mana = 10;
      TestAccess::hand(s, 0, source);
      s.apply_action(play_hand(s, static_cast<int>(TestAccess::player(s, 0).hand.size()) - 1));
    }
    TestAccess::player(s, 0).mana = 10;
    TestAccess::hand(s, 0, "EDR_476");
    s.apply_action(play_hand(s, static_cast<int>(TestAccess::player(s, 0).hand.size()) - 1));
    check(TestAccess::player(s, 0).hero_health == expected, "H08 Moonwell heals 4 plus the summed bonus (" + std::to_string(sources.size()) + " source(s))");
  }
  // A spell-based second consumer with a different amount and no minion involved.
  auto spell = healing_game();
  TestAccess::player(spell, 0).hero_health = 10;
  TestAccess::deck(spell, 0, {"TEST_FILLER"});
  TestAccess::hand(spell, 0, "TEST_HEAL_BONUS_THREE");
  spell.apply_action(play_hand(spell, 0));
  TestAccess::hand(spell, 0, "TEST_MEND_ALL");
  spell.apply_action(play_hand(spell, static_cast<int>(TestAccess::player(spell, 0).hand.size()) - 1));
  check(TestAccess::player(spell, 0).hero_health == 16, "H09 a +3 spell source gives 3 + 3 per packet");

  // H10 each packet gets the bonus: a hero and two damaged minions each gain 3 + 2.
  auto per_packet = healing_game();
  TestAccess::player(per_packet, 0).hero_health = 10;
  TestAccess::minion(per_packet, 0, "TEST_FILLER", 1, 9);
  TestAccess::set_health(per_packet, 0, 0, 1);
  TestAccess::minion(per_packet, 0, "TEST_FILLER", 1, 9);
  TestAccess::set_health(per_packet, 0, 1, 1);
  TestAccess::player(per_packet, 0).healing_bonus = 2;
  TestAccess::hand(per_packet, 0, "TEST_MEND_ALL");
  per_packet.apply_action(play_hand(per_packet, 0));
  check(TestAccess::player(per_packet, 0).hero_health == 15 && TestAccess::player(per_packet, 0).board[0].health == 6 && TestAccess::player(per_packet, 0).board[1].health == 6,
        "H10 every healed character receives base + bonus (5), not a single aggregate bonus");

  // H11 ownership: the opponent's bonus does not help the caster and the caster's bonus does not help the opponent.
  auto owner = healing_game();
  TestAccess::player(owner, 0).hero_health = 10;
  TestAccess::player(owner, 1).healing_bonus = 7;
  TestAccess::hand(owner, 0, "EDR_476");
  owner.apply_action(play_hand(owner, 0));
  check(TestAccess::player(owner, 0).hero_health == 14 && TestAccess::player(owner, 1).healing_bonus == 7 && TestAccess::player(owner, 0).healing_bonus == 0,
        "H11 only the caster's bonus counts; the opponent's bonus is neither used nor consumed");
  check(TestAccess::player(owner, 1).hero_health == 26, "H11 Moonwell damage still targets the opponent's hero");
  auto second = healing_game();
  TestAccess::active(second, 1);
  TestAccess::player(second, 1).hero_health = 10;
  TestAccess::player(second, 1).healing_bonus = 2;
  TestAccess::player(second, 0).hero_health = 30;
  TestAccess::hand(second, 1, "EDR_476");
  second.apply_action(play_hand(second, 0));
  check(TestAccess::player(second, 1).hero_health == 16 && TestAccess::player(second, 0).hero_health == 26, "H11 the second seat uses its own bonus and damages the first seat's hero");

  // H12 persistence: the bonus belongs to the player, not to the minion. It survives the Cleric's death and a turn change.
  auto persistent = healing_game();
  TestAccess::deck(persistent, 0, std::vector<std::string>(4, "TEST_FILLER"));
  TestAccess::deck(persistent, 1, std::vector<std::string>(4, "TEST_FILLER"));
  play_cleric(persistent, 0);
  check(TestAccess::player(persistent, 0).healing_bonus == 2, "H12 Cleansing Cleric grants +2");
  TestAccess::player(persistent, 0).board.front().health = 0;
  TestAccess::stabilize(persistent);
  check(TestAccess::player(persistent, 0).board.empty() && TestAccess::player(persistent, 0).healing_bonus == 2, "H12 the bonus survives the Cleric's death");
  persistent.apply_action(end_turn_action(persistent));
  persistent.apply_action(end_turn_action(persistent));
  check(TestAccess::player(persistent, 0).healing_bonus == 2, "H12 the bonus survives full turn cycles");
  TestAccess::player(persistent, 0).hero_health = 10;
  TestAccess::hand(persistent, 0, "CORE_AT_055");
  persistent.apply_action(play_card_on(persistent, "CORE_AT_055", hero0));
  check(TestAccess::player(persistent, 0).hero_health == 17, "H12 Flash Heal (an existing consumer) now restores 5 + 2");

  // H13 silence/removal of the source minion is irrelevant, and a clone branches independently.
  auto branch_parent = healing_game();
  auto branch = branch_parent.clone();
  play_cleric(*branch, 0);
  check(TestAccess::player(*branch, 0).healing_bonus == 2 && TestAccess::player(branch_parent, 0).healing_bonus == 0, "H13 clones never share the bonus");

  // H14 bound: the total is capped; exceeding it fails closed.
  auto bound = healing_game();
  TestAccess::player(bound, 0).healing_bonus = 998;
  TestAccess::hand(bound, 0, "CATA_216");
  bound.apply_action(play_hand(bound, 0));
  check(TestAccess::player(bound, 0).healing_bonus == 1000, "H14 the reviewed bound itself is allowed");
  auto over = healing_game();
  TestAccess::player(over, 0).healing_bonus = 999;
  TestAccess::hand(over, 0, "CATA_216");
  const auto code = failure_of([&] { over.apply_action(play_hand(over, 0)); });
  check(code && *code == FailureCode::NUMERIC_RANGE_VIOLATION, "H14 a total above 1000 fails closed");
}

void test_healing_lifesteal_shares_the_pipeline() {
  // H15 three separate damage packets: each is its own healing packet. Without a bonus, 3 x 2 = 6.
  auto plain = healing_game();
  TestAccess::player(plain, 0).hero_health = 10;
  for (int i = 0; i < 3; ++i) TestAccess::minion(plain, 1, "TEST_FILLER", 1, 6);
  TestAccess::hand(plain, 0, "TEST_LIFESTEAL_AREA");
  plain.apply_action(play_hand(plain, 0));
  check(TestAccess::player(plain, 0).hero_health == 16, "H15 three Lifesteal packets of 2 heal 6 in total");
  // With +2: each packet restores 4 (12 in total), not 6 + 2.
  auto boosted = healing_game();
  TestAccess::player(boosted, 0).hero_health = 10;
  TestAccess::player(boosted, 0).healing_bonus = 2;
  for (int i = 0; i < 3; ++i) TestAccess::minion(boosted, 1, "TEST_FILLER", 1, 6);
  TestAccess::hand(boosted, 0, "TEST_LIFESTEAL_AREA");
  boosted.apply_action(play_hand(boosted, 0));
  check(TestAccess::player(boosted, 0).hero_health == 22, "H15 the bonus applies to each Lifesteal packet (3 x (2 + 2))");
  // H16 cap in the middle of a group: 28 + 4 caps at 30, the later packets restore nothing.
  auto capped = healing_game();
  TestAccess::player(capped, 0).hero_health = 28;
  TestAccess::player(capped, 0).healing_bonus = 2;
  for (int i = 0; i < 3; ++i) TestAccess::minion(capped, 1, "TEST_FILLER", 1, 6);
  TestAccess::hand(capped, 0, "TEST_LIFESTEAL_AREA");
  capped.apply_action(play_hand(capped, 0));
  check(TestAccess::player(capped, 0).hero_health == 30, "H16 Lifesteal healing is capped at the hero maximum");
  // H17 Lifesteal heals the damage dealer's hero even for the second seat, and uses that seat's bonus only.
  auto seat = healing_game();
  TestAccess::active(seat, 1);
  TestAccess::player(seat, 1).hero_health = 10;
  TestAccess::player(seat, 0).healing_bonus = 9;
  TestAccess::player(seat, 1).healing_bonus = 1;
  TestAccess::minion(seat, 0, "TEST_FILLER", 1, 6);
  TestAccess::hand(seat, 1, "TEST_LIFESTEAL_AREA");
  seat.apply_action(play_hand(seat, 0));
  check(TestAccess::player(seat, 1).hero_health == 13 && TestAccess::player(seat, 0).hero_health == 30, "H17 a Lifesteal packet heals its own controller by 2 + 1");

  // H18 combat Lifesteal (minion flag) goes through the same path.
  auto combat = healing_game();
  TestAccess::player(combat, 0).hero_health = 20;
  TestAccess::player(combat, 0).healing_bonus = 2;
  const int attacker = TestAccess::minion(combat, 0, "TEST_LS_MINION", 3, 4, true);
  TestAccess::player(combat, 0).board.back().lifesteal = true;
  const int victim = TestAccess::minion(combat, 1, "TEST_FILLER", 1, 6);
  combat.apply_action(attack(combat, attacker, victim));
  check(TestAccess::player(combat, 0).hero_health == 25 && TestAccess::player(combat, 1).board[0].health == 3, "H18 a combat Lifesteal packet of 3 heals 3 + 2");

  // H19 a packet absorbed by Divine Shield deals no damage, so Lifesteal (and the bonus) produce nothing.
  auto shielded = healing_game();
  TestAccess::player(shielded, 0).hero_health = 10;
  TestAccess::player(shielded, 0).healing_bonus = 2;
  const int shield = TestAccess::minion(shielded, 1, "TEST_FILLER", 1, 6);
  TestAccess::set_divine_shield(shielded, 1, 0, true);
  (void)shield;
  TestAccess::hand(shielded, 0, "TEST_LIFESTEAL_AREA");
  shielded.apply_action(play_hand(shielded, 0));
  check(TestAccess::player(shielded, 0).hero_health == 10, "H19 a packet absorbed by Divine Shield deals no damage, so it heals nothing (the bonus needs a packet)");
}

void test_healing_fail_closed_and_declaration_validation() {
  // H20 a bonus holder healing a character it does not control is an unreviewed combination.
  auto cross = healing_game();
  TestAccess::player(cross, 0).healing_bonus = 2;
  TestAccess::player(cross, 1).hero_health = 20;
  TestAccess::hand(cross, 0, "CORE_AT_055");
  const auto code = failure_of([&] { cross.apply_action(play_card_on(cross, "CORE_AT_055", hero1)); });
  check(code && *code == FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED, "H20 healing the opponent with a bonus fails closed");
  check(TestAccess::player(cross, 1).hero_health == 20 && !cross.is_valid(), "H20 the failure is atomic and poisons the session");
  auto followup = healing_game();
  const int minion = TestAccess::minion(followup, 1, "TEST_FILLER", 1, 5);
  TestAccess::player(followup, 1).hero_health = 20;
  TestAccess::player(followup, 0).healing_bonus = 2;
  TestAccess::hand(followup, 0, "CATA_303");
  const auto followup_code = failure_of([&] { followup.apply_action(play_card_on(followup, "CATA_303", minion)); });
  check(followup_code && *followup_code == FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED, "H20 the existing damage follow-up uses the same pipeline and the same fail-closed rule");
  auto legacy = healing_game();
  const int legacy_minion = TestAccess::minion(legacy, 1, "TEST_FILLER", 1, 5);
  TestAccess::player(legacy, 1).hero_health = 20;
  TestAccess::hand(legacy, 0, "CATA_303");
  legacy.apply_action(play_card_on(legacy, "CATA_303", legacy_minion));
  check(TestAccess::player(legacy, 1).hero_health == 25, "H20 without a bonus Purifying Breath restores the enemy hero by exactly 5");

  // H21 declaration validation: every malformed combination is rejected at catalog load.
  check(catalog_rejects(healing_card("BAD_1", {effect(EffectKind::Damage, TargetSelector::AllFriendlyCharacters, 2)})), "H21 friendly area selector requires Heal");
  check(catalog_rejects(healing_card("BAD_2", {effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 0)})), "H21 Heal needs a positive amount");
  check(catalog_rejects(healing_card("BAD_3", {effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 1001)})), "H21 Heal amount is bounded");
  check(catalog_rejects(healing_card("BAD_4", {effect(EffectKind::Heal, TargetSelector::AllCharacters, 2)})), "H21 Heal may not use other area selectors");
  check(catalog_rejects(healing_card("BAD_5", {effect(EffectKind::GrantHealingBonus, TargetSelector::ExplicitCharacter, 2)})), "H21 bonus grant requires SELF");
  check(catalog_rejects(healing_card("BAD_6", {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 0)})), "H21 bonus grant needs a positive amount");
  check(catalog_rejects(healing_card("BAD_7", {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 101)})), "H21 bonus grant amount is bounded");
  check(catalog_rejects(healing_card("BAD_8", {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 2, true)})), "H21 bonus grant carries no other step fields");
  check(catalog_rejects(healing_card("BAD_9", {effect(EffectKind::Heal, TargetSelector::ExplicitFriendlyCharacter, 3, true)})), "H21 Heal carries no Lifesteal field");
  check(catalog_rejects(healing_card("BAD_10", {effect(EffectKind::Heal, TargetSelector::ExplicitFriendlyCharacter, 3), effect(EffectKind::Damage, TargetSelector::ExplicitEnemyCharacter, 1)})),
        "H21 a friendly explicit target cannot share a card with another explicit target");
  auto choose = healing_card("BAD_11", {});
  choose.choose_one_a = {effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 2)};
  choose.choose_one_b = {effect(EffectKind::Draw, TargetSelector::Self, 1)};
  check(catalog_rejects(choose), "H21 the new selectors are not valid inside Choose One");
  auto choose_bonus = healing_card("BAD_12", {});
  choose_bonus.choose_one_a = {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 2)};
  choose_bonus.choose_one_b = {effect(EffectKind::Draw, TargetSelector::Self, 1)};
  check(catalog_rejects(choose_bonus), "H21 the bonus grant is not valid inside Choose One");
  auto not_composition = def("BAD_13", "MINION", 1, 1, 1, "TARGET_DAMAGE", 1);
  not_composition.effects = {effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 2)};
  check(catalog_rejects(not_composition), "H21 the bonus grant needs EFFECT_COMPOSITION");
  auto bad_followup = healing_card("BAD_14", {effect(EffectKind::Damage, TargetSelector::ExplicitMinion, 2)});
  bad_followup.damage_outcome_condition = DamageOutcomeCondition::MortallyWounded;
  bad_followup.damage_outcome_followup = DamageOutcomeFollowup::HealEnemyHero;
  bad_followup.damage_outcome_amount = 0;
  check(catalog_rejects(bad_followup), "H21 HEAL_ENEMY_HERO requires a positive amount");
  check(!catalog_rejects(healing_card("OK_1", {effect(EffectKind::Heal, TargetSelector::ExplicitFriendlyCharacter, 3)})), "H21 the valid friendly explicit form loads");
  check(!catalog_rejects(healing_card("OK_2", {effect(EffectKind::Heal, TargetSelector::AllFriendlyCharacters, 1), effect(EffectKind::GrantHealingBonus, TargetSelector::Self, 100)}, "MINION")),
        "H21 the valid area and bonus forms load together");

  // H22 stale or malformed packets never reach a mutation.
  auto invalid = healing_game();
  const auto invalid_code = failure_of([&] { TestAccess::heal(invalid, 0, {hero0}, 0); });
  check(invalid_code && *invalid_code == FailureCode::INVARIANT_VIOLATION, "H22 a non-positive base amount is an invariant violation");
  auto stale = healing_game();
  const auto stale_code = failure_of([&] { TestAccess::heal(stale, 0, {9999}, 2); });
  check(stale_code && *stale_code == FailureCode::LEGALITY_EXECUTION_MISMATCH, "H22 a target that is no longer a character is refused");
}

void test_healing_regressions() {
  // H23 the Mage hero power and ordinary damage are unchanged by a held bonus.
  auto s = healing_game();
  TestAccess::player(s, 0).healing_bonus = 5;
  for (const auto& a : s.legal_actions()) {
    if (a.type == ActionType::HeroPower && a.target_entity_id == hero1) { s.apply_action(a); break; }
  }
  check(TestAccess::player(s, 1).hero_health == 29 && TestAccess::player(s, 0).hero_health == 30 && TestAccess::player(s, 0).healing_bonus == 5,
        "H23 Fireblast still deals exactly 1 and never heals anyone");
  // H24 Mend (restore to full) is independent of the bonus.
  auto mend = healing_game();
  TestAccess::player(mend, 0).healing_bonus = 4;
  const int hurt = TestAccess::minion(mend, 0, "TEST_FILLER", 1, 6);
  TestAccess::set_health(mend, 0, 0, 1);
  TestAccess::hand(mend, 0, "CATA_302");
  TestAccess::deck(mend, 0, {"TEST_FILLER"});
  mend.apply_action(play_card_on(mend, "CATA_302", hurt));
  check(TestAccess::player(mend, 0).board[0].health == 6, "H24 Restore-to-full is unchanged");
  // H25 a bonus-free game behaves exactly as before for the pre-existing consumers.
  auto flash = healing_game();
  TestAccess::player(flash, 0).hero_health = 20;
  TestAccess::hand(flash, 0, "CORE_AT_055");
  flash.apply_action(play_card_on(flash, "CORE_AT_055", hero0));
  check(TestAccess::player(flash, 0).hero_health == 25, "H25 Flash Heal without a bonus restores exactly 5");
  // H26 a clone made after healing replays identically (state completeness).
  auto source = healing_game();
  TestAccess::player(source, 0).hero_health = 10;
  TestAccess::player(source, 0).healing_bonus = 2;
  auto copy = source.clone();
  TestAccess::hand(source, 0, "EDR_476");
  TestAccess::hand(*copy, 0, "EDR_476");
  source.apply_action(play_hand(source, 0));
  copy->apply_action(play_hand(*copy, 0));
  check(TestAccess::player(source, 0).hero_health == TestAccess::player(*copy, 0).hero_health && TestAccess::player(source, 0).hero_health == 16, "H26 clones replay the same healing");
  // H27 the public observation is unchanged by the pipeline: hero Health is exported, the bonus is not an invented active effect.
  const auto view = source.observation(0);
  check(view.self_player.hero_health == 16 && view.self_player.active_effects.empty(), "H27 no active effect is fabricated for the healing bonus");
  source.validate_invariants();
}

void test_healing_observation_and_restore_to_full() {
  // H28 the persistent bonus is public: both seats export their own exact value (0 is a known "no bonus").
  auto s = healing_game();
  TestAccess::player(s, 0).healing_bonus = 2;
  TestAccess::player(s, 1).healing_bonus = 5;
  const auto first = s.observation(0), second = s.observation(1);
  check(first.self_player.healing_bonus == 2 && first.opponent.healing_bonus == 5, "H28 observation exports SELF and OPPONENT bonuses");
  check(second.self_player.healing_bonus == 5 && second.opponent.healing_bonus == 2, "H28 the other perspective swaps them");
  auto none = healing_game();
  check(none.observation(0).self_player.healing_bonus == 0 && none.observation(0).opponent.healing_bonus == 0, "H28 a state without a bonus exports a known 0");
  check(none.observation(0).self_player.healing_bonus != first.self_player.healing_bonus, "H28 states with different bonuses export different observations");
  // Playing the Cleric changes the exported value of its controller only.
  auto played = healing_game();
  play_cleric(played, 0);
  check(played.observation(0).self_player.healing_bonus == 2 && played.observation(0).opponent.healing_bonus == 0, "H28 the Cleric changes only its controller's exported bonus");

  // H29 Mend (HEAL_MINION_TO_FULL) restores through the shared pipeline: own minion, with and without a bonus.
  for (const int bonus : {0, 4}) {
    auto m = healing_game();
    TestAccess::player(m, 0).healing_bonus = bonus;
    const int own = TestAccess::minion(m, 0, "TEST_FILLER", 1, 7);
    TestAccess::set_health(m, 0, 0, 2);
    TestAccess::hand(m, 0, "CATA_302");
    TestAccess::deck(m, 0, {"TEST_FILLER"});
    m.set_trace_enabled(true);
    m.apply_action(play_card_on(m, "CATA_302", own));
    check(TestAccess::player(m, 0).board[0].health == 7 && TestAccess::player(m, 0).hand.size() == 1, "H29 restore-to-full reaches the minion's own maximum and then draws");
    const auto& trace = m.diagnostic_trace();
    check(std::any_of(trace.begin(), trace.end(), [](const std::string& row) { return row.find("HEAL controller=0") != std::string::npos && row.find("restored=5") != std::string::npos; }),
          "H29 the restoration is one healing packet of exactly the missing 5 Health");
  }
  // H30 an opposing minion: the result is full Health whatever the bonus (the packet already equals the missing Health).
  for (const int bonus : {0, 3}) {
    auto m = healing_game();
    TestAccess::player(m, 0).healing_bonus = bonus;
    const int foe = TestAccess::minion(m, 1, "TEST_FILLER", 1, 6);
    TestAccess::set_health(m, 1, 0, 1);
    TestAccess::hand(m, 0, "CATA_302");
    TestAccess::deck(m, 0, {"TEST_FILLER"});
    m.apply_action(play_card_on(m, "CATA_302", foe));
    check(m.is_valid() && TestAccess::player(m, 1).board[0].health == 6, "H30 restoring an enemy minion to full is independent of the caster's bonus");
  }
  // H31 undamaged targets produce no healing packet; buffed maximum Health is respected; pending death still fails closed.
  auto idle = healing_game();
  const int whole = TestAccess::minion(idle, 0, "TEST_FILLER", 1, 4);
  TestAccess::hand(idle, 0, "CATA_302");
  TestAccess::deck(idle, 0, {"TEST_FILLER"});
  idle.set_trace_enabled(true);
  idle.apply_action(play_card_on(idle, "CATA_302", whole));
  const auto& idle_trace = idle.diagnostic_trace();
  check(TestAccess::player(idle, 0).board[0].health == 4 && std::none_of(idle_trace.begin(), idle_trace.end(), [](const std::string& row) { return row.find("HEAL controller=") != std::string::npos; }),
        "H31 an undamaged minion receives no healing packet");
  auto dying = healing_game();
  const int doomed = TestAccess::minion(dying, 1, "TEST_FILLER", 1, 5);
  TestAccess::hand(dying, 0, "CATA_302");
  TestAccess::deck(dying, 0, {"TEST_FILLER"});
  TestAccess::set_health(dying, 1, 0, 0);
  const auto mortal = failure_of([&] { TestAccess::spell(dying, "CATA_302", doomed); });
  check(mortal && *mortal == FailureCode::HEAL_MORTALLY_WOUNDED_UNREVIEWED, "H31 a minion pending death cannot be restored");
}

void run_healing_family() {
  current_native_group = "healing_pipeline_v1";
  test_healing_area_and_damage_order();
  test_healing_single_target_and_friendly_restriction();
  test_healing_bonus_stacking_ownership_and_persistence();
  test_healing_lifesteal_shares_the_pipeline();
  test_healing_fail_closed_and_declaration_validation();
  test_healing_regressions();
  test_healing_observation_and_restore_to_full();
}
}  // namespace
}  // namespace manaengine
