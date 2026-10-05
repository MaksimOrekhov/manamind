"""Synthetic Power.log builders for collector tests. No real log data is used."""

from __future__ import annotations

SECRET_NAME = "SecretPlayer#4242"  # sentinel that must never reach console/summary output

_HAND_CARDS = ["CS2_029", "CS2_023", "CS2_024", "CS2_025", "CS2_026"]


class Clock:
    """Strictly increasing fake timestamps."""

    def __init__(self) -> None:
        self._tick = 0

    def stamp(self) -> str:
        self._tick += 1
        seconds = self._tick
        return f"D 20:{seconds // 60 % 60:02d}:{seconds % 60:02d}.0000000"


def build_game(
    *,
    seed: int,
    game_type: str | None = "GT_RANKED",
    format_type: str | None = "FT_STANDARD",
    complete: bool = True,
    result: str = "WON",
    variant: int = 0,
    extra_meta: list[str] | None = None,
    turn_in_header: int | None = None,
    clock: Clock | None = None,
) -> list[str]:
    """Lines of one game section. ``game_type=None`` omits the GameType line entirely."""
    clock = clock or Clock()
    power = "{} GameState.DebugPrintPower() - "
    game = "{} GameState.DebugPrintGame() - "
    out: list[str] = []

    def p(text: str) -> None:
        out.append(power.format(clock.stamp()) + text)

    def g(text: str) -> None:
        out.append(game.format(clock.stamp()) + text)

    hero = lambda eid, controller: [  # noqa: E731
        f"FULL_ENTITY - Creating ID={eid} CardID=HERO_0{controller}",
        "    tag=CARDTYPE value=HERO", "    tag=ZONE value=PLAY",
        f"    tag=CONTROLLER value={controller}", f"    tag=ENTITY_ID value={eid}",
        "    tag=HEALTH value=30",
    ]

    p("CREATE_GAME")
    p("    GameEntity EntityID=1")
    p("        tag=CARDTYPE value=GAME")
    p("        tag=ZONE value=PLAY")
    p("        tag=ENTITY_ID value=1")
    p(f"        tag=GAME_SEED value={seed}")
    if turn_in_header is not None:
        p(f"        tag=TURN value={turn_in_header}")
    for entity_id, player_id, hero_id in ((2, 1, 4), (3, 2, 5)):
        p(f"    Player EntityID={entity_id} PlayerID={player_id} GameAccountId=[hi=1 lo={player_id}]")
        p(f"        tag=CONTROLLER value={player_id}")
        p("        tag=CARDTYPE value=PLAYER")
        p(f"        tag=PLAYER_ID value={player_id}")
        p(f"        tag=HERO_ENTITY value={hero_id}")
        p(f"        tag=ENTITY_ID value={entity_id}")
    g("BuildNumber=1")
    if game_type is not None:
        g(f"GameType={game_type}")
    if format_type is not None:
        g(f"FormatType={format_type}")
    for extra in extra_meta or []:
        g(extra)
    g("ScenarioID=2")
    g(f"PlayerID=1, PlayerName={SECRET_NAME}")
    g("PlayerID=2, PlayerName=Opponent#0001")

    for line in hero(4, 1) + hero(5, 2):
        p(line)
    own_cards = [_HAND_CARDS[(variant + i) % len(_HAND_CARDS)] for i in range(3)]
    for offset, card in enumerate(own_cards):
        p(f"FULL_ENTITY - Creating ID={6 + offset} CardID={card}")
        p("    tag=ZONE value=HAND")
        p("    tag=CONTROLLER value=1")
        p(f"    tag=ENTITY_ID value={6 + offset}")
        p(f"    tag=ZONE_POSITION value={offset + 1}")
    for offset in range(3):
        p(f"FULL_ENTITY - Creating ID={20 + offset} CardID=")
        p("    tag=ZONE value=HAND")
        p("    tag=CONTROLLER value=2")
        p(f"    tag=ENTITY_ID value={20 + offset}")

    p("TAG_CHANGE Entity=GameEntity tag=STATE value=RUNNING")
    for turn in range(1, 3 + variant % 3):
        p(f"TAG_CHANGE Entity=GameEntity tag=TURN value={turn}")
        p("TAG_CHANGE Entity=2 tag=CURRENT_PLAYER value=1")
        p("TAG_CHANGE Entity=3 tag=CURRENT_PLAYER value=0")
        p(f"TAG_CHANGE Entity=2 tag=RESOURCES value={turn}")
        card_id = 6 + (turn - 1) % 3
        p(
            f"BLOCK_START BlockType=PLAY Entity=[entityName=Card id={card_id} zone=HAND "
            f"zonePos={turn} cardId={own_cards[(turn - 1) % 3]} player=1] "
            "EffectCardId= EffectIndex=0 Target=0 SubOption=-1"
        )
        p(f"    TAG_CHANGE Entity=2 tag=RESOURCES_USED value={turn}")
        p("BLOCK_END")

    if complete:
        loser = "LOST" if result == "WON" else "WON"
        p(f"TAG_CHANGE Entity=2 tag=PLAYSTATE value={'TIED' if result == 'TIED' else result}")
        p(f"TAG_CHANGE Entity=3 tag=PLAYSTATE value={'TIED' if result == 'TIED' else loser}")
        p("TAG_CHANGE Entity=GameEntity tag=NEXT_STEP value=FINAL_WRAPUP")
        p("TAG_CHANGE Entity=GameEntity tag=STATE value=COMPLETE")
    return out


def to_text(*games: list[str], trailing_newline: bool = True) -> str:
    text = "\n".join(line for game in games for line in game)
    return text + ("\n" if trailing_newline else "")
