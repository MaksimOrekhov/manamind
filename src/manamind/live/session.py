"""LiveSession: the single owner of live state, driven by complete log lines.

``feed``/``tick`` are pure functions of the lines and the monotonic millisecond clock
they are given, so a recorded slice plus read trace reproduces the same snapshots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from manamind.cards.catalog import CardCatalog
from manamind.integrations.powerlog.lines import (
    COMPLETE_RE,
    CREATE_GAME_RE,
    META_RE,
    PLAYER_HEADER_RE,
    TURN_RE,
    game_key_from_header,
)
from manamind.integrations.powerlog.visible_state import infer_local_player_id

from .gate import DUMP_RE, END_RE, SettleGate
from .reducer import GameReducer, ReducerError
from .snapshot import Snapshot, state_hash, state_to_dict
from .trust import LiveStatus, ModePolicy, Reason, StatusEvent
from .visibility import build_decision, has_candidate_option, has_named_option, option_controllers, project_state

_LINE_RE = re.compile(r"^[DWE] \S+ (\w+)\.(\w+)\(\) - (.*)$")
_CHOSEN_RE = re.compile(r"^m_chosenEntities\[\d+\]=\[.*player=(\d+)\]\s*$")
_BUILD_RE = re.compile(r"^BuildNumber=(\d+)\s*$")
_SPECTATOR_RE = re.compile(r"^[DWE] \S+ ={18}(.*)$")
_SPECTATOR_BEGIN = ("Start Spectator Game", "Begin Spectating 1st player", "Begin Spectating 2nd player")
_SPECTATOR_END = ("End Spectator Mode", "End Spectator Game")

_MODE_OK, _MODE_UNSUPPORTED, _MODE_AMBIGUOUS = "OK", "UNSUPPORTED", "AMBIGUOUS"

LiveEvent = Snapshot | StatusEvent


@dataclass
class GameRun:
    """Everything known about the current CREATE_GAME section. Holds raw lines (private)."""

    reducer: GameReducer = field(default_factory=GameReducer)
    gate: SettleGate = field(default_factory=SettleGate)
    lines: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    game_key: str | None = None
    header_done: bool = False
    mid_game: bool = False
    game_types: set[str] = field(default_factory=set)
    formats: set[str] = field(default_factory=set)
    build: int | None = None
    mode_state: str | None = None
    self_choice_players: set[int] = field(default_factory=set)
    self_player_id: int | None = None
    ended: bool = False
    failed: bool = False
    unsupported_reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.ended or self.failed or self.mode_state != _MODE_OK

    @property
    def game_type(self) -> str:
        return next(iter(self.game_types), "")

    @property
    def format_type(self) -> str:
        return next(iter(self.formats), "")


class LiveSession:
    def __init__(
        self,
        catalog: CardCatalog,
        mode_policy: ModePolicy | None = None,
        session_name: str | None = None,
        *,
        parity_view: bool = False,
    ) -> None:
        self.catalog = catalog
        self.parity_view = parity_view
        self.mode_policy = mode_policy or ModePolicy()
        self.session_name = session_name
        self.status = LiveStatus.WAITING_FOR_GAME
        self.current_snapshot: Snapshot | None = None
        self.reason: str | None = None
        self.game: GameRun | None = None
        self._seq: dict[str, int] = {}
        self._spectating = False
        self._quiet = False
        self._catchup = False
        self._events: list[LiveEvent] = []
        self.last_touched: list[GameRun] = []  # games that received lines in the last call

    # -- external transitions (driven by the tail) ----------------------------

    def disconnected(self, reason: str) -> list[LiveEvent]:
        self.game = None
        return self._flush(lambda: self._set(LiveStatus.DISCONNECTED, reason))

    def connected(self) -> list[LiveEvent]:
        if self.status is not LiveStatus.DISCONNECTED:
            return []
        return self._flush(lambda: self._set(LiveStatus.WAITING_FOR_GAME, None))

    def new_source(self, session_name: str | None = None) -> list[LiveEvent]:
        """A different Power.log (new client launch): forget the game, wait for the next."""
        self.game = None
        self._spectating = False
        self.session_name = session_name
        return self._flush(lambda: self._set(LiveStatus.WAITING_FOR_GAME, None))

    def file_discontinuity(self, has_game: bool) -> list[LiveEvent]:
        self.game = None
        self._spectating = False
        if has_game:
            return self._flush(lambda: self._set(LiveStatus.UNTRUSTED, Reason.FILE_DISCONTINUITY))
        return self._flush(lambda: self._set(LiveStatus.WAITING_FOR_GAME, None))

    # -- input ---------------------------------------------------------------

    def feed(
        self,
        lines: list[str],
        now_ms: int,
        offsets: tuple[int, int] | None = None,
        catchup: bool = False,
    ) -> list[LiveEvent]:
        """Process complete lines.

        ``catchup`` marks lines that already existed when the source was attached or rebuilt
        (startup, new session, file discontinuity). They are replayed internally: no historical
        snapshot or status transition is emitted. A finished game ends in WAITING_FOR_GAME and
        is forgotten; a running game ends in SYNCING, and only a decision that is current and
        settled after the catch-up is emitted, normally.
        """
        watched: dict[int, tuple[GameRun, int]] = {}
        if self.game is not None:
            watched[id(self.game)] = (self.game, len(self.game.lines))
        saved = (self.status, self.reason)

        def run() -> None:
            self._catchup = catchup
            try:
                for line in lines:
                    self._line(line, now_ms)
                    if self.game is not None and id(self.game) not in watched:
                        watched[id(self.game)] = (self.game, 0)
            finally:
                self._catchup = False
            if catchup:
                self._finish_catchup(saved, watched)
            self._poll(now_ms)

        events = self._flush(run)
        for game, start in watched.values():
            count = len(game.lines) - start
            if count > 0:
                row = {"t": now_ms, "n": count}
                if offsets is not None:
                    row["bytes"] = list(offsets)
                if catchup:
                    row["catchup"] = True
                game.trace.append(row)
        self.last_touched = [game for game, _ in watched.values()]
        return events

    def _finish_catchup(self, saved: tuple, watched: dict) -> None:
        final = (self.status, self.reason)
        self.status, self.reason = saved
        game = self.game
        if game is not None and game.ended:
            final = (LiveStatus.WAITING_FOR_GAME, None)
            watched.pop(id(game), None)  # a finished historical game is neither followed nor recorded
            self.game = None
        self._set(*final)

    def tick(self, now_ms: int, partial_line: bool = False) -> list[LiveEvent]:
        """Advance time. ``partial_line``: the tail still buffers a half-written line."""

        def run() -> None:
            if self.game is not None:
                self.game.gate.idle(now_ms, partial_line)
            self._poll(now_ms)

        events = self._flush(run)
        if events and self.game is not None:
            self.game.trace.append({"t": now_ms, "n": 0, "tick": True})
        self.last_touched = [self.game] if self.game is not None else []
        return events

    # -- internals -----------------------------------------------------------

    def _flush(self, action) -> list[LiveEvent]:
        self._events = []
        action()
        events, self._events = self._events, []
        return events

    def _set(self, status: LiveStatus, reason: str | None) -> None:
        if status is not LiveStatus.READY:
            self.current_snapshot = None
        if (status, reason) == (self.status, self.reason):
            return
        self.status, self.reason = status, reason
        if not (self._quiet or self._catchup):
            key = self.game.game_key if self.game else None
            self._events.append(StatusEvent(status, reason, key))

    def _invalidate_current(self) -> None:
        if self.current_snapshot is not None or self.status is LiveStatus.READY:
            self.current_snapshot = None
            self._set(LiveStatus.SYNCING, Reason.AWAITING_DECISION)

    def _line(self, line: str, now_ms: int) -> None:
        spectator = _SPECTATOR_RE.match(line)
        if spectator:
            text = spectator.group(1).strip()
            if text in _SPECTATOR_BEGIN:
                self._spectating = True
            elif text in _SPECTATOR_END:
                self._spectating = False
            return
        if CREATE_GAME_RE.match(line):
            self._begin_game(line)
            return
        game = self.game
        if game is None or game.unsupported_reason is not None:
            return
        game.lines.append(line)
        if COMPLETE_RE.match(line):
            game.ended = True
            game.gate.discard()
            if not game.failed:
                try:
                    game.reducer.read_line(line)
                except ReducerError:
                    pass  # the game is over either way; the entity table is no longer used
            if game.mode_state == _MODE_OK:
                self._set(LiveStatus.GAME_OVER, None)
            return
        if game.failed:
            return
        self._header(game, line)
        match = _LINE_RE.match(line)
        if match is None:
            game.gate.close_message()
            return
        owner, method, message = match.groups()
        message = message.strip()
        try:
            if owner == "GameState":
                self._game_state_line(game, method, message, line, now_ms)
            else:
                game.gate.close_message()
                if owner == "PowerTaskList" and method == "DebugDump":
                    dump = DUMP_RE.match(message)
                    if dump:
                        if int(dump.group(1)) > game.gate.q_created:
                            self._invalidate_current()
                        game.gate.queued(int(dump.group(1)))
                elif owner == "PowerProcessor" and method == "EndCurrentTaskList":
                    end = END_RE.match(message)
                    if end:
                        game.gate.ended(int(end.group(1)))
        except ReducerError as error:
            self._untrusted(game, error.reason)
            return
        if game.mode_state == _MODE_OK and not (self._quiet or self._catchup):
            self._try_emit(game)

    def _begin_game(self, line: str) -> None:
        self._invalidate_current()
        game = GameRun()
        self.game = game
        game.lines.append(line)
        if self._spectating:
            game.unsupported_reason = Reason.SPECTATOR
            self._set(LiveStatus.WAITING_FOR_GAME, Reason.SPECTATOR)
            return
        try:
            game.reducer.read_line(line)
        except ReducerError as error:
            self._untrusted(game, error.reason)

    def _header(self, game: GameRun, line: str) -> None:
        if game.header_done:
            return
        if PLAYER_HEADER_RE.search(line):
            game.header_done = True
            game.game_key = game_key_from_header(game.lines[: len(game.lines) - 1])
            return
        turn = TURN_RE.search(line)
        if turn and int(turn.group(1)) > 0:
            game.mid_game = True

    def _game_state_line(self, game: GameRun, method: str, message: str, line: str, now_ms: int) -> None:
        self._invalidate_current()
        if method == "DebugPrintOptions":
            if game.mode_state != _MODE_OK:
                return
            game.reducer.read_line(line)
            if message.startswith("id="):
                packet = game.reducer.last_options()
                if packet is not None:
                    game.gate.begin(packet, packet.id, now_ms, len(game.lines))
            else:
                game.gate.touch(now_ms)
            return

        game.gate.close_message()
        game.gate.supersede()
        if method == "DebugPrintGame":
            self._mode_line(game, line, message)
            if game.unsupported_reason is not None:
                return
        elif method == "SendChoices":
            chosen = _CHOSEN_RE.match(message)
            if chosen:
                game.self_choice_players.add(int(chosen.group(1)))
        elif method == "DebugPrintPower" and "BLOCK_START BlockType=GAME_RESET" in message:
            if game.mode_state == _MODE_OK:
                self._set(LiveStatus.SYNCING, Reason.GAME_RESET)
        game.reducer.read_line(line)

    def _mode_line(self, game: GameRun, line: str, message: str) -> None:
        build = _BUILD_RE.match(message)
        if build:
            game.build = int(build.group(1))
        meta = META_RE.match(line)
        if meta is None:
            return
        (game.game_types if meta.group(1) == "GameType" else game.formats).add(meta.group(2))
        if len(game.game_types) > 1 or len(game.formats) > 1:
            game.mode_state = _MODE_AMBIGUOUS
            game.unsupported_reason = Reason.MODE_AMBIGUOUS
            self._set(LiveStatus.WAITING_FOR_GAME, Reason.MODE_AMBIGUOUS)
        elif game.game_types and game.formats:
            if self.mode_policy.allows(game.game_type, game.format_type):
                game.mode_state = _MODE_OK
                reason = Reason.RECONNECT if game.mid_game else Reason.AWAITING_DECISION
                self._set(LiveStatus.SYNCING, reason)
            else:
                game.mode_state = _MODE_UNSUPPORTED
                game.unsupported_reason = Reason.UNSUPPORTED_MODE
                game.lines = game.lines[:1]  # nothing from an unsupported game is kept
                self._set(LiveStatus.WAITING_FOR_GAME, Reason.UNSUPPORTED_MODE)

    # -- decision points -----------------------------------------------------

    def _poll(self, now_ms: int) -> None:
        game = self.game
        if game is None or game.blocked or self._quiet:
            return
        if game.gate.timed_out(now_ms):
            dropped = game.gate.pending.options_id
            self._untrusted(game, Reason.SETTLE_TIMEOUT)
            self._resync(game, dropped)
            return
        self._try_emit(game)

    def _try_emit(self, game: GameRun) -> None:
        if game.blocked:
            return
        pending = game.gate.take_ready()
        if pending is None or not has_candidate_option(pending.packet):
            return
        try:
            game.reducer.commit()
            board = game.reducer.game
            if board is None or game.game_key is None:
                raise ReducerError(Reason.INVARIANT)
            self_id = self._resolve_self(game, board, option_controllers(board, pending.packet))
            state = project_state(board, self_id, self.catalog, parity_view=self.parity_view,
                                  options_packet=pending.packet)
            decision = build_decision(board, pending.packet, self_id)
            if state.active_player != "SELF":
                if has_named_option(pending.packet):
                    raise ReducerError(Reason.INVARIANT)  # validated options in the opponent's turn
                return  # END_TURN alone: the opponent's turn, no decision
        except ReducerError as error:
            self._untrusted(game, error.reason)
            return
        except Exception:  # privacy: only the stable reason is kept, never exception text
            self._untrusted(game, Reason.INVARIANT)
            return

        state_dict = state_to_dict(state)
        seq = self._seq.get(game.game_key, 0) + 1
        self._seq[game.game_key] = seq
        self._set(LiveStatus.READY, None)
        snapshot = Snapshot(
            seq=seq,
            status=LiveStatus.READY.value,
            reason=None,
            game_key=game.game_key,
            session=self.session_name,
            client_build=game.build,
            game_type=game.game_type,
            format=game.format_type,
            phase="SELF_DECISION",
            turn=state.turn_number,
            active_player=state.active_player,
            state=state_dict,
            decision=decision,
            state_hash=state_hash(state_dict),
            source={"line_in_game": pending.line_in_game},
        )
        self.current_snapshot = snapshot
        self._events.append(snapshot)

    @staticmethod
    def _resolve_self(game: GameRun, board, controllers: set[int]) -> int:
        """SELF = the client side. Two independent rules must not disagree:

        A. the owner of the entities the client itself sent in ``SendChoices`` (mulligan);
        B. the side whose hand shows card identities.
        The answer is remembered for the game; later decisions must stay consistent with
        it, which covers an empty hand. Only when neither rule has ever applied, the
        controller of the server-validated options is used. Every validated option must
        belong to the resolved side.
        """
        chosen = game.self_choice_players
        if len(chosen) > 1:
            raise ReducerError(Reason.SELF_AMBIGUOUS)
        by_choice = next(iter(chosen)) if chosen else None
        try:
            by_hand = infer_local_player_id(board)
        except ValueError:
            by_hand = None
        signals = {value for value in (by_choice, by_hand) if value is not None}
        if len(signals) > 1:
            raise ReducerError(Reason.SELF_AMBIGUOUS)
        remembered = game.self_player_id
        if signals:
            resolved = next(iter(signals))
            if remembered is not None and remembered != resolved:
                raise ReducerError(Reason.SELF_AMBIGUOUS)
        elif remembered is not None:
            resolved = remembered
        elif len(controllers) == 1:
            resolved = next(iter(controllers))
        else:
            raise ReducerError(Reason.SELF_AMBIGUOUS)
        if controllers - {resolved}:
            raise ReducerError(Reason.SELF_AMBIGUOUS)
        game.self_player_id = resolved
        return resolved

    def _untrusted(self, game: GameRun, reason: str) -> None:
        game.failed = True
        game.gate.discard()
        self._set(LiveStatus.UNTRUSTED, reason)

    def _resync(self, old: GameRun, dropped_option_id: int | None) -> None:
        """Rebuild the game silently from its retained lines.

        Succeeds only if the lines parse and apply cleanly; otherwise the game stays
        UNTRUSTED until the next CREATE_GAME. The options message that timed out is
        never offered again.
        """
        saved = (self.status, self.reason)
        previous_game, self.game = self.game, None
        self._quiet = True
        try:
            for line in old.lines:
                self._line(line, 0)
            fresh = self.game
            if fresh is None or fresh.failed or fresh.mode_state != _MODE_OK:
                raise ReducerError(Reason.PARSE_ERROR)
            if dropped_option_id is not None:
                fresh.gate.emitted_ids.add(dropped_option_id)
            fresh.gate.discard()
            fresh.reducer.commit()
            fresh.trace = old.trace
        except Exception:
            self.game = previous_game
            return
        finally:
            self._quiet = False
            self.status, self.reason = saved
        self._set(LiveStatus.SYNCING, Reason.AWAITING_DECISION)
