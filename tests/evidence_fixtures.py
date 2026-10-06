"""Synthetic Power.log builder for the evidence extractor tests. No real log data is used.

Layout (S = SELF's player id, O = the other; player 1 owns entity 2 and hero 4, player 2 entity 3, hero 5):

    6-8   SELF hand            20-22 opponent hand (identities empty)     30-31 opponent deck
    41    SELF minion TEST_FRIEND                  50  opponent minion TEST_ENEMY
"""

from __future__ import annotations

from power_log_fixtures import SECRET_NAME

ACCOUNT_LO = "98765432101"  # an account-id fragment that must never reach the output
BATTLETAG = SECRET_NAME


def desc(entity_id: int, zone: str, position: int, card_id: str, player: int) -> str:
    return f"[entityName=X id={entity_id} zone={zone} zonePos={position} cardId={card_id} player={player}]"


# -- packet line builders (relative indentation; ``blk`` indents a body one level) ---------------

def tag(entity, name, value) -> list[str]:
    return [f"TAG_CHANGE Entity={entity} tag={name} value={value}"]


def full(entity_id, card_id, **tags) -> list[str]:
    lines = [f"FULL_ENTITY - Creating ID={entity_id} CardID={card_id}"]
    lines += [f"    tag={name} value={value}" for name, value in tags.items()]
    return lines


def show(entity_id, card_id, **tags) -> list[str]:
    lines = [f"SHOW_ENTITY - Updating Entity={entity_id} CardID={card_id}"]
    lines += [f"    tag={name} value={value}" for name, value in tags.items()]
    return lines


def hide(entity_id, zone, card_id, player, position=1) -> list[str]:
    return [f"HIDE_ENTITY - Entity={desc(entity_id, zone, position, card_id, player)} tag=ZONE value={zone}"]


def change(entity_id, card_id) -> list[str]:
    return [f"CHANGE_ENTITY - Updating Entity={entity_id} CardID={card_id}"]


def meta(kind, data, *targets) -> list[str]:
    lines = [f"META_DATA - Meta={kind} Data={data} InfoCount={len(targets)}"]
    lines += [f"    Info[{i}] = {target}" for i, target in enumerate(targets)]
    return lines


def subspell(body: list[str]) -> list[str]:
    return ["SUB_SPELL_START - SpellPrefabGUID=TEST_Fab:abc Source=0 TargetCount=0",
            *[f"    {line}" for line in body], "SUB_SPELL_END"]


def blk(block_type, entity, body=(), *, target=0, keyword=None) -> list[str]:
    extra = f" TriggerKeyword={keyword}" if keyword is not None else ""
    head = f"BLOCK_START BlockType={block_type} Entity={entity} EffectCardId= EffectIndex=0 Target={target} SubOption=-1{extra}"
    return [head, *[f"    {line}" for line in body], "BLOCK_END"]


def flat(*parts: list[str]) -> list[str]:
    return [line for part in parts for line in part]


class EvLog:
    def __init__(self, *, self_pid: int = 1, seed: int = 7, game_type: str | None = "GT_RANKED",
                 format_type: str | None = "FT_STANDARD", hand: dict | None = None, build: int = 253216) -> None:
        self.self_pid = self_pid
        self.opp_pid = 3 - self_pid
        self.seed, self.game_type, self.format_type, self.build = seed, game_type, format_type, build
        self.hand = hand or {6: ("TEST_SPELL", "SPELL"), 7: ("TEST_MINION", "MINION"), 8: ("TEST_OTHER", "SPELL")}
        self.lines: list[str] = []
        self.tick = 0
        self.options_id = 0

    # -- low level ---------------------------------------------------------------------------

    def _stamp(self) -> str:
        self.tick += 1
        seconds, fraction = divmod(self.tick * 100_000, 10_000_000)
        return f"D 20:{seconds // 60 % 60:02d}:{seconds % 60:02d}.{fraction:07d}"

    def raw(self, owner: str, method: str, text: str) -> None:
        self.lines.append(f"{self._stamp()} {owner}.{method}() - {text}")

    def p(self, text: str) -> None:
        self.raw("GameState", "DebugPrintPower", text)

    def power(self, lines: list[str]) -> EvLog:
        for line in lines:
            self.p(line)
        return self

    def entity(self, entity_id, card_id, **tags) -> None:
        self.power(full(entity_id, card_id, **{**tags, "ENTITY_ID": entity_id}))

    # -- game --------------------------------------------------------------------------------

    def create(self) -> EvLog:
        S, O = self.self_pid, self.opp_pid
        self.p("CREATE_GAME")
        self.p("    GameEntity EntityID=1")
        for line in ("tag=CARDTYPE value=GAME", "tag=ZONE value=PLAY", "tag=ENTITY_ID value=1",
                     f"tag=GAME_SEED value={self.seed}"):
            self.p("        " + line)
        for entity_id, player_id, hero_id in ((2, 1, 4), (3, 2, 5)):
            self.p(f"    Player EntityID={entity_id} PlayerID={player_id} GameAccountId=[hi=144115193835963207 lo={ACCOUNT_LO}{player_id}]")
            for line in (f"tag=CONTROLLER value={player_id}", "tag=CARDTYPE value=PLAYER",
                         f"tag=PLAYER_ID value={player_id}", f"tag=HERO_ENTITY value={hero_id}",
                         f"tag=ENTITY_ID value={entity_id}"):
                self.p("        " + line)
        self.raw("GameState", "DebugPrintGame", f"BuildNumber={self.build}")
        if self.game_type is not None:
            self.raw("GameState", "DebugPrintGame", f"GameType={self.game_type}")
        if self.format_type is not None:
            self.raw("GameState", "DebugPrintGame", f"FormatType={self.format_type}")
        self.raw("GameState", "DebugPrintGame", "ScenarioID=2")
        self.raw("GameState", "DebugPrintGame", f"PlayerID=1, PlayerName={BATTLETAG}")
        self.raw("GameState", "DebugPrintGame", "PlayerID=2, PlayerName=Rival#7777")
        for hero_id, controller in ((4, 1), (5, 2)):
            self.entity(hero_id, f"HERO_0{controller}", CARDTYPE="HERO", ZONE="PLAY", CONTROLLER=controller, HEALTH=30)
        for entity_id, (card_id, card_type) in self.hand.items():
            self.entity(entity_id, card_id, ZONE="HAND", CONTROLLER=S, ZONE_POSITION=entity_id - 5, CARDTYPE=card_type)
        for entity_id in (20, 21, 22):
            self.entity(entity_id, "", ZONE="HAND", CONTROLLER=O, ZONE_POSITION=entity_id - 19)
        for entity_id in (30, 31):
            self.entity(entity_id, "", ZONE="DECK", CONTROLLER=O)
        self.entity(41, "TEST_FRIEND", CARDTYPE="MINION", ZONE="PLAY", CONTROLLER=S, ZONE_POSITION=1, ATK=2, HEALTH=3)
        self.entity(50, "TEST_ENEMY", CARDTYPE="MINION", ZONE="PLAY", CONTROLLER=O, ZONE_POSITION=1, ATK=1, HEALTH=4)
        self.p("TAG_CHANGE Entity=GameEntity tag=STATE value=RUNNING")
        return self

    def start_turn(self, turn: int, player: int) -> EvLog:
        other = 3 - player
        self.p(f"TAG_CHANGE Entity=GameEntity tag=TURN value={turn}")
        self.p("TAG_CHANGE Entity=GameEntity tag=STEP value=MAIN_ACTION")
        self.p(f"TAG_CHANGE Entity={1 + player} tag=CURRENT_PLAYER value=1")
        self.p(f"TAG_CHANGE Entity={1 + other} tag=CURRENT_PLAYER value=0")
        self.p(f"TAG_CHANGE Entity={1 + player} tag=RESOURCES value={turn}")
        return self

    def options(self, entries: list[tuple]) -> EvLog:
        """entries: (entity_id, zone, position, card_id, error, [(target_id, zone, pos, card, ctrl, error)])."""
        self.options_id += 1
        self.raw("GameState", "DebugPrintOptions", f"id={self.options_id}")
        self.raw("GameState", "DebugPrintOptions", "option 0 type=END_TURN mainEntity= error=INVALID errorParam=")
        for index, (entity_id, zone, position, card_id, error, targets) in enumerate(entries, 1):
            self.raw("GameState", "DebugPrintOptions",
                     f"option {index} type=POWER mainEntity={desc(entity_id, zone, position, card_id, self.self_pid)} "
                     f"error={error or 'NONE'} errorParam=")
            for t_index, (t_id, t_zone, t_pos, t_card, t_ctrl, t_error) in enumerate(targets):
                self.raw("GameState", "DebugPrintOptions",
                         f"target {t_index} entity={desc(t_id, t_zone, t_pos, t_card, t_ctrl)} "
                         f"error={t_error or 'NONE'} errorParam=")
        return self

    def hand_option(self, entity_id: int | None = None, targets=()) -> EvLog:
        entity_id = entity_id or 6
        card_id, _ = self.hand[entity_id]
        return self.options([(entity_id, "HAND", entity_id - 5, card_id, None, list(targets))])

    def complete(self) -> EvLog:
        self.p("TAG_CHANGE Entity=GameEntity tag=STATE value=COMPLETE")
        return self

    def build_lines(self) -> list[str]:
        return list(self.lines)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def play_game(body: list[str], *, entity: int = 6, target: int = 0, targets=(), self_pid: int = 1,
              before: list[str] | None = None, **kwargs) -> EvLog:
    """A complete game where SELF plays hand entity ``entity`` with ``body`` as its PLAY block content."""
    log = EvLog(self_pid=self_pid, **kwargs).create()
    log.start_turn(1, self_pid)
    if before:
        log.power(before)
    log.hand_option(entity, targets)
    log.power(blk("PLAY", entity, body, target=target))
    log.complete()
    return log
