"""Synthetic live Power.log builder (options, task lists, choices, hidden-info canaries).

No real log data is used. Entity layout of a built game (SELF is player 1):

    2/3 players, 4/5 heroes, 6-8 SELF hand (known), 10-12 SELF deck, 20-22 opponent hand,
    30-32 opponent deck, 40 SELF hero power, 41 SELF minion, 50 opponent minion
"""

from __future__ import annotations

from power_log_fixtures import SECRET_NAME

SELF_HAND = {6: "CS2_029", 7: "CS2_023", 8: "CS2_024"}

# Identities that must never appear in sanitized output.
CANARY_OPP_HAND = "CANARY_OPP_HAND"
CANARY_OPP_DECK = "CANARY_OPP_DECK"
CANARY_OPP_SETASIDE = "CANARY_OPP_SETASIDE"
CANARY_OPP_SECRET = "CANARY_OPP_SECRET"
CANARY_OVERRIDE = "CANARY_OVERRIDE"
CANARY_HIDDEN_BY_HIDE = "CANARY_SHOW_THEN_HIDE"
CANARIES = (
    CANARY_OPP_HAND, CANARY_OPP_DECK, CANARY_OPP_SETASIDE, CANARY_OPP_SECRET,
    CANARY_OVERRIDE, CANARY_HIDDEN_BY_HIDE,
)


def desc(entity_id: int, zone: str, position: int, card_id: str, player: int, name: str = "X") -> str:
    return (f"[entityName={name} id={entity_id} zone={zone} zonePos={position} "
            f"cardId={card_id} player={player}]")


class LiveLog:
    def __init__(
        self,
        *,
        seed: int = 1,
        game_type: str | None = "GT_RANKED",
        format_type: str | None = "FT_STANDARD",
        turn_in_header: int | None = None,
        canaries: bool = False,
        weapon: bool = False,
    ) -> None:
        self.lines: list[str] = []
        self.tick = 0
        self.seed = seed
        self.game_type = game_type
        self.format_type = format_type
        self.turn_in_header = turn_in_header
        self.canaries = canaries
        self.weapon = weapon
        self.q = 0
        self.options_id = 0

    # -- low level -----------------------------------------------------------

    def stamp(self) -> str:
        self.tick += 1
        total = self.tick * 100_000  # 10 ms steps in 100 ns units
        seconds, fraction = divmod(total, 10_000_000)
        return f"D 20:{seconds // 60 % 60:02d}:{seconds % 60:02d}.{fraction:07d}"

    def raw(self, owner: str, method: str, text: str) -> None:
        self.lines.append(f"{self.stamp()} {owner}.{method}() - {text}")

    def p(self, text: str) -> None:
        self.raw("GameState", "DebugPrintPower", text)

    def g(self, text: str) -> None:
        self.raw("GameState", "DebugPrintGame", text)

    def entity(self, entity_id: int, card_id: str, tags: dict[str, object]) -> None:
        self.p(f"FULL_ENTITY - Creating ID={entity_id} CardID={card_id}")
        for name, value in {**tags, "ENTITY_ID": entity_id}.items():
            self.p(f"    tag={name} value={value}")

    # -- game ----------------------------------------------------------------

    def create_game(self) -> LiveLog:
        self.p("CREATE_GAME")
        self.p("    GameEntity EntityID=1")
        self.p("        tag=CARDTYPE value=GAME")
        self.p("        tag=ZONE value=PLAY")
        self.p("        tag=ENTITY_ID value=1")
        self.p(f"        tag=GAME_SEED value={self.seed}")
        if self.turn_in_header is not None:
            self.p(f"        tag=TURN value={self.turn_in_header}")
        for entity_id, player_id, hero_id in ((2, 1, 4), (3, 2, 5)):
            self.p(f"    Player EntityID={entity_id} PlayerID={player_id} GameAccountId=[hi=1 lo={player_id}]")
            self.p(f"        tag=CONTROLLER value={player_id}")
            self.p("        tag=CARDTYPE value=PLAYER")
            self.p(f"        tag=PLAYER_ID value={player_id}")
            self.p(f"        tag=HERO_ENTITY value={hero_id}")
            self.p(f"        tag=ENTITY_ID value={entity_id}")
        self.g("BuildNumber=253216")
        if self.game_type is not None:
            self.g(f"GameType={self.game_type}")
        if self.format_type is not None:
            self.g(f"FormatType={self.format_type}")
        self.g("ScenarioID=2")
        self.g(f"PlayerID=1, PlayerName={SECRET_NAME}")
        self.g("PlayerID=2, PlayerName=Opponent#0001")

        for hero_id, controller in ((4, 1), (5, 2)):
            self.entity(hero_id, f"HERO_0{controller}", {
                "CARDTYPE": "HERO", "ZONE": "PLAY", "CONTROLLER": controller, "HEALTH": 30,
            })
        for entity_id, card in SELF_HAND.items():
            self.entity(entity_id, card, {
                "ZONE": "HAND", "CONTROLLER": 1, "ZONE_POSITION": entity_id - 5, "CARDTYPE": "MINION",
            })
        for entity_id in (10, 11, 12):
            self.entity(entity_id, "", {"ZONE": "DECK", "CONTROLLER": 1})
        for entity_id in (20, 21, 22):
            self.entity(entity_id, "", {"ZONE": "HAND", "CONTROLLER": 2, "ZONE_POSITION": entity_id - 19})
        for entity_id in (30, 31, 32):
            self.entity(entity_id, "", {"ZONE": "DECK", "CONTROLLER": 2})
        self.entity(40, "HERO_POWER_X", {
            "CARDTYPE": "HERO_POWER", "ZONE": "PLAY", "CONTROLLER": 1, "EXHAUSTED": 0,
        })
        self.entity(41, "CS2_231", {
            "CARDTYPE": "MINION", "ZONE": "PLAY", "CONTROLLER": 1, "ZONE_POSITION": 1,
            "ATK": 2, "HEALTH": 3,
        })
        self.entity(50, "CS2_168", {
            "CARDTYPE": "MINION", "ZONE": "PLAY", "CONTROLLER": 2, "ZONE_POSITION": 1,
            "ATK": 1, "HEALTH": 2,
        })
        if self.weapon:
            # Real logs carry HEALTH/DAMAGE for weapons, not DURABILITY: 4 - 3 = 1 left.
            self.entity(42, "CS2_080", {
                "CARDTYPE": "WEAPON", "ZONE": "PLAY", "CONTROLLER": 1, "ATK": 3, "HEALTH": 4, "DAMAGE": 3,
            })
        if self.canaries:
            self.entity(60, CANARY_OPP_SETASIDE, {"ZONE": "SETASIDE", "CONTROLLER": 2})
            self.entity(61, CANARY_OPP_SECRET, {"ZONE": "SECRET", "CONTROLLER": 2, "CARDTYPE": "SPELL"})
            self.entity(62, CANARY_OPP_DECK, {"ZONE": "DECK", "CONTROLLER": 2})
        self.p("TAG_CHANGE Entity=GameEntity tag=STATE value=RUNNING")
        return self

    def mulligan(self) -> LiveLog:
        self.raw("GameState", "DebugPrintEntityChoices",
                 f"id=1 Player={SECRET_NAME} TaskList=5 ChoiceType=MULLIGAN CountMin=0 CountMax=3")
        self.raw("GameState", "DebugPrintEntityChoices", "  Source=GameEntity")
        self.raw("GameState", "SendChoices", "id=1 ChoiceType=MULLIGAN")
        self.raw("GameState", "SendChoices", f"  m_chosenEntities[0]={desc(6, 'HAND', 1, 'CS2_029', 1)}")
        return self

    def begin_turn(self, turn: int, *, self_turn: bool = True, mana: int | None = None) -> LiveLog:
        mover, other = (2, 3) if self_turn else (3, 2)
        self.batch([
            f"TAG_CHANGE Entity=GameEntity tag=TURN value={turn}",
            f"TAG_CHANGE Entity={mover} tag=CURRENT_PLAYER value=1",
            f"TAG_CHANGE Entity={other} tag=CURRENT_PLAYER value=0",
            f"TAG_CHANGE Entity=2 tag=RESOURCES value={mana if mana is not None else turn}",
        ])
        self.finish_list()
        return self

    # -- task lists, options -------------------------------------------------

    def batch(self, power_lines: list[str]) -> LiveLog:
        """A GameState packet batch followed by the client's task-list queue marker."""
        self.q += 1
        self.raw("GameState", "DebugPrintPowerList", f"Count={len(power_lines)}")
        for text in power_lines:
            self.p(text)
        self.raw("PowerTaskList", "DebugDump", f"ID={self.q} ParentID=0 PreviousID=0 TaskCount={len(power_lines)}")
        return self

    def finish_list(self) -> LiveLog:
        self.raw("PowerProcessor", "EndCurrentTaskList", f"m_currentTaskList={self.q}")
        return self

    def options(self, *, legal: bool = True, targets: bool = True) -> LiveLog:
        self.options_id += 1
        self.raw("GameState", "DebugPrintOptions", f"id={self.options_id}")
        error = "NONE" if legal else "REQ_YOUR_TURN"
        self.raw("GameState", "DebugPrintOptions",
                 "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")  # real logs: always INVALID
        self.raw("GameState", "DebugPrintOptions",
                 f"option 1 type=POWER mainEntity={desc(6, 'HAND', 1, 'CS2_029', 1)} error={error} errorParam=")
        if targets:
            self.raw("GameState", "DebugPrintOptions",
                     f"target 0 entity={desc(50, 'PLAY', 1, 'CS2_168', 2)} error={error} errorParam=")
        self.raw("GameState", "DebugPrintOptions",
                 f"option 2 type=POWER mainEntity={desc(7, 'HAND', 2, 'CS2_023', 1)} "
                 "error=REQ_ENOUGH_MANA errorParam=2")
        self.raw("GameState", "DebugPrintOptions",
                 f"option 3 type=POWER mainEntity={desc(41, 'PLAY', 1, 'CS2_231', 1)} error={error} errorParam=")
        return self

    def send_option(self, index: int = 0) -> LiveLog:
        self.raw("GameState", "SendOption",
                 f"selectedOption={index} selectedSubOption=-1 selectedTarget=0 selectedPosition=0")
        return self

    def self_decision(self, turn: int = 1) -> LiveLog:
        """Own turn starts, the UI finishes, the server offers options."""
        self.begin_turn(turn, self_turn=True)
        return self.options()

    # -- hidden-information canaries ------------------------------------------

    def canary_reveals(self) -> LiveLog:
        """Opponent identities that the log carries but the player never saw."""
        self.batch([
            "BLOCK_START BlockType=TRIGGER Entity=1 EffectCardId= EffectIndex=0 Target=0 SubOption=-1",
            "    META_DATA - Meta=OVERRIDE_HISTORY Data=0 InfoCount=1",
            "        Info[0] = 1",
            f"    SHOW_ENTITY - Updating Entity=20 CardID={CANARY_OVERRIDE}",
            "        tag=ZONE value=HAND",
            "    SHOW_ENTITY - Updating Entity=21 CardID=" + CANARY_HIDDEN_BY_HIDE,
            "        tag=ZONE value=HAND",
            f"    HIDE_ENTITY - Entity={desc(21, 'HAND', 2, CANARY_HIDDEN_BY_HIDE, 2)} tag=ZONE value=HAND",
            "BLOCK_END",
        ])
        self.finish_list()
        return self

    def opponent_hand_identity(self) -> LiveLog:
        self.batch([f"SHOW_ENTITY - Updating Entity=22 CardID={CANARY_OPP_HAND}", "    tag=ZONE value=HAND"])
        self.finish_list()
        return self

    def complete(self) -> LiveLog:
        self.p("TAG_CHANGE Entity=GameEntity tag=STATE value=COMPLETE")
        return self
