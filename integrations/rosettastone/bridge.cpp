#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <unordered_set>
#include <effolkronium/random.hpp>
#include <Rosetta/PlayMode/Cards/Cards.hpp>
#include <Rosetta/PlayMode/Actions/PlayCard.hpp>
#include <Rosetta/PlayMode/Cards/CardDefs.hpp>
#include <Rosetta/PlayMode/Games/Game.hpp>
#include <Rosetta/PlayMode/Models/Character.hpp>
#include <Rosetta/PlayMode/Models/Hero.hpp>
#include <Rosetta/PlayMode/Models/HeroPower.hpp>
#include <Rosetta/PlayMode/Models/Minion.hpp>
#include <Rosetta/PlayMode/Models/Location.hpp>
#include <Rosetta/PlayMode/Models/Player.hpp>
#include <Rosetta/PlayMode/Models/Weapon.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/AttackTask.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/ChooseTask.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/EndTurnTask.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/HeroPowerTask.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/PlayCardTask.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/PlayLocationTask.hpp>
#include <Rosetta/PlayMode/Tasks/PlayerTasks/TradeCardTask.hpp>
#include <Rosetta/PlayMode/Zones/DeckZone.hpp>
#include <Rosetta/PlayMode/Zones/FieldZone.hpp>
#include <Rosetta/PlayMode/Zones/HandZone.hpp>

namespace py = pybind11;
using namespace RosettaStone;
using namespace RosettaStone::PlayMode;
using Random = effolkronium::random_static;

namespace
{
int tag_value(const Entity* entity, GameTag tag)
{
    const auto tags = entity->GetGameTags();
    const auto found = tags.find(tag);
    return found == tags.end() ? 0 : found->second;
}
py::dict card_features(const Card* card, int current_cost)
{
    py::dict result;
    result["card_id"] = card ? card->id : "UNKNOWN_CARD";
    result["cost"] = card && card->gameTags.contains(GameTag::COST)
                         ? py::cast(card->gameTags.at(GameTag::COST))
                         : py::none();
    result["current_cost"] = current_cost;
    result["card_type"] = card ? std::string(EnumToStr(card->GetCardType())) : "UNKNOWN_TYPE";
    result["card_class"] = card ? std::string(EnumToStr(card->GetCardClass())) : "UNKNOWN_CLASS";
    if (card && card->gameTags.contains(GameTag::CARDRACE) &&
        card->GetRace() != Race::INVALID)
    {
        result["race"] = std::string(EnumToStr(card->GetRace()));
    }
    else
    {
        result["race"] = py::none();
    }
    result["attack"] = card && card->gameTags.contains(GameTag::ATK)
                            ? py::cast(card->gameTags.at(GameTag::ATK))
                            : py::none();
    result["health"] = card && card->gameTags.contains(GameTag::HEALTH)
                            ? py::cast(card->gameTags.at(GameTag::HEALTH))
                            : py::none();
    result["mechanics"] = py::list();
    result["durability"] = card && card->gameTags.contains(GameTag::DURABILITY)
                                ? py::cast(card->gameTags.at(GameTag::DURABILITY))
                                : py::none();
    return result;
}

py::dict playable_features(const Playable* playable)
{
    py::dict result = card_features(playable->card, playable->GetCost());
    const auto tags = playable->GetGameTags();
    const auto type = playable->card->GetCardType();
    if (tags.contains(GameTag::ATK) && (type == CardType::MINION || type == CardType::WEAPON))
        result["current_attack"] = playable->GetGameTag(GameTag::ATK);
    if (tags.contains(GameTag::HEALTH) && (type == CardType::MINION || type == CardType::LOCATION))
        result["current_health"] = playable->GetGameTag(GameTag::HEALTH) - playable->GetGameTag(GameTag::DAMAGE);
    if (tags.contains(GameTag::DURABILITY) && type == CardType::WEAPON)
        result["current_durability"] = playable->GetGameTag(GameTag::DURABILITY);
    result["dark_gift_id"] = tag_value(playable, GameTag::MANAMIND_DARK_GIFT_ID);
    return result;
}

py::dict player_observation(Player* player)
{
    py::dict result;
    Hero* hero = player->GetHero();
    result["hero_health"] = std::max(0, hero->GetHealth());
    result["armor"] = tag_value(hero, GameTag::ARMOR);
    result["hero_attack"] = hero->GetAttack();
    result["max_mana"] = player->GetTotalMana();
    result["available_mana"] = std::max(0, player->GetRemainingMana());
    result["overloaded_mana"] = player->GetOverloadLocked();
    result["pending_overload"] = player->GetOverloadOwed();
    result["deck_size"] = player->GetDeckZone()->GetCount();
    result["hand_size"] = player->GetHandZone()->GetCount();
    result["fatigue"] = tag_value(player, GameTag::FATIGUE);
    HeroPower* heroPower = hero->heroPower;
    result["hero_power_ready"] = heroPower && heroPower->card && !heroPower->IsExhausted();
    result["player_class"] = std::string(EnumToStr(player->baseClass));
    if (heroPower && heroPower->card)
    {
        result["hero_power"] = card_features(heroPower->card, heroPower->GetCost());
    }
    else
    {
        result["hero_power"] = py::none();
    }
    Weapon* weapon = hero->weapon;
    if (weapon && weapon->card)
    {
        py::dict weaponFeatures = card_features(weapon->card, weapon->GetCost());
        weaponFeatures["current_attack"] = weapon->GetAttack();
        weaponFeatures["current_durability"] = weapon->GetDurability();
        result["weapon"] = std::move(weaponFeatures);
    }
    else
    {
        result["weapon"] = py::none();
    }

    py::list board;
    for (Minion* minion : player->GetFieldZone()->GetMinions())
    {
        py::dict entity = card_features(minion->card, minion->GetCost());
        entity["current_attack"] = minion->GetAttack();
        entity["current_health"] = minion->GetHealth();
        entity["max_health"] = minion->GetBaseHealth();
        entity["board_position"] = minion->GetZonePosition();
        entity["taunt"] = minion->HasTaunt();
        entity["divine_shield"] = minion->HasDivineShield();
        entity["stealth"] = tag_value(minion, GameTag::STEALTH) != 0;
        entity["frozen"] = tag_value(minion, GameTag::FROZEN) != 0;
        entity["silenced"] = tag_value(minion, GameTag::SILENCED) != 0;
        entity["immune"] = tag_value(minion, GameTag::IMMUNE) != 0;
        entity["rush"] = minion->HasRush();
        entity["charge"] = minion->HasCharge();
        entity["windfury"] = tag_value(minion, GameTag::WINDFURY) != 0;
        entity["lifesteal"] = tag_value(minion, GameTag::LIFESTEAL) != 0;
        entity["poisonous"] = minion->HasPoisonous();
        entity["reborn"] = minion->HasReborn();
        entity["dark_gift_id"] = tag_value(minion, GameTag::MANAMIND_DARK_GIFT_ID);
        entity["dormant"] = tag_value(minion, GameTag::DORMANT) != 0;
        entity["can_attack"] = minion->CanAttack();
        board.append(std::move(entity));
    }
    result["board"] = std::move(board);

    py::list locations;
    for (Location* location : player->GetFieldZone()->GetLocations())
    {
        py::dict entity = card_features(location->card, location->GetCost());
        entity["current_health"] = location->GetHealth();
        entity["max_health"] = location->GetBaseHealth();
        entity["board_position"] = location->GetZonePosition();
        entity["on_cooldown"] = location->IsOnCooldown();
        entity["can_activate"] = location->card && location->IsPlayableByPlayer() &&
                                  location->IsPlayableByCardReq();
        locations.append(std::move(entity));
    }
    result["locations"] = std::move(locations);
    return result;
}

py::dict action_record(const char* type)
{
    py::dict action;
    action["type"] = type;
    action["card_cost"] = 0;
    action["card_attack"] = 0;
    action["card_health"] = 0;
    action["card_type"] = "UNKNOWN_TYPE";
    action["source_is_hero"] = false;
    action["source_attack"] = 0;
    action["source_health"] = 0;
    action["source_board_position"] = -1;
    action["target_is_hero"] = false;
    action["target_is_self"] = false;
    action["target_attack"] = 0;
    action["target_health"] = 0;
    action["target_board_position"] = -1;
    action["target_taunt"] = false;
    action["choose_one"] = 0;
    return action;
}

void add_source_features(py::dict& action, Character* source)
{
    action["source_is_hero"] = dynamic_cast<Hero*>(source) != nullptr;
    action["source_attack"] = source->GetAttack();
    action["source_health"] = source->GetHealth();
    if (auto* minion = dynamic_cast<Minion*>(source))
    {
        action["source_board_position"] = minion->GetZonePosition();
    }
    else if (auto* location = dynamic_cast<Location*>(source))
    {
        action["source_board_position"] = location->GetZonePosition();
    }
}

void add_target_features(py::dict& action, Character* target, Player* actor)
{
    if (!target)
    {
        action["target_entity_id"] = py::none();
        return;
    }

    action["target_entity_id"] = tag_value(target, GameTag::ENTITY_ID);
    action["target_is_hero"] = dynamic_cast<Hero*>(target) != nullptr;
    action["target_is_self"] = target->player == actor;
    action["target_attack"] = target->GetAttack();
    action["target_health"] = target->GetHealth();
    if (auto* minion = dynamic_cast<Minion*>(target))
    {
        action["target_board_position"] = minion->GetZonePosition();
        action["target_taunt"] = minion->HasTaunt();
    }
}

void add_targeted_actions(py::list& actions, const char* actionType,
                         Playable* source, Player* actor, int handIndex = -1,
                         int chooseOne = 0)
{
    const auto add_source_card_features = [&](py::dict& action)
    {
        if (source->card)
        {
            action["card_cost"] = source->GetCost();
            action["card_type"] = std::string(EnumToStr(source->card->GetCardType()));
            action["card_attack"] = source->card->gameTags.contains(GameTag::ATK)
                                         ? source->card->gameTags.at(GameTag::ATK) : 0;
            action["card_health"] = source->card->gameTags.contains(GameTag::HEALTH)
                                             ? source->card->gameTags.at(GameTag::HEALTH) : 0;
        }
        if (std::string(actionType) == "ACTIVATE_LOCATION")
        {
            action["card_id"] = source->card->id;
            if (auto* character = dynamic_cast<Character*>(source))
            {
                add_source_features(action, character);
            }
            action["source_entity_id"] = tag_value(source, GameTag::ENTITY_ID);
        }
    };
    if (source->IsValidPlayTarget(nullptr, chooseOne))
    {
        py::dict action = action_record(actionType);
        add_source_card_features(action);
        if (handIndex >= 0)
        {
            action["hand_index"] = handIndex;
            action["card_id"] = source->card->id;
            action["field_position"] = -1;
            action["choose_one"] = chooseOne;
        }
        add_target_features(action, nullptr, actor);
        actions.append(std::move(action));
    }

    for (Character* target : source->GetValidPlayTargets())
    {
        if (!source->IsValidPlayTarget(target, chooseOne))
        {
            continue;
        }
        py::dict action = action_record(actionType);
        add_source_card_features(action);
        if (handIndex >= 0)
        {
            action["hand_index"] = handIndex;
            action["card_id"] = source->card->id;
            action["field_position"] = -1;
            action["choose_one"] = chooseOne;
        }
        add_target_features(action, target, actor);
        actions.append(std::move(action));
    }
}

py::list enumerate_legal_actions(Game& game, Player* player)
{
    py::list actions;
    if (game.GetCurrentPlayer() != player)
    {
        return actions;
    }

    if (player->choice)
    {
        // Include temporary deck choices while preserving the full Game layout.
        const auto choiceAction = player->choice->choiceAction;
        if (player->choice->choiceType != ChoiceType::GENERAL ||
            (choiceAction != ChoiceAction::MOTHER &&
             choiceAction != ChoiceAction::HAND &&
             choiceAction != ChoiceAction::HAND_REDUCE_BY_HERO_ATTACK &&
             choiceAction != ChoiceAction::DRAW_FROM_DECK &&
             choiceAction != ChoiceAction::DRAW_TEMPORARY_FROM_DECK &&
             choiceAction != ChoiceAction::KAZAKUS &&
             choiceAction != ChoiceAction::SUMMON_COPY_2_3))
        {
            return actions;
        }

        const auto hand = player->GetHandZone()->GetAll();
        for (const int entityID : player->choice->choices)
        {
            const auto found = game.entityList.find(entityID);
            if (found == game.entityList.end())
            {
                continue;
            }
            auto* card = dynamic_cast<Playable*>(found->second);
            const auto expectedZone =
                choiceAction == ChoiceAction::MOTHER
                    ? ZoneType::HAND
                    : choiceAction == ChoiceAction::KAZAKUS ||
                              choiceAction == ChoiceAction::HAND ||
                              choiceAction == ChoiceAction::HAND_REDUCE_BY_HERO_ATTACK ||
                              choiceAction == ChoiceAction::SUMMON_COPY_2_3
                          ? ZoneType::SETASIDE
                          : ZoneType::DECK;
            if (!card || card->GetZoneType() != expectedZone || !card->card)
            {
                continue;
            }

            py::dict action = action_record("CHOOSE_CARD");
            action["choice_entity_id"] = entityID;
            action["card_id"] = card->card->id;
            action["card_cost"] = card->GetCost();
            action["card_type"] = std::string(EnumToStr(card->card->GetCardType()));
            action["card_attack"] = card->card->gameTags.contains(GameTag::ATK)
                                         ? card->card->gameTags.at(GameTag::ATK) : 0;
            action["card_health"] = card->card->gameTags.contains(GameTag::HEALTH)
                                         ? card->card->gameTags.at(GameTag::HEALTH) : 0;
            const auto handPosition = std::ranges::find(hand, card);
            action["hand_index"] = handPosition == hand.end()
                                        ? -1
                                        : static_cast<int>(std::distance(hand.begin(), handPosition));
            const auto gift = std::ranges::find(
                player->choice->darkGiftOptionsByEntityID, entityID,
                &std::pair<int, RosettaStone::PlayMode::DarkGift>::first);
            if (gift != player->choice->darkGiftOptionsByEntityID.end())
            {
                action["dark_gift_id"] = static_cast<int>(gift->second);
            }
            actions.append(std::move(action));
        }
        return actions;
    }

    if (game.nextStep != Step::MAIN_ACTION)
    {
        return actions;
    }

    int handIndex = 0;
    for (Playable* card : player->GetHandZone()->GetAll())
    {
        const auto cardType = card->card ? card->card->GetCardType()
                                         : CardType::INVALID;
        const bool boardFillingCard = cardType == CardType::MINION ||
                                      cardType == CardType::LOCATION;
        const bool fullBoardForCard = boardFillingCard &&
                                      player->GetFieldZone()->IsFull();
        if (card->card && !fullBoardForCard && card->IsPlayableByPlayer())
        {
            if (!card->card->chooseCardIDs.empty())
            {
                for (std::size_t choice = 1;
                     choice <= card->card->chooseCardIDs.size(); ++choice)
                {
                    const int chooseOne = static_cast<int>(choice);
                    if (card->IsPlayableByCardReq(chooseOne))
                    {
                        add_targeted_actions(actions, "PLAY_CARD", card, player,
                                             handIndex, chooseOne);
                    }
                }
            }
            else if (card->IsPlayableByCardReq())
            {
                if (cardType == CardType::LOCATION)
                {
                    // Locations are played without choosing an activation target;
                    // their target is selected when the location is activated.
                    py::dict action = action_record("PLAY_CARD");
                    action["card_cost"] = card->GetCost();
                    action["card_type"] = std::string(EnumToStr(cardType));
                    action["card_attack"] = card->card->gameTags.contains(GameTag::ATK)
                                                 ? card->card->gameTags.at(GameTag::ATK) : 0;
                    action["card_health"] = card->card->gameTags.contains(GameTag::HEALTH)
                                                 ? card->card->gameTags.at(GameTag::HEALTH) : 0;
                    action["hand_index"] = handIndex;
                    action["card_id"] = card->card->id;
                    action["field_position"] = -1;
                    add_target_features(action, nullptr, player);
                    actions.append(std::move(action));
                }
                else
                {
                    add_targeted_actions(actions, "PLAY_CARD", card, player, handIndex);
                }
            }
        }

        if (card->HasTradeable() && player->GetRemainingMana() >= 1 &&
            !player->GetDeckZone()->IsEmpty())
        {
            py::dict action = action_record("TRADE_CARD");
            action["card_cost"] = card->GetCost();
            action["card_type"] = card->card
                                       ? std::string(EnumToStr(card->card->GetCardType()))
                                       : "UNKNOWN_TYPE";
            action["card_attack"] = card->card && card->card->gameTags.contains(GameTag::ATK)
                                        ? card->card->gameTags.at(GameTag::ATK) : 0;
            action["card_health"] = card->card && card->card->gameTags.contains(GameTag::HEALTH)
                                        ? card->card->gameTags.at(GameTag::HEALTH) : 0;
            action["hand_index"] = handIndex;
            action["card_id"] = card->card ? card->card->id : "";
            action["field_position"] = -1;
            add_target_features(action, nullptr, player);
            actions.append(std::move(action));
        }
        ++handIndex;
    }

    for (Location* location : player->GetFieldZone()->GetLocations())
    {
        if (!location->card || !location->IsPlayableByPlayer() ||
            !location->IsPlayableByCardReq())
        {
            continue;
        }
        add_targeted_actions(actions, "ACTIVATE_LOCATION", location, player);
    }

    auto add_attacks = [&](Character* attacker)
    {
        if (!attacker->CanAttack())
        {
            return;
        }
        for (Character* target : attacker->GetValidAttackTargets(player->opponent))
        {
            if (!attacker->IsValidAttackTarget(player->opponent, target))
            {
                continue;
            }
            py::dict action = action_record("ATTACK");
            add_source_features(action, attacker);
            add_target_features(action, target, player);
            action["attacker_entity_id"] = tag_value(attacker, GameTag::ENTITY_ID);
            actions.append(std::move(action));
        }
    };

    add_attacks(player->GetHero());
    for (Minion* minion : player->GetFieldZone()->GetMinions())
    {
        add_attacks(minion);
    }

    HeroPower& heroPower = player->GetHeroPower();
    if (heroPower.card && !heroPower.IsExhausted() && heroPower.card->chooseCardIDs.empty() &&
        heroPower.IsPlayableByPlayer() && heroPower.IsPlayableByCardReq())
    {
        add_targeted_actions(actions, "HERO_POWER", &heroPower, player);
    }

    actions.append(action_record("END_TURN"));
    return actions;
}

py::dict game_observation(Game& game, Player* viewer)
{
    Player* opponent = viewer == game.GetPlayer1() ? game.GetPlayer2() : game.GetPlayer1();
    py::dict state;
    state["turn_number"] = game.GetTurn();
    state["active_player"] = game.GetCurrentPlayer() == viewer ? "SELF" : "OPPONENT";
    state["self_player"] = player_observation(viewer);
    state["opponent"] = player_observation(opponent);

    py::list hand;
    for (Playable* card : viewer->GetHandZone()->GetAll())
    {
        hand.append(playable_features(card));
    }
    state["self_hand"] = std::move(hand);
    state["self_hand_known_count"] = viewer->GetHandZone()->GetCount();
    state["opponent_known_cards"] = py::list();
    return state;
}

std::vector<std::string> validate_deck(const std::vector<std::string>& deck,
                                       const std::string& className,
                                       const std::string& format);

class SimulatorSession
{
 public:
    SimulatorSession(const std::vector<std::string>& player1Deck,
                     const std::vector<std::string>& player2Deck,
                     const std::string& player1Class,
                     const std::string& player2Class,
                     const std::string& formatName,
                     bool shuffle,
                     bool randomStart,
                     std::uint32_t randomSeed)
    {
        if (player1Deck.size() != START_DECK_SIZE || player2Deck.size() != START_DECK_SIZE)
        {
            throw std::invalid_argument("Each deck must contain exactly 30 card IDs");
        }

        Random::seed(randomSeed);
        Cards::GetInstance();
        const auto player1Errors =
            validate_deck(player1Deck, player1Class, formatName);
        const auto player2Errors =
            validate_deck(player2Deck, player2Class, formatName);
        if (!player1Errors.empty())
        {
            throw std::invalid_argument("Player 1 deck validation failed: " +
                                        player1Errors.front());
        }
        if (!player2Errors.empty())
        {
            throw std::invalid_argument("Player 2 deck validation failed: " +
                                        player2Errors.front());
        }

        GameConfig config;
        config.player1Class = StrToEnum<CardClass>(player1Class);
        config.player2Class = StrToEnum<CardClass>(player2Class);
        if (formatName == "STANDARD")
        {
            config.formatType = FormatType::STANDARD;
        }
        else if (formatName == "WILD")
        {
            config.formatType = FormatType::WILD;
        }
        else
        {
            throw std::invalid_argument("Format must be STANDARD or WILD");
        }
        if (config.player1Class == CardClass::INVALID || config.player2Class == CardClass::INVALID)
        {
            throw std::invalid_argument("Unknown player class");
        }
        config.startPlayer = randomStart ? PlayerType::RANDOM : PlayerType::PLAYER1;
        config.doShuffle = shuffle;
        config.skipMulligan = true;
        config.autoRun = false;

        for (int i = 0; i < START_DECK_SIZE; ++i)
        {
            config.player1Deck[i] = Cards::FindCardByID(player1Deck[i]);
            config.player2Deck[i] = Cards::FindCardByID(player2Deck[i]);
            if (!config.player1Deck[i] || config.player1Deck[i]->id.empty() ||
                !config.player2Deck[i] || config.player2Deck[i]->id.empty())
            {
                throw std::invalid_argument("Unknown card ID in one of the decks");
            }
        }

        m_game = std::make_unique<Game>(config);
        m_game->Start();
        m_game->ProcessUntil(Step::MAIN_ACTION);
    }

    py::dict Observation(const std::string& perspective = "ACTIVE")
    {
        Player* viewer = nullptr;
        if (perspective == "ACTIVE")
        {
            viewer = m_game->GetCurrentPlayer();
        }
        else if (perspective == "PLAYER1")
        {
            viewer = m_game->GetPlayer1();
        }
        else if (perspective == "PLAYER2")
        {
            viewer = m_game->GetPlayer2();
        }
        else
        {
            throw std::invalid_argument("perspective must be ACTIVE, PLAYER1, or PLAYER2");
        }
        return game_observation(*m_game, viewer);
    }

    py::list LegalActions()
    {
        if (m_game->state == State::COMPLETE)
        {
            return py::list();
        }
        return enumerate_legal_actions(*m_game, m_game->GetCurrentPlayer());
    }

    bool IsComplete() const
    {
        return m_game->state == State::COMPLETE;
    }

    bool NeedsChoice() const
    {
        return m_game->state != State::COMPLETE && m_game->GetCurrentPlayer()->choice != nullptr;
    }

    py::object Result() const
    {
        if (m_game->state != State::COMPLETE)
        {
            return py::none();
        }
        const PlayState player1State = m_game->GetPlayer1()->playState;
        const PlayState player2State = m_game->GetPlayer2()->playState;
        if (player1State == PlayState::WON || player2State == PlayState::LOST)
        {
            return py::str("PLAYER1_WIN");
        }
        if (player2State == PlayState::WON || player1State == PlayState::LOST)
        {
            return py::str("PLAYER2_WIN");
        }
        if (player1State == PlayState::TIED && player2State == PlayState::TIED)
        {
            return py::str("DRAW");
        }
        return py::str("UNKNOWN");
    }

    py::dict ApplyAction(const py::dict& requested)
    {
        py::dict selected;
        bool isLegal = false;
        for (py::handle candidateHandle : enumerate_legal_actions(*m_game, m_game->GetCurrentPlayer()))
        {
            py::dict candidate = py::reinterpret_borrow<py::dict>(candidateHandle);
            if (requested.equal(candidate))
            {
                selected = candidate;
                isLegal = true;
                break;
            }
        }
        if (!isLegal)
        {
            throw std::invalid_argument("Action is stale or not currently legal");
        }

        Player* actor = m_game->GetCurrentPlayer();
        const std::string type = py::cast<std::string>(selected["type"]);
        if (type == "CHOOSE_CARD")
        {
            const int entityID = py::cast<int>(selected["choice_entity_id"]);
            m_game->Process(actor, PlayerTasks::ChooseTask::Pick(actor, entityID));
        }
        else if (type == "PLAY_CARD")
        {
            const int index = py::cast<int>(selected["hand_index"]);
            const auto hand = actor->GetHandZone()->GetAll();
            if (index < 0 || static_cast<std::size_t>(index) >= hand.size())
            {
                throw std::invalid_argument("Action hand index is no longer valid");
            }
            Character* target = nullptr;
            py::handle targetValue = selected["target_entity_id"];
            if (!targetValue.is_none())
            {
                const int targetID = py::cast<int>(targetValue);
                const auto found = m_game->entityList.find(targetID);
                if (found == m_game->entityList.end())
                {
                    throw std::invalid_argument("Action target no longer exists");
                }
                target = dynamic_cast<Character*>(found->second);
                if (!target)
                {
                    throw std::invalid_argument("Action target is not a character");
                }
            }
            const int fieldPosition = py::cast<int>(selected["field_position"]);
            const int chooseOne = selected.contains("choose_one")
                                      ? py::cast<int>(selected["choose_one"])
                                      : 0;
            m_game->Process(actor, PlayerTasks::PlayCardTask(
                hand[index], target, fieldPosition, chooseOne));
        }
        else if (type == "TRADE_CARD")
        {
            const int index = py::cast<int>(selected["hand_index"]);
            const auto hand = actor->GetHandZone()->GetAll();
            if (index < 0 || static_cast<std::size_t>(index) >= hand.size())
            {
                throw std::invalid_argument("Trade hand index is no longer valid");
            }
            m_game->Process(actor, PlayerTasks::TradeCardTask(hand[index]));
        }
        else if (type == "ACTIVATE_LOCATION")
        {
            const int sourceID = py::cast<int>(selected["source_entity_id"]);
            const auto found = m_game->entityList.find(sourceID);
            if (found == m_game->entityList.end())
            {
                throw std::invalid_argument("Action location no longer exists");
            }
            auto* location = dynamic_cast<Location*>(found->second);
            if (!location)
            {
                throw std::invalid_argument("Action source is not a location");
            }
            Character* target = nullptr;
            py::handle targetValue = selected["target_entity_id"];
            if (!targetValue.is_none())
            {
                const int targetID = py::cast<int>(targetValue);
                const auto targetIt = m_game->entityList.find(targetID);
                if (targetIt == m_game->entityList.end())
                {
                    throw std::invalid_argument("Action target no longer exists");
                }
                target = dynamic_cast<Character*>(targetIt->second);
                if (!target)
                {
                    throw std::invalid_argument("Action target is not a character");
                }
            }
            m_game->Process(actor, PlayerTasks::PlayLocationTask(location, target));
        }
        else if (type == "ATTACK")
        {
            const int attackerID = py::cast<int>(selected["attacker_entity_id"]);
            const int targetID = py::cast<int>(selected["target_entity_id"]);
            const auto attackerIt = m_game->entityList.find(attackerID);
            const auto targetIt = m_game->entityList.find(targetID);
            if (attackerIt == m_game->entityList.end() || targetIt == m_game->entityList.end())
            {
                throw std::invalid_argument("Action attacker or target no longer exists");
            }
            m_game->Process(actor, PlayerTasks::AttackTask(attackerIt->second, targetIt->second));
        }
        else if (type == "HERO_POWER")
        {
            Playable* target = nullptr;
            py::handle targetValue = selected["target_entity_id"];
            if (!targetValue.is_none())
            {
                const int targetID = py::cast<int>(targetValue);
                const auto found = m_game->entityList.find(targetID);
                if (found == m_game->entityList.end())
                {
                    throw std::invalid_argument("Action target no longer exists");
                }
                target = found->second;
            }
            m_game->Process(actor, PlayerTasks::HeroPowerTask(target));
        }
        else if (type == "END_TURN")
        {
            m_game->Process(actor, PlayerTasks::EndTurnTask());
        }

        if (m_game->state != State::COMPLETE && !m_game->GetCurrentPlayer()->choice)
        {
            m_game->ProcessUntil(Step::MAIN_ACTION);
        }
        return Observation("ACTIVE");
    }

 private:
    std::unique_ptr<Game> m_game;
};
bool is_hero_class(CardClass cardClass)
{
    switch (cardClass)
    {
        case CardClass::DEATHKNIGHT:
        case CardClass::DRUID:
        case CardClass::HUNTER:
        case CardClass::MAGE:
        case CardClass::PALADIN:
        case CardClass::PRIEST:
        case CardClass::ROGUE:
        case CardClass::SHAMAN:
        case CardClass::WARLOCK:
        case CardClass::WARRIOR:
        case CardClass::DEMONHUNTER:
            return true;
        default:
            return false;
    }
}

bool card_in_format(const Card* card, const std::string& format)
{
    if (format == "STANDARD")
    {
        return card->IsStandardSet();
    }
    if (format == "WILD")
    {
        return card->IsStandardSet() || card->IsWildSet();
    }
    return false;
}

bool has_simulator_rules(const Card* card)
{
    // Textless cards need no scripted effect; text-bearing cards need an
    // explicit CardDef. This is a conservative admission gate, not proof that
    // the implementation matches the live game in every edge case.
    return card->text.empty() || CardDefs::HasCardDefByID(card->id);
}

std::vector<std::string> validate_deck(const std::vector<std::string>& deck,
                                       const std::string& className,
                                       const std::string& format)
{
    Cards::GetInstance();
    std::vector<std::string> errors;
    const CardClass playerClass = StrToEnum<CardClass>(className);
    const bool validClass = is_hero_class(playerClass);
    if (!validClass)
    {
        errors.emplace_back("Unknown or invalid player class: " + className);
    }
    if (format != "STANDARD" && format != "WILD")
    {
        errors.emplace_back("Format must be STANDARD or WILD");
    }
    if (deck.size() != START_DECK_SIZE)
    {
        errors.emplace_back("Deck must contain exactly 30 card IDs (got " +
                            std::to_string(deck.size()) + ")");
    }

    std::map<int, std::pair<int, Card*>> countsByDbfId;
    std::unordered_set<std::string> missingRulesReported;
    for (std::size_t index = 0; index < deck.size(); ++index)
    {
        Card* card = Cards::FindCardByID(deck[index]);
        if (!card || card->id.empty())
        {
            errors.emplace_back("Card " + std::to_string(index + 1) +
                                " is unknown to RosettaStone: " + deck[index]);
            continue;
        }
        if (!card->IsCollectible())
        {
            errors.emplace_back("Card is not collectible: " + card->name +
                                " (" + card->id + ")");
        }
        if (!has_simulator_rules(card) &&
            missingRulesReported.emplace(card->id).second)
        {
            errors.emplace_back("Card rules are not implemented in RosettaStone: " +
                                card->name + " (" + card->id + ")");
        }
        if ((format == "STANDARD" || format == "WILD") && !card_in_format(card, format))
        {
            errors.emplace_back("Card is outside the configured " + format +
                                " card pool: " +
                                card->name + " (" + card->id + ", set " +
                                std::string(EnumToStr(card->GetCardSet())) +
                                ")");
        }
        if (validClass && card->GetCardClass() != CardClass::NEUTRAL &&
            !card->IsCardClass(playerClass))
        {
            errors.emplace_back("Card is not allowed for " + className +
                                ": " + card->name + " (" + card->id + ")");
        }
        auto& entry = countsByDbfId[card->dbfID];
        ++entry.first;
        entry.second = card;
    }

    for (const auto& [dbfId, entry] : countsByDbfId)
    {
        (void)dbfId;
        const int count = entry.first;
        Card* card = entry.second;
        const auto limit = static_cast<int>(card->GetMaxAllowedInDeck());
        if (count > limit)
        {
            errors.emplace_back("Too many copies of " + card->name +
                                " (" + std::to_string(count) +
                                "; maximum " + std::to_string(limit) + ")");
        }
    }
    return errors;
}

py::list list_deck_candidates(const std::string& className,
                              const std::string& format)
{
    Cards::GetInstance();
    const CardClass playerClass = StrToEnum<CardClass>(className);
    if (!is_hero_class(playerClass))
    {
        throw std::invalid_argument("Unknown or invalid player class: " + className);
    }
    if (format != "STANDARD" && format != "WILD")
    {
        throw std::invalid_argument("Format must be STANDARD or WILD");
    }

    py::list result;
    for (Card* card : Cards::GetAllCards())
    {
        if (!card->IsCollectible() || !card_in_format(card, format) ||
            card->GetCardType() != CardType::MINION ||
            !has_simulator_rules(card) ||
            (card->GetCardClass() != CardClass::NEUTRAL &&
             !card->IsCardClass(playerClass)) ||
            !card->chooseCardIDs.empty() || card->HasGameTag(GameTag::BATTLECRY))
        {
            continue;
        }
        py::dict item;
        item["card_id"] = card->id;
        item["dbf_id"] = card->dbfID;
        item["name"] = card->name;
        item["cost"] = card->GetCost();
        item["max_copies"] = card->GetMaxAllowedInDeck();
        result.append(std::move(item));
    }
    return result;
}

py::dict inspect_decks(const std::vector<std::string>& player1Deck,
                       const std::vector<std::string>& player2Deck,
                       const std::string& player1Class,
                       const std::string& player2Class)
{
    if (player1Deck.size() != START_DECK_SIZE || player2Deck.size() != START_DECK_SIZE)
    {
        throw std::invalid_argument("Each deck must contain exactly 30 card IDs");
    }

    Cards::GetInstance();
    GameConfig config;
    config.player1Class = StrToEnum<CardClass>(player1Class);
    config.player2Class = StrToEnum<CardClass>(player2Class);
    if (config.player1Class == CardClass::INVALID || config.player2Class == CardClass::INVALID)
    {
        throw std::invalid_argument("Unknown player class");
    }
    config.startPlayer = PlayerType::PLAYER1;
    config.doShuffle = false;
    config.skipMulligan = true;
    config.autoRun = false;

    for (int i = 0; i < START_DECK_SIZE; ++i)
    {
        config.player1Deck[i] = Cards::FindCardByID(player1Deck[i]);
        config.player2Deck[i] = Cards::FindCardByID(player2Deck[i]);
        if (!config.player1Deck[i] || config.player1Deck[i]->id.empty() ||
            !config.player2Deck[i] || config.player2Deck[i]->id.empty())
        {
            throw std::invalid_argument("Unknown card ID in one of the decks");
        }
    }

    Game game(config);
    game.Start();
    game.ProcessUntil(Step::MAIN_ACTION);
    Player* self = game.GetPlayer1();
    Player* opponent = game.GetPlayer2();

    py::dict state;
    state["turn_number"] = game.GetTurn();
    state["active_player"] = game.GetCurrentPlayer() == self ? "SELF" : "OPPONENT";
    state["self_player"] = player_observation(self);
    state["opponent"] = player_observation(opponent);
    py::list hand;
    for (Playable* card : self->GetHandZone()->GetAll())
    {
        hand.append(playable_features(card));
    }
    state["self_hand"] = std::move(hand);
    state["self_hand_known_count"] = self->GetHandZone()->GetCount();
    state["opponent_known_cards"] = py::list();

    py::dict result;
    result["state"] = std::move(state);
    result["legal_actions"] = enumerate_legal_actions(game, self);
    return result;
}
py::dict make_instance_observation_fixture()
{
    GameConfig config;
    config.player1Class = CardClass::WARRIOR;
    config.player2Class = CardClass::WARRIOR;
    config.startPlayer = PlayerType::PLAYER1;
    config.fillCardIDs = {"CS2_182", "CS2_200", "CS2_131", "CS2_172", "CS2_122", "CS2_142", "CS2_196", "CS2_120", "CS2_168"};
    config.doFillDecks = true;
    config.doShuffle = false;
    config.skipMulligan = true;
    config.autoRun = false;
    Cards::GetInstance();
    Game game(config);
    game.Start();
    game.ProcessUntil(Step::MAIN_ACTION);
    Player* player = game.GetPlayer1();
    Playable* held = player->GetHandZone()->GetAll().front();
    held->SetGameTag(GameTag::ATK, 5);
    held->SetGameTag(GameTag::HEALTH, 5);
    held->SetGameTag(GameTag::COST, 1);
    auto* weapon = dynamic_cast<Weapon*>(Entity::GetFromCard(player, Cards::FindCardByID("CS2_106")));
    Generic::PlayWeapon(player, weapon, nullptr);
    weapon->SetAttack(5);
    weapon->SetDurability(1);
    py::dict result;
    result["hand_card"] = playable_features(held);
    result["weapon"] = player_observation(player)["weapon"];
    return result;
}

py::dict make_sample_observation()
{
    std::string stage = "configure game";
    try
    {
        GameConfig config;
        config.player1Class = CardClass::WARLOCK;
        config.player2Class = CardClass::PALADIN;
        config.startPlayer = PlayerType::PLAYER1;
        config.fillCardIDs = {"CS2_182", "CS2_200", "CS2_131", "CS2_172", "CS2_122", "CS2_142", "CS2_196", "CS2_120", "CS2_168"};
        config.doFillDecks = true;
        config.doShuffle = false;
        config.skipMulligan = true;
        config.autoRun = false;

        Cards::GetInstance();
        stage = "construct game";
        Game game(config);
        stage = "start game";
        game.Start();
        stage = "process to action";
        game.ProcessUntil(Step::MAIN_ACTION);

        Player* self = game.GetPlayer1();
        Playable* sampleMinion = nullptr;
        for (Playable* card : self->GetHandZone()->GetAll())
        {
            if (card->card && card->card->id == "CS2_168")
            {
                sampleMinion = card;
                break;
            }
        }
        if (!sampleMinion)
        {
            throw std::runtime_error("Deterministic fixture did not draw CS2_168");
        }
        stage = "play known 1-mana minion";
        game.Process(game.GetCurrentPlayer(), PlayerTasks::PlayCardTask::Minion(sampleMinion));

        Player* opponent = game.GetPlayer2();
        py::dict observation;
        observation["turn_number"] = game.GetTurn();
        observation["active_player"] = game.GetCurrentPlayer() == self ? "SELF" : "OPPONENT";
        stage = "read self observation";
        observation["self_player"] = player_observation(self);
        stage = "read opponent observation";
        observation["opponent"] = player_observation(opponent);

        stage = "read self hand";
        py::list hand;
        for (Playable* card : self->GetHandZone()->GetAll())
        {
            hand.append(playable_features(card));
        }
        observation["self_hand"] = std::move(hand);
        observation["self_hand_known_count"] = self->GetHandZone()->GetCount();
        observation["opponent_known_cards"] = py::list();
        return observation;
    }
    catch (const std::out_of_range& error)
    {
        throw std::runtime_error(stage + ": " + error.what());
    }
}
}  // namespace

PYBIND11_MODULE(mana_rosetta_bridge, module)
{
    module.doc() = "Minimal player-visible observation bridge for RosettaStone";
    py::class_<SimulatorSession>(module, "SimulatorSession")
        .def(py::init<const std::vector<std::string>&, const std::vector<std::string>&, const std::string&, const std::string&, const std::string&, bool, bool, std::uint32_t>(), py::arg("player1_deck"), py::arg("player2_deck"), py::arg("player1_class") = "WARLOCK", py::arg("player2_class") = "PALADIN", py::arg("format") = "STANDARD", py::arg("shuffle") = false, py::arg("random_start") = false, py::arg("random_seed") = 0)
        .def("observation", &SimulatorSession::Observation, py::arg("perspective") = "ACTIVE")
        .def("legal_actions", &SimulatorSession::LegalActions)
        .def("apply_action", &SimulatorSession::ApplyAction)
        .def("is_complete", &SimulatorSession::IsComplete)
        .def("needs_choice", &SimulatorSession::NeedsChoice)
        .def("result", &SimulatorSession::Result);
    module.def("inspect_decks", &inspect_decks, py::arg("player1_deck"), py::arg("player2_deck"), py::arg("player1_class") = "WARLOCK", py::arg("player2_class") = "PALADIN", "Create an opening position and enumerate its basic legal actions");
    module.def("validate_deck", &validate_deck, py::arg("deck"), py::arg("player_class"), py::arg("format") = "STANDARD", "Validate deck size, card legality, class, collectibility, and copy limits");
    module.def("list_deck_candidates", &list_deck_candidates, py::arg("player_class"), py::arg("format") = "STANDARD", "List collectible, class-legal minions suitable for simple test decks");
    module.def("make_sample_observation", &make_sample_observation,
               "Start a deterministic sample match and export player-visible state");
    module.def("make_instance_observation_fixture", &make_instance_observation_fixture,
               "Diagnostic fixture for modified visible hand and weapon instances");
}
