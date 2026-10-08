#pragma once

#include "manaengine/hero_power.hpp"

#include <array>
#include <optional>

// Hero Power v1 (ENGINE-GATE-0). Expected values are written from the printed Hero Power texts
// (Fireblast: 1 damage; Lesser Heal: restore 2; Steady Shot: 2 damage to the enemy hero; Armor Up!: gain 2 Armor),
// the 2-Mana cost and the once-per-turn rule, never read back from a declaration.
namespace manaengine {
namespace {
const std::array<std::string, 4> hp_classes = {"MAGE", "PRIEST", "HUNTER", "WARRIOR"};
std::string hp_power_of(const std::string& player_class) {
  if (player_class == "MAGE") return "HERO_08bp";
  if (player_class == "PRIEST") return "HERO_09bp";
  if (player_class == "HUNTER") return "HERO_05bp";
  return "HERO_01bp";
}

std::vector<CardDefinition> hero_power_definitions() {
  auto c = catalog();  // HERO_08bp keeps its pre-gate TARGET_DAMAGE encoding here (normalised by the catalog).
  auto make = [&](const std::string& id, const std::string& player_class, EffectStep step) {
    auto power = def(id, "HERO_POWER", 2, 0, 0, "EFFECT_COMPOSITION");
    power.card_class = player_class;
    power.effects = {step};
    c.push_back(power);
  };
  make("HERO_09bp", "PRIEST", effect(EffectKind::Heal, TargetSelector::ExplicitCharacter, 2));
  make("HERO_05bp", "HUNTER", effect(EffectKind::Damage, TargetSelector::EnemyHero, 2));
  make("HERO_01bp", "WARRIOR", effect(EffectKind::GainArmor, TargetSelector::Self, 2));
  // Design evidence for extensibility (not Standard cards): new powers are declarations, not session code.
  auto friendly_heal = def("TEST_POWER_FRIENDLY_HEAL", "HERO_POWER", 1, 0, 0, "EFFECT_COMPOSITION");
  friendly_heal.effects = {effect(EffectKind::Heal, TargetSelector::ExplicitFriendlyCharacter, 3)};
  c.push_back(friendly_heal);
  auto armor_power = def("TEST_POWER_ARMOR_THREE", "HERO_POWER", 3, 0, 0, "EFFECT_COMPOSITION");
  armor_power.effects = {effect(EffectKind::GainArmor, TargetSelector::Self, 3)};
  c.push_back(armor_power);
  // A replaced/unreviewed power stand-in: declared but UNSUPPORTED.
  auto replaced = def("TEST_POWER_REPLACED", "HERO_POWER", 2, 0, 0, "EFFECT_COMPOSITION");
  replaced.support_state = "UNSUPPORTED";
  replaced.effects = {effect(EffectKind::Damage, TargetSelector::EnemyHero, 9)};
  c.push_back(replaced);
  auto spell_damage = def("TEST_SPELL_POWER_TWO", "MINION", 1, 1, 3, "DEATHRATTLE_DRAW");  // unconditional Spell Damage +2 (as Bloodmage's +1)
  spell_damage.spell_damage = 2;
  spell_damage.deathrattle_draw_count = 1;
  c.push_back(spell_damage);
  return c;
}

GameSession hp_game(const std::string& first, const std::string& second, std::uint64_t seed = 11) {
  std::vector<std::string> deck(30, "TEST_FILLER");
  GameSession s(deck, deck, hero_power_definitions(), seed, false, first, second);
  TestAccess::reset(s);  // reset empties the decks; refill them so turn changes do not cause fatigue damage
  for (int player = 0; player < 2; ++player) TestAccess::deck(s, player, std::vector<std::string>(20, "TEST_FILLER"));
  return s;
}

std::vector<Action> hp_actions(const GameSession& s) {
  std::vector<Action> out;
  for (const auto& a : s.legal_actions()) if (a.type == ActionType::HeroPower) out.push_back(a);
  return out;
}

std::set<int> hp_targets(const GameSession& s) {
  std::set<int> out;
  for (const auto& a : hp_actions(s)) out.insert(a.target_entity_id);
  return out;
}

Action hp_action(const GameSession& s, int target = -1) {
  for (const auto& a : hp_actions(s)) if (a.target_entity_id == target) return a;
  throw std::runtime_error("hero power action not found");
}

template <class F>
bool hp_invalid_argument(F&& operation) {
  try { operation(); } catch (const std::invalid_argument&) { return true; }
  return false;
}

std::optional<FailureCode> hp_ctor_failure(const std::string& first, const std::string& second, std::vector<CardDefinition> definitions) {
  std::vector<std::string> deck(30, "TEST_FILLER");
  try { GameSession s(deck, deck, std::move(definitions), 3, false, first, second); } catch (const UnsupportedSimulationError& e) { return e.record().code; }
  return std::nullopt;
}

void test_hero_power_identity_and_observation() {
  // HP01: every supported pairing starts with the reviewed base power of each seat and exports it from both perspectives.
  for (const auto& first : hp_classes) for (const auto& second : hp_classes) {
    auto s = hp_game(first, second);
    const auto seat0 = s.observation(0), seat1 = s.observation(1);
    check(seat0.self_player.hero_power && seat0.self_player.hero_power->card_id == hp_power_of(first), "HP01 SELF power of seat 0 is the " + first + " base power");
    check(seat0.opponent.hero_power && seat0.opponent.hero_power->card_id == hp_power_of(second), "HP01 OPPONENT power of seat 0 is the " + second + " base power");
    check(seat1.self_player.hero_power && seat1.self_player.hero_power->card_id == hp_power_of(second), "HP01 SELF power of seat 1 is the " + second + " base power");
    check(seat1.opponent.hero_power && seat1.opponent.hero_power->card_id == hp_power_of(first), "HP01 OPPONENT power of seat 1 is the " + first + " base power");
    check(seat0.self_player.hero_power->card_type == "HERO_POWER" && seat0.self_player.hero_power->current_cost == 2 && seat0.self_player.hero_power->cost == 2, "HP01 power exports type and 2-Mana cost");
    check(seat0.self_player.hero_power_ready && seat0.opponent.hero_power_ready && seat1.self_player.hero_power_ready, "HP01 fresh powers are ready for both seats");
    check(seat0.self_player.player_class == first && seat0.opponent.player_class == second, "HP01 class export is unchanged");
  }
  // HP02: unknown or unsupported classes stay rejected with the class code, in either seat, also next to a supported class.
  for (const std::string& bad : {"WARLOCK", "SHAMAN", "UNKNOWN_CLASS", "NEUTRAL", "mage", "Priest", ""}) {
    check(hp_ctor_failure(bad, "MAGE", hero_power_definitions()) == FailureCode::UNSUPPORTED_HERO_CLASS, "HP02 unsupported first class " + bad);
    check(hp_ctor_failure("PRIEST", bad, hero_power_definitions()) == FailureCode::UNSUPPORTED_HERO_CLASS, "HP02 supported class next to unsupported " + bad);
  }
  check(hp_ctor_failure("PRIEST", "WARLOCK", hero_power_definitions()) == FailureCode::UNSUPPORTED_HERO_CLASS, "HP02 Priest vs Warlock is rejected because Warlock's power is unreviewed");
  // HP03: a supported class needs a reviewed, supported catalog definition of its starting power.
  auto without_priest = hero_power_definitions();
  without_priest.erase(std::remove_if(without_priest.begin(), without_priest.end(), [](const CardDefinition& d) { return d.card_id == "HERO_09bp"; }), without_priest.end());
  check(hp_ctor_failure("PRIEST", "MAGE", without_priest) == FailureCode::UNSUPPORTED_HERO_POWER, "HP03 missing catalog definition of the starting power is typed UNSUPPORTED_HERO_POWER");
  check(!hp_ctor_failure("MAGE", "MAGE", without_priest), "HP03 a catalog without Priest's power still serves a Mage mirror");
  auto unsupported_priest = hero_power_definitions();
  for (auto& d : unsupported_priest) if (d.card_id == "HERO_09bp") d.support_state = "UNSUPPORTED";
  check(hp_ctor_failure("PRIEST", "MAGE", unsupported_priest) == FailureCode::UNSUPPORTED_HERO_POWER, "HP03 an UNSUPPORTED starting power is rejected, not replaced");
  check(failure_kind_of(FailureCode::UNSUPPORTED_HERO_POWER) == FailureKind::Unsupported && std::string(failure_code_id(FailureCode::UNSUPPORTED_HERO_POWER)) == "UNSUPPORTED_HERO_POWER", "HP03 new failure code is an Unsupported-kind append-only identity");
  check(static_cast<int>(FailureCode::UNSUPPORTED_HERO_POWER) == 59 && static_cast<int>(FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED) == 58, "HP03 failure code numbering is append-only");
  check(reviewed_base_hero_power("PRIEST") == "HERO_09bp" && reviewed_base_hero_power("MAGE") == "HERO_08bp" && reviewed_base_hero_power("HUNTER") == "HERO_05bp" && reviewed_base_hero_power("WARRIOR") == "HERO_01bp" && reviewed_base_hero_power("DRUID").empty(), "HP03 reviewed base power table");
}

void test_mage_fireblast_regression() {
  auto s = hp_game("MAGE", "MAGE");
  const int friendly = TestAccess::minion(s, 0, "TEST_FILLER", 2, 2), enemy = TestAccess::minion(s, 1, "TEST_FILLER", 3, 3);
  check(hp_targets(s) == std::set<int>({hero0, hero1, friendly, enemy}), "HP10 Fireblast targets every character on both sides");
  for (const auto& a : s.legal_actions()) check(a.type != ActionType::HeroPower || (a.hand_index == -1 && a.attacker_entity_id == -1), "HP10 Fireblast encoding: type + target only");
  s.apply_action(hp_action(s, enemy));
  check(TestAccess::player(s, 1).board[0].health == 2 && TestAccess::player(s, 0).mana == 8 && TestAccess::player(s, 0).hero_power_used_this_turn, "HP10 Fireblast deals exactly 1, spends 2 Mana, exhausts the power");
  check(hp_actions(s).empty(), "HP10 no second use in the same turn despite 8 Mana");
  s.apply_action(end_turn_action(s));
  check(hp_targets(s).count(hero0) == 1 && TestAccess::player(s, 1).mana == 10, "HP10 the opponent's power is ready on their own turn");
  s.apply_action(hp_action(s, hero0));
  check(TestAccess::player(s, 0).hero_health == 29 && TestAccess::player(s, 1).hero_health == 30, "HP10 opponent Fireblast hits only the chosen hero " + std::to_string(TestAccess::player(s, 0).hero_health) + "/" + std::to_string(TestAccess::player(s, 1).hero_health));
  s.apply_action(end_turn_action(s));
  check(TestAccess::player(s, 0).mana == 10 && !hp_actions(s).empty() && !TestAccess::player(s, 0).hero_power_used_this_turn, "HP10 own power and Mana are restored at the next own turn");
  // Spell Damage never applies to Hero Power damage (HeroPower attribution, not Spell).
  auto sd = hp_game("MAGE", "MAGE");
  TestAccess::minion(sd, 0, "TEST_SPELL_POWER_TWO", 1, 3);
  check(sd.observation(0).self_player.spell_damage == 2, "HP11 fixture: Spell Damage +2 is active");
  sd.apply_action(hp_action(sd, hero1));
  check(TestAccess::player(sd, 1).hero_health == 29, "HP11 Fireblast ignores Spell Damage");
  // Prevention semantics: a Divine Shield absorbs the whole packet; armor absorbs hero damage first.
  auto shield = hp_game("MAGE", "MAGE");
  const int shielded = TestAccess::minion(shield, 1, "TEST_FILLER", 1, 4);
  TestAccess::set_divine_shield(shield, 1, 0, true);
  shield.apply_action(hp_action(shield, shielded));
  check(TestAccess::player(shield, 1).board[0].health == 4 && !TestAccess::player(shield, 1).board[0].divine_shield, "HP11 Fireblast pops Divine Shield without damage");
  auto armored = hp_game("MAGE", "MAGE");
  TestAccess::player(armored, 1).armor = 3;
  armored.apply_action(hp_action(armored, hero1));
  check(TestAccess::player(armored, 1).armor == 2 && TestAccess::player(armored, 1).hero_health == 30, "HP11 Fireblast is absorbed by Armor first");
  // Lethal Fireblast and a killed minion go through the shared death/result path.
  auto lethal = hp_game("MAGE", "MAGE");
  TestAccess::player(lethal, 1).hero_health = 1;
  const int one_health = TestAccess::minion(lethal, 1, "TEST_FILLER", 1, 1);
  lethal.apply_action(hp_action(lethal, one_health));
  check(TestAccess::player(lethal, 1).board.empty() && !lethal.result(), "HP12 Fireblast kills a 1-Health minion");
  lethal.apply_action(end_turn_action(lethal));
  lethal.apply_action(end_turn_action(lethal));
  lethal.apply_action(hp_action(lethal, hero1));
  check(lethal.result() == std::optional<std::string>("PLAYER1_WIN") && lethal.legal_actions().empty(), "HP12 lethal Fireblast ends the game");
}

void test_priest_lesser_heal() {
  auto s = hp_game("PRIEST", "MAGE");
  TestAccess::player(s, 0).hero_health = 20;
  TestAccess::player(s, 1).hero_health = 25;
  const int friendly = TestAccess::minion(s, 0, "TEST_FILLER", 1, 5);
  TestAccess::set_health(s, 0, 0, 3);
  const int enemy = TestAccess::minion(s, 1, "TEST_FILLER", 1, 6);
  TestAccess::set_health(s, 1, 0, 1);
  check(hp_targets(s) == std::set<int>({hero0, hero1, friendly, enemy}), "HP20 Lesser Heal may target any character");
  s.apply_action(hp_action(s, hero0));
  check(TestAccess::player(s, 0).hero_health == 22 && TestAccess::player(s, 0).mana == 8 && TestAccess::player(s, 0).armor == 0, "HP20 heals the friendly hero by exactly 2 and spends 2 Mana, no armor");
  s.apply_action(end_turn_action(s));
  s.apply_action(end_turn_action(s));
  s.apply_action(hp_action(s, friendly));
  check(TestAccess::player(s, 0).board[0].health == 5, "HP20 friendly minion 3 -> 5 (its own maximum 5)");
  s.apply_action(end_turn_action(s));
  s.apply_action(end_turn_action(s));
  s.apply_action(hp_action(s, hero1));
  check(TestAccess::player(s, 1).hero_health == 27 && TestAccess::player(s, 0).hero_health == 22, "HP21 an enemy hero may be healed (no bonus: permitted)");
  s.apply_action(end_turn_action(s));
  s.apply_action(end_turn_action(s));
  s.apply_action(hp_action(s, enemy));
  check(TestAccess::player(s, 1).board[0].health == 3, "HP21 an enemy minion 1 -> 3 may be healed");
  // Caps: hero at 29 restores exactly 1; full Health still spends the power and Mana.
  auto cap = hp_game("PRIEST", "MAGE");
  TestAccess::player(cap, 0).hero_health = 29;
  cap.apply_action(hp_action(cap, hero0));
  check(TestAccess::player(cap, 0).hero_health == 30, "HP22 healing stops at the hero maximum 30");
  auto full = hp_game("PRIEST", "MAGE");
  check(hp_targets(full).count(hero0) == 1, "HP22 a full-Health target is still selectable");
  full.apply_action(hp_action(full, hero0));
  check(TestAccess::player(full, 0).hero_health == 30 && TestAccess::player(full, 0).mana == 8 && TestAccess::player(full, 0).hero_power_used_this_turn, "HP22 healing at full Health changes nothing but spends Mana and the use");
  // Healing bonus (controller-owned, per packet) reaches Lesser Heal through the shared pipeline.
  auto bonus = hp_game("PRIEST", "MAGE");
  TestAccess::player(bonus, 0).healing_bonus = 2;
  TestAccess::player(bonus, 0).hero_health = 20;
  const int hurt = TestAccess::minion(bonus, 0, "TEST_FILLER", 1, 6);
  TestAccess::set_health(bonus, 0, 0, 1);
  bonus.apply_action(hp_action(bonus, hero0));
  check(TestAccess::player(bonus, 0).hero_health == 24, "HP23 Lesser Heal restores 2 + bonus 2 = 4 to the friendly hero");
  bonus.apply_action(end_turn_action(bonus));
  bonus.apply_action(end_turn_action(bonus));
  bonus.apply_action(hp_action(bonus, hurt));
  check(TestAccess::player(bonus, 0).board[0].health == 5, "HP23 minion 1 -> 5 with the bonus");
  auto opponent_bonus = hp_game("PRIEST", "MAGE");
  TestAccess::player(opponent_bonus, 1).healing_bonus = 5;
  TestAccess::player(opponent_bonus, 0).hero_health = 20;
  opponent_bonus.apply_action(hp_action(opponent_bonus, hero0));
  check(TestAccess::player(opponent_bonus, 0).hero_health == 22, "HP23 the opponent's bonus never applies to my heal");
  // Cross-side healing with an unresolved bonus fails closed (shared pipeline code), without touching Health.
  auto cross = hp_game("PRIEST", "MAGE");
  TestAccess::player(cross, 0).healing_bonus = 2;
  TestAccess::player(cross, 1).hero_health = 20;
  const auto cross_action = hp_action(cross, hero1);
  const auto code = failure_of([&] { cross.apply_action(cross_action); });
  check(code == FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED && !cross.is_valid() && TestAccess::player(cross, 1).hero_health == 20,
        "HP24 cross-side heal with a bonus is typed fail-closed and the target keeps its Health");
  auto cross_minion = hp_game("PRIEST", "MAGE");
  TestAccess::player(cross_minion, 0).healing_bonus = 1;
  const int enemy_minion = TestAccess::minion(cross_minion, 1, "TEST_FILLER", 1, 4);
  TestAccess::set_health(cross_minion, 1, 0, 2);
  const auto minion_action = hp_action(cross_minion, enemy_minion);
  check(failure_of([&] { cross_minion.apply_action(minion_action); }) == FailureCode::HEALING_BONUS_SCOPE_UNREVIEWED && TestAccess::player(cross_minion, 1).board[0].health == 2, "HP24 cross-side minion heal with a bonus is fail-closed too");
}

void test_hunter_steady_shot() {
  auto s = hp_game("HUNTER", "PRIEST");
  const int friendly = TestAccess::minion(s, 0, "TEST_FILLER", 1, 3);
  const int taunt = TestAccess::minion(s, 1, "TEST_FILLER", 1, 3);
  TestAccess::set_taunt(s, 1, 0, true);
  const auto actions = hp_actions(s);
  check(actions.size() == 1 && actions[0].target_entity_id == -1, "HP30 Steady Shot is untargeted: exactly one action, no target handle, no minion or friendly choice");
  const auto semantic = s.semantic_legal_actions();
  const auto power = std::find_if(semantic.begin(), semantic.end(), [](const Action& a) { return a.type == ActionType::HeroPower; });
  check(power != semantic.end() && power->card_id == "HERO_05bp" && power->card_type == "HERO_POWER" && power->card_cost == 2 && !power->target_is_hero && power->target_card_id.empty(), "HP30 semantic encoding names Steady Shot with no target fields");
  s.apply_action(actions[0]);
  check(TestAccess::player(s, 1).hero_health == 28 && TestAccess::player(s, 0).hero_health == 30, "HP31 exactly 2 damage to the enemy hero only");
  check(TestAccess::player(s, 1).board[0].health == 3 && TestAccess::player(s, 0).board[0].health == 3 && TestAccess::player(s, 1).board[0].entity_id == taunt && TestAccess::player(s, 0).board[0].entity_id == friendly, "HP31 a Taunt minion does not redirect and no minion is touched");
  check(TestAccess::player(s, 0).mana == 8 && hp_actions(s).empty(), "HP31 2 Mana spent, once per turn");
  // Armor, then Health; Spell Damage never applies; lethal ends the game.
  auto armor = hp_game("HUNTER", "MAGE");
  TestAccess::player(armor, 1).armor = 5;
  armor.apply_action(hp_action(armor));
  check(TestAccess::player(armor, 1).armor == 3 && TestAccess::player(armor, 1).hero_health == 30, "HP32 Armor absorbs Steady Shot");
  auto partial = hp_game("HUNTER", "MAGE");
  TestAccess::player(partial, 1).armor = 1;
  partial.apply_action(hp_action(partial));
  check(TestAccess::player(partial, 1).armor == 0 && TestAccess::player(partial, 1).hero_health == 29, "HP32 1 Armor absorbs 1, the rest hits Health");
  auto sd = hp_game("HUNTER", "MAGE");
  TestAccess::minion(sd, 0, "TEST_SPELL_POWER_TWO", 1, 3);
  sd.apply_action(hp_action(sd));
  check(TestAccess::player(sd, 1).hero_health == 28, "HP33 Steady Shot ignores Spell Damage (HeroPower attribution)");
  auto lethal = hp_game("HUNTER", "MAGE");
  TestAccess::player(lethal, 1).hero_health = 2;
  lethal.apply_action(hp_action(lethal));
  check(lethal.result() == std::optional<std::string>("PLAYER1_WIN"), "HP33 lethal Steady Shot ends the game");
  // A frozen hero still uses its Hero Power.
  auto frozen = hp_game("HUNTER", "MAGE");
  TestAccess::player(frozen, 0).hero_frozen = true;
  check(hp_actions(frozen).size() == 1, "HP34 Freeze on the hero does not block the Hero Power");
}

void test_warrior_armor_up() {
  auto s = hp_game("WARRIOR", "HUNTER");
  TestAccess::player(s, 0).hero_health = 17;
  TestAccess::minion(s, 0, "TEST_FILLER", 1, 3);
  TestAccess::minion(s, 1, "TEST_FILLER", 1, 3);
  const auto actions = hp_actions(s);
  check(actions.size() == 1 && actions[0].target_entity_id == -1, "HP40 Armor Up! is untargeted");
  s.apply_action(actions[0]);
  check(TestAccess::player(s, 0).armor == 2 && TestAccess::player(s, 0).hero_health == 17 && TestAccess::player(s, 0).mana == 8, "HP41 +2 Armor, Health untouched, 2 Mana spent");
  check(TestAccess::player(s, 1).armor == 0 && TestAccess::player(s, 1).hero_health == 30 && TestAccess::player(s, 0).board[0].health == 3 && TestAccess::player(s, 1).board[0].health == 3, "HP41 nothing else changes");
  check(hp_actions(s).empty(), "HP41 once per turn");
  s.apply_action(end_turn_action(s));
  s.apply_action(end_turn_action(s));
  s.apply_action(hp_action(s));
  check(TestAccess::player(s, 0).armor == 4 && TestAccess::player(s, 0).hero_health == 17, "HP42 Armor accumulates across turns");
  auto full = hp_game("WARRIOR", "WARRIOR");
  TestAccess::player(full, 0).armor = 5;
  full.apply_action(hp_action(full));
  check(TestAccess::player(full, 0).armor == 7 && TestAccess::player(full, 0).hero_health == 30, "HP42 existing Armor is added to, hero at full Health is not changed");
}

void test_mixed_class_matrix() {
  // Independent rules model of the four powers at 20/20 Health: Armor absorbs hero damage before Health.
  struct Hero { int health, armor; };
  auto damage = [](Hero& hero, int amount) { const int absorbed = std::min(hero.armor, amount); hero.armor -= absorbed; hero.health -= amount - absorbed; };
  auto model = [&](const std::string& player_class, Hero& own, Hero& enemy) {
    if (player_class == "MAGE") damage(enemy, 1);                  // Fireblast aimed at the enemy hero
    else if (player_class == "PRIEST") own.health = std::min(30, own.health + 2);  // Lesser Heal aimed at the own hero
    else if (player_class == "HUNTER") damage(enemy, 2);
    else own.armor += 2;
  };
  for (const auto& first : hp_classes) for (const auto& second : hp_classes) {
    auto s = hp_game(first, second);
    TestAccess::player(s, 0).hero_health = 20;
    TestAccess::player(s, 1).hero_health = 20;
    auto use = [&](const std::string& player_class, int own_hero, int enemy_hero) {
      Action chosen;
      bool found = false;
      for (const auto& a : s.semantic_legal_actions()) {
        if (a.type != ActionType::HeroPower || a.card_id != hp_power_of(player_class)) continue;
        const int wanted = player_class == "MAGE" ? enemy_hero : player_class == "PRIEST" ? own_hero : -1;
        if (a.target_entity_id == wanted) { chosen = a; found = true; }
      }
      check(found, "HP50 " + first + " vs " + second + ": " + player_class + " offers its own Hero Power");
      s.apply_action(chosen);
    };
    Hero expected0{20, 0}, expected1{20, 0};
    use(first, hero0, hero1);
    model(first, expected0, expected1);
    s.apply_action(end_turn_action(s));
    use(second, hero1, hero0);
    model(second, expected1, expected0);
    check(TestAccess::player(s, 0).hero_health == expected0.health && TestAccess::player(s, 1).hero_health == expected1.health,
          "HP50 " + first + " vs " + second + ": Health follows each seat's own power");
    check(TestAccess::player(s, 0).armor == expected0.armor && TestAccess::player(s, 1).armor == expected1.armor, "HP50 " + first + " vs " + second + ": Armor follows each seat's own power");
    check(TestAccess::player(s, 0).mana == 8 && TestAccess::player(s, 1).mana == 8, "HP50 both seats paid 2 Mana");
  }
}

void test_hero_power_availability_and_turn_boundary() {
  for (const auto& player_class : hp_classes) {
    auto s = hp_game(player_class, player_class);
    TestAccess::player(s, 0).mana = 1;
    check(hp_actions(s).empty(), "HP60 " + player_class + " 1 Mana: power unavailable");
    TestAccess::player(s, 0).mana = 2;
    check(!hp_actions(s).empty(), "HP60 " + player_class + " exactly 2 Mana: power available");
    s.apply_action(hp_actions(s).front());
    check(TestAccess::player(s, 0).mana == 0, "HP60 " + player_class + " spends exactly 2 Mana");
    check(!s.observation(0).self_player.hero_power_ready && s.observation(0).self_player.hero_power->card_id == hp_power_of(player_class), "HP61 exhausted power stays visible but not ready");
    TestAccess::player(s, 0).mana = 10;
    check(hp_actions(s).empty(), "HP61 Mana does not override the once-per-turn rule");
    s.apply_action(end_turn_action(s));
    check(!s.observation(1).opponent.hero_power_ready && s.observation(1).self_player.hero_power_ready, "HP62 during the opponent's turn my power is still exhausted, theirs ready (both perspectives)");
    check(!s.observation(0).self_player.hero_power_ready && s.observation(0).opponent.hero_power_ready, "HP62 mirrored perspective agrees");
    s.apply_action(end_turn_action(s));
    check(!TestAccess::player(s, 0).hero_power_used_this_turn && !hp_actions(s).empty() && s.observation(0).self_player.hero_power_ready, "HP62 my power is ready again at my next turn");
  }
}

void test_hero_power_clone_independence() {
  for (const auto& player_class : hp_classes) {
    auto original = hp_game(player_class, "MAGE");
    TestAccess::player(original, 0).hero_health = 20;
    const auto before = original.legal_actions().size();
    auto copy = original.clone();
    copy->apply_action(hp_actions(*copy).front());
    check(!TestAccess::player(original, 0).hero_power_used_this_turn && TestAccess::player(original, 0).mana == 10 && original.legal_actions().size() == before, "HP70 " + player_class + " clone use does not leak into the source");
    check(TestAccess::player(*copy, 0).hero_power_used_this_turn && TestAccess::player(*copy, 0).mana == 8, "HP70 " + player_class + " the clone carries the use");
    const int copy_health = TestAccess::player(*copy, 0).hero_health, copy_armor = TestAccess::player(*copy, 0).armor;
    original.apply_action(hp_actions(original).front());
    TestAccess::player(original, 0).armor += 40;
    check(TestAccess::player(*copy, 0).hero_health == copy_health && TestAccess::player(*copy, 0).armor == copy_armor && TestAccess::player(*copy, 0).mana == 8, "HP70 " + player_class + " source changes do not leak into the clone");
    auto fresh = hp_game(player_class, "MAGE");
    auto fresh_copy = fresh.clone();
    TestAccess::player(*fresh_copy, 0).hero_power_id = "TEST_POWER_ARMOR_THREE";
    check(TestAccess::player(fresh, 0).hero_power_id == hp_power_of(player_class) && fresh.observation(0).self_player.hero_power->card_id == hp_power_of(player_class), "HP70 " + player_class + " the clone has its own Hero Power identity");
  }
}

void test_hero_power_action_parity_and_illegal_input() {
  for (const auto& player_class : hp_classes) {
    auto s = hp_game(player_class, "MAGE");
    TestAccess::player(s, 0).hero_health = 20;
    const int mine = TestAccess::minion(s, 0, "TEST_FILLER", 1, 4), theirs = TestAccess::minion(s, 1, "TEST_FILLER", 1, 4);
    const auto raw = hp_actions(s);
    std::vector<Action> semantic;
    for (const auto& a : s.semantic_legal_actions()) if (a.type == ActionType::HeroPower) semantic.push_back(a);
    check(raw.size() == semantic.size() && !raw.empty(), "HP80 " + player_class + " raw and semantic enumeration agree");
    for (std::size_t i = 0; i < raw.size(); ++i) {
      check(raw[i].execution_equal(semantic[i]) && semantic[i].card_id == hp_power_of(player_class) && semantic[i].card_type == "HERO_POWER" && semantic[i].card_cost == 2, "HP80 " + player_class + " semantic fields describe the current power");
      const int handle = semantic[i].target_entity_id;
      if (handle >= 0) {
        const bool hero = handle == hero0 || handle == hero1;
        check(semantic[i].target_is_hero == hero && semantic[i].target_is_self == (handle == hero0 || handle == mine) && (hero || (semantic[i].target_card_id == "TEST_FILLER" && semantic[i].target_health == 4 && (handle == mine || handle == theirs))), "HP80 " + player_class + " target fields describe the handle");
      } else {
        check(!semantic[i].target_is_hero && semantic[i].target_card_id.empty(), "HP80 " + player_class + " untargeted action carries no target fields");
      }
      auto branch = s.clone();
      branch->apply_action(raw[i]);  // every advertised action executes (legality/execution parity)
      check(TestAccess::player(*branch, 0).mana == 8 && TestAccess::player(*branch, 0).hero_power_used_this_turn && branch->is_valid(), "HP80 " + player_class + " advertised action executes and charges 2 Mana");
    }
    // Illegal shapes are non-poisoning caller errors.
    const bool targeted = player_class == "MAGE" || player_class == "PRIEST";
    Action wrong;
    wrong.type = ActionType::HeroPower;
    wrong.target_entity_id = targeted ? -1 : hero1;
    check(hp_invalid_argument([&] { s.apply_action(wrong); }) && s.is_valid(), "HP81 " + player_class + " wrong target shape is rejected without poisoning");
    wrong.target_entity_id = 999;
    check(hp_invalid_argument([&] { s.apply_action(wrong); }) && s.is_valid(), "HP81 " + player_class + " non-character target is rejected without poisoning");
    s.apply_action(raw.front());
    check(hp_invalid_argument([&] { s.apply_action(raw.front()); }) && s.is_valid(), "HP81 " + player_class + " second use in a turn is rejected without poisoning");
  }
  // A Hunter must not inherit Mage targeting: a minion or friendly handle is never legal.
  auto hunter = hp_game("HUNTER", "MAGE");
  const int friendly = TestAccess::minion(hunter, 0, "TEST_FILLER", 1, 4), enemy = TestAccess::minion(hunter, 1, "TEST_FILLER", 1, 4);
  for (int handle : {hero0, hero1, friendly, enemy}) {
    Action a;
    a.type = ActionType::HeroPower;
    a.target_entity_id = handle;
    check(hp_invalid_argument([&] { hunter.apply_action(a); }), "HP82 Steady Shot accepts no target handle");
  }
}

void test_hero_power_state_is_not_inferred_from_class() {
  // The class never proves the current power: the engine reads the stored identity.
  auto swapped = hp_game("MAGE", "MAGE");
  TestAccess::player(swapped, 0).hero_power_id = "HERO_09bp";
  TestAccess::player(swapped, 0).hero_health = 20;
  check(swapped.observation(0).self_player.hero_power->card_id == "HERO_09bp" && swapped.observation(0).self_player.player_class == "MAGE", "HP90 a reviewed non-class power is exported as itself");
  check(hp_targets(swapped).count(hero0) == 1, "HP90 targets follow the stored power (heal), not the class");
  swapped.apply_action(hp_action(swapped, hero0));
  check(TestAccess::player(swapped, 0).hero_health == 22, "HP90 effect follows the stored power: a Mage-class seat holding Lesser Heal heals");
  // Extensibility: new reviewed powers are catalog declarations; cost, targeting and effect come from the definition.
  auto friendly_heal = hp_game("MAGE", "MAGE");
  TestAccess::player(friendly_heal, 0).hero_power_id = "TEST_POWER_FRIENDLY_HEAL";
  TestAccess::player(friendly_heal, 0).hero_health = 20;
  const int mine = TestAccess::minion(friendly_heal, 0, "TEST_FILLER", 1, 6);
  TestAccess::set_health(friendly_heal, 0, 0, 1);
  TestAccess::minion(friendly_heal, 1, "TEST_FILLER", 1, 6);
  check(hp_targets(friendly_heal) == std::set<int>({hero0, mine}), "HP91 a friendly-only power offers only friendly characters");
  friendly_heal.apply_action(hp_action(friendly_heal, mine));
  check(TestAccess::player(friendly_heal, 0).board[0].health == 4 && TestAccess::player(friendly_heal, 0).mana == 9, "HP91 cost 1 and Restore 3 come from the definition");
  auto armor_three = hp_game("MAGE", "MAGE");
  TestAccess::player(armor_three, 0).hero_power_id = "TEST_POWER_ARMOR_THREE";
  TestAccess::player(armor_three, 0).mana = 2;
  check(hp_actions(armor_three).empty(), "HP91 a 3-Mana power is unavailable with 2 Mana");
  TestAccess::player(armor_three, 0).mana = 3;
  armor_three.apply_action(hp_action(armor_three));
  check(TestAccess::player(armor_three, 0).armor == 3 && TestAccess::player(armor_three, 0).mana == 0, "HP91 Armor 3 for 3 Mana from the definition alone");
  // Fail closed: unknown, empty, unsupported (replaced) and non-Hero-Power identities are never replaced by the base power.
  for (const std::string& bad : {std::string(), std::string("HERO_99bp"), std::string("TEST_POWER_REPLACED"), std::string("TEST_FILLER")}) {
    for (int seat = 0; seat < 2; ++seat) {
      auto s = hp_game("MAGE", "PRIEST");
      TestAccess::player(s, seat).hero_power_id = bad;
      check(failure_of([&] { s.legal_actions(); }) == FailureCode::UNSUPPORTED_HERO_POWER, "HP92 legal actions reject power '" + bad + "' on seat " + std::to_string(seat));
      check(failure_of([&] { s.observation(0); }) == FailureCode::UNSUPPORTED_HERO_POWER, "HP92 observation rejects power '" + bad + "' on seat " + std::to_string(seat));
      check(failure_of([&] { s.semantic_legal_actions(); }) == FailureCode::UNSUPPORTED_HERO_POWER, "HP92 semantic actions reject power '" + bad + "'");
      check(failure_of([&] { s.validate_invariants(); }) == FailureCode::UNSUPPORTED_HERO_POWER, "HP92 invariants reject power '" + bad + "'");
      Action a;
      a.type = ActionType::EndTurn;
      check(failure_of([&] { s.apply_action(a); }) == FailureCode::UNSUPPORTED_HERO_POWER, "HP92 no action executes while a seat holds an unreviewed power");
    }
  }
}

void test_hero_power_catalog_contract() {
  auto rejects = [](CardDefinition bad) {
    auto definitions = hero_power_definitions();
    definitions.push_back(std::move(bad));
    try { CardCatalog catalog_under_test(std::move(definitions)); } catch (const std::invalid_argument&) { return true; }
    return false;
  };
  auto power = [](const std::string& id, std::vector<EffectStep> steps, const std::string& ability = "EFFECT_COMPOSITION") {
    auto d = def(id, "HERO_POWER", 2, 0, 0, ability);
    d.effects = std::move(steps);
    return d;
  };
  check(!rejects(power("TEST_OK", {effect(EffectKind::Damage, TargetSelector::EnemyHero, 3)})), "HP95 a reviewed second consumer loads");
  check(rejects(power("TEST_NO_EFFECT", {})), "HP95 a supported power without effects is rejected");
  check(rejects(power("TEST_VANILLA", {}, "NONE")), "HP95 a vanilla/NONE supported power is rejected");
  check(rejects(power("TEST_DRAW", {effect(EffectKind::Draw, TargetSelector::Self, 1)})), "HP95 unreviewed effect kinds are rejected");
  check(rejects(power("TEST_TWO_TARGETS", {effect(EffectKind::Damage, TargetSelector::ExplicitCharacter, 1), effect(EffectKind::Heal, TargetSelector::ExplicitCharacter, 1)})), "HP95 at most one explicit target");
  check(rejects(power("TEST_AREA", {effect(EffectKind::Damage, TargetSelector::EnemyCharacters, 1)})), "HP95 unreviewed selectors are rejected");
  check(rejects(power("TEST_HEAL_ENEMY_HERO", {effect(EffectKind::Heal, TargetSelector::EnemyHero, 2)})), "HP95 EnemyHero is Damage-only");
  check(rejects(power("TEST_ZERO", {effect(EffectKind::GainArmor, TargetSelector::Self, 0)})), "HP95 amounts must be positive");
  check(rejects(power("TEST_LIFESTEAL", {effect(EffectKind::Damage, TargetSelector::EnemyHero, 1, true)})), "HP95 no extra step fields");
  auto collectible = power("TEST_COLLECTIBLE", {effect(EffectKind::GainArmor, TargetSelector::Self, 1)});
  collectible.collectible = true;
  check(rejects(collectible), "HP95 Hero Powers are non-collectible");
  auto spell = def("TEST_SPELL_ENEMY_HERO", "SPELL", 1, 0, 0, "EFFECT_COMPOSITION");
  spell.effects = {effect(EffectKind::Damage, TargetSelector::EnemyHero, 1)};
  check(rejects(spell), "HP95 EnemyHero is rejected on every other card type");
  auto unsupported = power("TEST_UNSUPPORTED_ANYTHING", {effect(EffectKind::Draw, TargetSelector::Self, 1)});
  unsupported.support_state = "UNSUPPORTED";
  check(!rejects(unsupported), "HP95 an UNSUPPORTED power may stay declared as a diagnostic row");
}

void test_hero_power_mixed_trajectories() {
  // Random legal play across every class pairing: invariants hold, every advertised action executes, the game terminates or stays valid.
  for (const auto& first : hp_classes) for (const auto& second : hp_classes) for (std::uint64_t seed = 0; seed < 8; ++seed) {
    std::vector<std::string> deck(30, "TEST_FILLER");
    GameSession s(deck, deck, hero_power_definitions(), seed, true, first, second);
    for (int step = 0; step < 60 && !s.is_complete(); ++step) {
      s.validate_invariants();
      const auto actions = s.legal_actions();
      const auto semantic = s.semantic_legal_actions();
      check(actions.size() == semantic.size(), "HP96 raw/semantic enumeration parity");
      const auto& chosen = actions[static_cast<std::size_t>((seed * 7 + step * 13) % actions.size())];
      s.apply_action(chosen);
      check(s.is_valid(), "HP96 random legal play never poisons the session");
    }
  }
}

void run_hero_power_family() {
  current_native_group = "hero_power_v1";
  test_hero_power_identity_and_observation();
  test_mage_fireblast_regression();
  test_priest_lesser_heal();
  test_hunter_steady_shot();
  test_warrior_armor_up();
  test_mixed_class_matrix();
  test_hero_power_availability_and_turn_boundary();
  test_hero_power_clone_independence();
  test_hero_power_action_parity_and_illegal_input();
  test_hero_power_state_is_not_inferred_from_class();
  test_hero_power_catalog_contract();
  test_hero_power_mixed_trajectories();
}
}  // namespace
}  // namespace manaengine
