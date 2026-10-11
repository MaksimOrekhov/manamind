"""Controlled demonstration scenarios for the forecaster (CLI: ``scripts/action_outcome_demo.py``).

Every number below is written out by hand. The cards are real catalog cards, so their rules text
comes from the pinned catalog; the minions are synthetic vanilla bodies registered next to them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from manamind.domain.game_state import GameState
from manamind.outcome import scenario as sc
from manamind.outcome.texts import TextSource

VANILLA = ("DEMO_ENEMY_6_6", "DEMO_ENEMY_2_2", "DEMO_OWN_3_3", "DEMO_ENEMY_SHIELD", "DEMO_ENEMY_LIFESTEAL",
           "DEMO_ENEMY_DAMAGED", "DEMO_OWN_5_5")


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    title: str
    state: GameState
    actions: tuple[dict[str, Any], ...]


def demo_texts(base: TextSource) -> TextSource:
    return base.extended([{"id": card, "text": "", "type": "MINION", "mechanics": []} for card in VANILLA],
                         source="demo")


def hold_them_off() -> Scenario:
    """The motivating case: Hold Them Off! (JAIL_913) offered on an enemy 6/6, next to its alternatives."""
    mine = (sc.minion("DEMO_OWN_3_3", 3, 3, 1, can_attack=True),)
    theirs = (sc.minion("DEMO_ENEMY_6_6", 6, 6, 1), sc.minion("DEMO_ENEMY_2_2", 2, 2, 2))
    hand = (sc.hand_card("JAIL_913", "SPELL", 5), sc.hand_card("CORE_CS2_029", "SPELL", 4),
            sc.hand_card("CORE_AT_055", "SPELL", 1))
    state = sc.position(self_side=sc.side(mana=5, board=mine, hero_health=24), opponent=sc.side(board=theirs),
                        hand=hand)
    big, small, own = (sc.target_minion("OPPONENT", 1, "DEMO_ENEMY_6_6"),
                       sc.target_minion("OPPONENT", 2, "DEMO_ENEMY_2_2"),
                       sc.target_minion("SELF", 1, "DEMO_OWN_3_3"))
    return Scenario("hold-them-off", "Hold Them Off! on an enemy 6/6 versus its alternatives", state, (
        sc.play("JAIL_913", 0, "SPELL", 5, big),
        sc.play("JAIL_913", 0, "SPELL", 5, small),
        sc.play("JAIL_913", 0, "SPELL", 5, own),
        sc.play("CORE_CS2_029", 1, "SPELL", 4, big),
        sc.play("CORE_CS2_029", 1, "SPELL", 4, sc.target_hero("OPPONENT")),
        sc.play("CORE_AT_055", 2, "SPELL", 1, sc.target_hero("SELF")),
        sc.attack(1, "DEMO_OWN_3_3", small),
        sc.end_turn(),
    ))


def sequencing() -> list[Scenario]:
    """Cases where a one-line calculation gives the wrong answer because of resolution order."""
    cases = []
    shield_state = sc.position(
        self_side=sc.side(mana=5), opponent=sc.side(board=(sc.minion("DEMO_ENEMY_SHIELD", 4, 3, 1,
                                                                   divine_shield=True),)),
        hand=(sc.hand_card("CATA_303", "SPELL", 2),))
    shield_target = sc.target_minion("OPPONENT", 1, "DEMO_ENEMY_SHIELD")
    cases.append(Scenario(
        "shield-before-condition",
        "Purifying Breath (5 damage, 'if it dies' restore 5 to the enemy hero) on a Divine Shield minion",
        shield_state, (sc.play("CATA_303", 0, "SPELL", 2, shield_target),)))
    cases.append(Scenario(
        "lifesteal-overkill",
        "Drain Soul (Lifesteal, 3 damage) on a 1-Health minion while at 20/30: heals the full 3, not 1",
        sc.position(self_side=sc.side(mana=5, hero_health=20),
                    opponent=sc.side(board=(sc.minion("DEMO_ENEMY_DAMAGED", 2, 1, 1),)),
                    hand=(sc.hand_card("CORE_ICC_055", "SPELL", 2),)),
        (sc.play("CORE_ICC_055", 0, "SPELL", 2, sc.target_minion("OPPONENT", 1, "DEMO_ENEMY_DAMAGED")),)))
    cases.append(Scenario(
        "poison-versus-shield",
        "A Poisonous minion attacks a Divine Shield minion: the shield absorbs the hit, so no poison kill",
        sc.position(self_side=sc.side(board=(sc.minion("DEMO_OWN_3_3", 1, 3, 1, poisonous=True, can_attack=True),)),
                    opponent=sc.side(board=(sc.minion("DEMO_ENEMY_SHIELD", 4, 9, 1, divine_shield=True),))),
        (sc.attack(1, "DEMO_OWN_3_3", sc.target_minion("OPPONENT", 1, "DEMO_ENEMY_SHIELD")),)))
    cases.append(Scenario(
        "already-has-keyword",
        "Hold Them Off! on an enemy that already has Lifesteal: only the +5/+5 is new",
        sc.position(self_side=sc.side(mana=5), opponent=sc.side(board=(
            sc.minion("DEMO_ENEMY_LIFESTEAL", 6, 6, 1, lifesteal=True),)),
                    hand=(sc.hand_card("JAIL_913", "SPELL", 5),)),
        (sc.play("JAIL_913", 0, "SPELL", 5, sc.target_minion("OPPONENT", 1, "DEMO_ENEMY_LIFESTEAL")),)))
    cases.append(Scenario(
        "unknown-battlecry",
        "A minion with a Battlecry outside the grammar: the body is exact, the Battlecry is reported unknown",
        sc.position(self_side=sc.side(mana=5), opponent=sc.side(),
                    hand=(sc.hand_card("CORE_EX1_193", "MINION", 1, attack=2, health=2,
                                       mechanics=("BATTLECRY",)),)),
        (sc.play("CORE_EX1_193", 0, "MINION", 1, play_position=1),)))
    return cases


def board_summary(state: GameState) -> str:
    def side(label: str, player) -> str:
        minions = ", ".join(
            f"#{e.board_position} {e.card.card_id} {e.current_attack}/{e.current_health}"
            + "".join(f" [{flag}]" for flag in ("taunt", "divine_shield", "lifesteal", "poisonous", "reborn",
                                                 "stealth", "windfury", "immune") if getattr(e, flag))
            for e in player.board) or "-"
        return (f"  {label}: hero {player.hero_health} armor {player.armor} mana {player.available_mana} "
                f"hand {player.hand_size} secrets {player.secret_count} | board: {minions}")
    return "\n".join((side("SELF", state.self_player), side("OPPONENT", state.opponent)))
