"""Human-readable one-snapshot rendering. Card ids only; no names, no raw log text."""

from __future__ import annotations

from .snapshot import Snapshot


def _board(entities: list[dict]) -> str:
    if not entities:
        return "-"
    return ", ".join(
        f"{e['card']['card_id']} {e['current_attack']}/{e['current_health']}"
        + ("" if e.get("can_attack") else "·")
        for e in entities
    )


def _side(label: str, side: dict) -> str:
    weapon = side.get("weapon")
    weapon_text = "-"
    if weapon:
        weapon_text = f"{weapon['card_id']} {weapon.get('current_attack')}/{weapon.get('current_durability')}"
    power = side.get("hero_power_ready")
    return (
        f"  {label} hp {side['hero_health']} armor {side['armor']} "
        f"mana {side['available_mana']}/{side['max_mana']} overload {side['overloaded_mana']} "
        f"hero power {'ready' if power else 'used' if power is False else '?'} weapon {weapon_text}\n"
        f"      hand {side['hand_size']} deck {side['deck_size']} secrets {side['secret_count']}\n"
        f"      board: {_board(side['board'])}"
    )


def render(snapshot: Snapshot) -> str:
    state = snapshot.state
    kinds: dict[str, int] = {}
    for action in snapshot.decision["legal"]:
        kinds[action["kind"]] = kinds.get(action["kind"], 0) + 1
    hand = ", ".join(card["card_id"] for card in state["self_hand"]) or "-"
    legal = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
    return "\n".join([
        f"[#{snapshot.seq}] {snapshot.game_type}/{snapshot.format} turn {snapshot.turn} "
        f"{snapshot.active_player} {snapshot.status} game {snapshot.game_key[:16]} "
        f"build {snapshot.client_build} hash {snapshot.state_hash[:12]}",
        _side("SELF", state["self_player"]),
        f"      hand: {hand}",
        _side("OPP ", state["opponent"]),
        f"  legal: {legal}",
    ])
