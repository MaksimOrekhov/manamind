"""Offline, completed-match action labels using the LIVE visibility/trust contract."""
from __future__ import annotations

import re
from collections import Counter

from hearthstone.enums import GameTag, PlayState
from hslog.player import coerce_to_entity_id

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.lines import inspect_segment
from manamind.live.session import LiveSession
from manamind.live.snapshot import Snapshot
from manamind.live.visibility import has_named_option

from .policy_actions import ActionMappingError, map_actions

OPTIONS = re.compile(r"^[DWE] \S+ GameState\.DebugPrintOptions\(\) -\s*(.*)$")
SEND = re.compile(r"^[DWE] \S+ GameState\.SendOption\(\) -\s*selectedOption=(\d+) "
                  r"selectedSubOption=(-1|\d+) selectedTarget=(\d+) selectedPosition=(\d+)\s*$")
GAME_STATE = re.compile(r"^[DWE] \S+ GameState\.([\w]+)\(\) -")
PUBLIC_BLOCK = re.compile(r"^[DWE] \S+ GameState\.DebugPrintPower\(\) -\s*"
                          r"BLOCK_START BlockType=(\w+) Entity=(.*?) EffectCardId=")


class PolicyImportError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def extract_match(lines: list[str], catalog: CardCatalog) -> tuple[list[dict], dict]:
    """Take complete options at their line boundary, before SendOption mutates state.

    Offline message completeness comes from the next line, not an invented idle delay.
    The real client task-list gate must still be settled. Any intervening GameState
    message invalidates an unanswered candidate; no power-block fallback is guessed.
    """
    info = inspect_segment(lines)
    if info.game_types != {"GT_RANKED"} or info.formats != {"FT_STANDARD"}:
        raise PolicyImportError("MODE_INELIGIBLE")
    if info.mid_game_start or info.start_key is None:
        raise PolicyImportError("MID_GAME_START")
    if info.complete_index is None:
        raise PolicyImportError("INCOMPLETE")
    if any("BLOCK_START BlockType=GAME_RESET" in line for line in lines):
        raise PolicyImportError("GAME_RESET")
    session = LiveSession(catalog)
    examples, skipped, observed = [], [], set()
    candidate = None
    packet = None
    packet_line = 0
    handled = set()
    selections = Counter()
    confirmation = None

    def skip(identifier: int, reason: str) -> None:
        if identifier in handled:
            return
        handled.add(identifier)
        observed.add(identifier)
        skipped.append({"decision_id": f"{info.start_key}:{identifier}", "reason": reason})

    def receive(events):
        nonlocal candidate
        for snapshot in events:
            if not isinstance(snapshot, Snapshot):
                continue
            identifier = snapshot.decision["options_id"]
            observed.add(identifier)
            try:
                from manamind.domain.serialization import game_state_from_dict
                state = game_state_from_dict(snapshot.state)
                mapped = map_actions(packet, session.game.reducer.game,
                                     session.game.self_player_id, state)
                candidate = (snapshot, mapped)
            except ActionMappingError as error:
                skip(identifier, error.reason)

    def finish_confirmation():
        nonlocal confirmation
        if confirmation is not None and not confirmation["confirmed"]:
            identifier = confirmation["id"]
            examples[:] = [row for row in examples if row["decision_id"] != f"{info.start_key}:{identifier}"]
            handled.discard(identifier)
            skip(identifier, "UNSUPPORTED_DECISION_KIND")
        confirmation = None

    for number, line in enumerate(lines[:info.complete_index + 1], 1):
        option_line = OPTIONS.match(line)
        new_options = option_line and option_line.group(1).startswith("id=")
        if new_options:
            finish_confirmation()
        block = PUBLIC_BLOCK.match(line)
        if block and confirmation is not None:
            try:
                actor = session.game.reducer.parser.parse_entity_id(block.group(2))
            except Exception:
                actor = None
            if actor == confirmation["actor"] and block.group(1) == confirmation["block_type"]:
                confirmation["confirmed"] = True
        if not option_line or new_options:
            game = session.game
            if game is not None:
                game.gate.close_message()
                receive(session.tick(number))
        game_state = GAME_STATE.match(line)
        send = SEND.match(line)
        if send and packet is not None:
            selections[packet.id] += 1
            if selections[packet.id] > 1:
                decision_id = f"{info.start_key}:{packet.id}"
                examples[:] = [row for row in examples if row["decision_id"] != decision_id]
                if not any(row["decision_id"] == decision_id for row in skipped):
                    handled.discard(packet.id)
                    skip(packet.id, "AMBIGUOUS_SELECTION")
                candidate = None
                confirmation = None
        if candidate is not None and game_state and game_state.group(1) != "DebugPrintOptions":
            snapshot, mapped = candidate
            identifier = snapshot.decision["options_id"]
            if send:
                try:
                    chosen = mapped.select(*map(int, send.groups()))
                    examples.append({
                        "schema_version": 1, "action_schema_version": 1,
                        "game_id": info.start_key, "decision_id": f"{info.start_key}:{identifier}",
                        "state": snapshot.state, "legal_actions": mapped.actions,
                        "chosen_action_index": chosen, "final_result": None,
                        "source": "power_log_ranked_standard",
                        "provenance": {"options_line": packet_line, "selection_line": number,
                                       "state_hash": snapshot.state_hash},
                    })
                    handled.add(identifier)
                    kind = mapped.actions[chosen]["type"]
                    if kind != "END_TURN":
                        selected = [o for o in packet.options if o.id == int(send.group(1))]
                        confirmation = {"id": identifier,
                                        "actor": int(coerce_to_entity_id(selected[0].entity)),
                                        "block_type": "ATTACK" if kind == "ATTACK" else "PLAY",
                                        "confirmed": False}
                except ActionMappingError as error:
                    skip(identifier, error.reason)
            else:
                skip(identifier, "PARSE_ERROR" if "SendOption()" in line else "OPTIONS_SUPERSEDED")
            candidate = None
        if new_options:
            if candidate is not None:
                skip(candidate[0].decision["options_id"], "OPTIONS_SUPERSEDED")
                candidate = None
            if packet is not None and packet.id not in handled and has_named_option(packet):
                skip(packet.id, "OPTIONS_SUPERSEDED")
            packet_line = number
        receive(session.feed([line], number))
        if new_options and session.game is not None:
            packet = session.game.reducer.last_options()
        if session.game is not None and session.game.failed:
            raise PolicyImportError(session.reason or "PARSE_ERROR")
    if candidate is not None:
        skip(candidate[0].decision["options_id"], "NO_SELECTION")
    finish_confirmation()
    game = session.game
    if game is None or not game.ended or game.self_player_id is None:
        raise PolicyImportError("SELF_AMBIGUOUS")
    try:
        game.reducer.commit()
    except Exception:
        raise PolicyImportError("PARSE_ERROR") from None
    players = [p for p in game.reducer.game.players
               if p.tags.get(GameTag.PLAYER_ID) == game.self_player_id]
    if len(players) != 1:
        raise PolicyImportError("SELF_AMBIGUOUS")
    result = {PlayState.WON: 1.0, PlayState.LOST: 0.0, PlayState.TIED: 0.5}.get(
        players[0].tags.get(GameTag.PLAYSTATE))
    if result is None:
        raise PolicyImportError("RESULT_UNRESOLVED")
    for example in examples:
        example["final_result"] = result
    summary = {
        "schema_version": 1, "game_id": info.start_key, "final_result": result,
        "decisions_total": len(observed), "decisions_labeled": len(examples),
        "decisions_skipped": len(skipped),
        "skip_reasons": dict(sorted(Counter(row["reason"] for row in skipped).items())),
        "skipped_decisions": skipped,
    }
    return examples, summary
