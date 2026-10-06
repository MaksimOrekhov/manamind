"""Pre-order walk of one parsed game into causal windows.

A *window* is one root block. Inside it every nested ``Block`` is a *unit*; a ``SubSpell`` group
is transparent: its packets belong to the enclosing block. Each packet is applied to a real
entity table exactly once, in pre-order, so the "before" values read here are the values the
client had at that point. Events carry entity views captured at the moment they happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hearthstone.enums import GameTag
from hslog.packets import (
    Block, ChangeEntity, Choices, ChosenEntities, FullEntity, HideEntity, MetaData, Options,
    ShowEntity, SubSpell, TagChange,
)

from manamind.live.reducer import PacketExporter, quiet_parser
from manamind.live.snapshot import state_hash, state_to_dict
from manamind.integrations.powerlog.visible_state import to_visible_state

from .entities import PUBLIC_ZONES, EntityView, to_id, view_of
from .sanitize import safe_code, tag_is_known, tag_label, to_int

STAT_TAGS = frozenset({"ATK", "HEALTH", "COST", "DURABILITY", "ARMOR", "DAMAGE"})
KEYWORD_TAGS = frozenset({
    "TAUNT", "DIVINE_SHIELD", "STEALTH", "POISONOUS", "LIFESTEAL", "WINDFURY", "CHARGE", "RUSH",
    "REBORN", "FROZEN", "SILENCED", "IMMUNE", "CANT_BE_TARGETED_BY_SPELLS", "DORMANT",
    "ELUSIVE", "MEGA_WINDFURY", "AURA", "DEATHRATTLE", "TRIGGER_VISUAL",
})
ROOT_ATTRIBUTION_GUARD = frozenset({"PLAY", "ATTACK"})


@dataclass
class Unit:
    unit_id: str
    block_type: str
    owner: int | None
    parent: str | None
    depth: int
    keyword: str | int | None
    target: int | None
    ordinal: int
    override_history: bool = False


@dataclass
class Event:
    ordinal: int
    unit: str | None
    kind: str  # TAG META CREATE REVEAL HIDE CHANGE CHOICES CHOSEN
    entity: int | None
    tag: str | None = None
    old: object = None
    new: object = None
    card_id: str | None = None
    old_card_id: str | None = None
    meta: str | None = None
    amount: int | None = None
    targets: tuple[int, ...] = ()
    view: EntityView | None = None
    hidden_reveal: bool = False
    unknown_tag: bool = False
    semantic: bool = False
    target_views: dict[int, EntityView] = field(default_factory=dict)


@dataclass
class OptionEntry:
    main: int
    accepted: bool
    targets: list[tuple[int, EntityView | None, str | None, int | None]]


@dataclass
class OptionsSnapshot:
    options_id: int
    entries: list[OptionEntry]


@dataclass
class Window:
    ordinal: int
    root_type: str
    root_entity: int | None
    root_ordinal: int
    turn: int
    step: str | None
    units: list[Unit] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    gap_events: list[Event] = field(default_factory=list)
    final: dict[int, EntityView] = field(default_factory=dict)
    created: set[int] = field(default_factory=set)
    before_state: dict | None = None
    after_state: dict | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    options: OptionsSnapshot | None = None
    unknown_tag_ids: set[str] = field(default_factory=set)
    subspell_packets: int = 0


@dataclass
class GameWalk:
    windows: list[Window]
    stats: dict[str, int]


def _block_type_name(block) -> str:
    name = getattr(block.type, "name", None)
    return name if isinstance(name, str) else "OTHER"


def _meta_name(meta) -> str | None:
    value = safe_code(meta)
    return value if isinstance(value, str) else None


def is_semantic(event: Event, owner: int | None) -> bool:
    if event.kind in ("CREATE", "CHANGE", "CHOICES", "CHOSEN"):
        return True
    if event.kind == "META":
        return event.meta in ("DAMAGE", "HEALING")
    if event.kind == "TAG":
        if event.unknown_tag or event.tag is None:
            return False
        if event.tag in STAT_TAGS or event.tag in KEYWORD_TAGS or event.tag == "CONTROLLER":
            return True
        if event.tag == "ZONE":
            return event.entity != owner
    return False


class Walker:
    def __init__(self, tree, self_id: int, catalog) -> None:
        self.tree = tree
        self.self_id = self_id
        self.catalog = catalog
        self.exporter = PacketExporter(tree)
        self.ordinal = 0
        self.stats: dict[str, int] = {
            "root_blocks": 0, "subspell_packets": 0, "enchantment_creations": 0,
            "enchantment_creations_with_creator_and_attached": 0, "unknown_tag_changes": 0,
            "late_enriched_creations": 0,
        }
        self.public_ids: set[int] = set()
        self.last_options: OptionsSnapshot | None = None

    @property
    def game(self):
        return self.exporter.game

    # -- state snapshots --------------------------------------------------------------------

    def _state(self) -> tuple[dict | None, str | None]:
        try:
            state = to_visible_state(
                self.game, self.self_id, self.catalog,
                opponent_identity_policy="none", hand_order="zone_position",
            )
        except Exception:  # noqa: BLE001 - a missing player/turn is just "no state yet"
            state = None
        if state is None:
            return None, None
        data = state_to_dict(state)
        return data, state_hash(data)

    # -- packet application -----------------------------------------------------------------

    def _apply(self, packet) -> None:
        with quiet_parser():
            self.exporter.export_packet(packet)

    def _event_from(self, packet, unit: Unit | None, window: Window | None) -> list[Event]:
        """Capture pre-state, apply the packet, return its events."""
        game = self.game
        events: list[Event] = []
        unit_id = unit.unit_id if unit is not None else None
        owner = unit.owner if unit is not None else None
        if isinstance(packet, TagChange):
            handle = to_id(packet.entity)
            tag = to_int(packet.tag)
            pre = view_of(game, handle)
            old = None
            if handle is not None:
                entity = game.find_entity_by_id(handle)
                old = to_int(entity.tags.get(tag)) if entity is not None else None
            self._apply(packet)
            new = to_int(packet.value)
            post = view_of(game, handle)
            known = tag is not None and tag_is_known(tag)
            label = tag_label(tag) if tag is not None else None
            if tag is not None and not known:
                self.stats["unknown_tag_changes"] += 1
                if window is not None:
                    window.unknown_tag_ids.add(str(tag))
            if label in ("ZONE",):
                old, new = _zone_name(old), _zone_name(new)
            event = Event(
                self._tick(), unit_id, "TAG", handle, tag=label, old=old, new=new, view=post,
                unknown_tag=not known,
            )
            event.semantic = is_semantic(event, owner)
            events.append(event)
        elif isinstance(packet, FullEntity):
            handle = to_id(packet.entity)
            self._apply(packet)
            view = view_of(game, handle)
            events.append(Event(self._tick(), unit_id, "CREATE", handle, card_id=packet.card_id or "",
                                view=view, semantic=True))
            if window is not None and handle is not None:
                window.created.add(handle)
        elif isinstance(packet, ShowEntity):
            handle = to_id(packet.entity)
            pre = view_of(game, handle)
            self._apply(packet)
            events.append(Event(
                self._tick(), unit_id, "REVEAL", handle, card_id=packet.card_id or "",
                old_card_id=pre.card_id if pre is not None else "", view=view_of(game, handle),
                hidden_reveal=bool(unit is not None and unit.override_history),
            ))
        elif isinstance(packet, HideEntity):
            handle = to_id(packet.entity)
            self._apply(packet)
            events.append(Event(self._tick(), unit_id, "HIDE", handle, view=view_of(game, handle)))
        elif isinstance(packet, ChangeEntity):
            handle = to_id(packet.entity)
            pre = view_of(game, handle)
            self._apply(packet)
            events.append(Event(
                self._tick(), unit_id, "CHANGE", handle, card_id=packet.card_id or "",
                old_card_id=pre.card_id if pre is not None else "", view=view_of(game, handle), semantic=True,
            ))
        elif isinstance(packet, MetaData):
            self._apply(packet)
            name = _meta_name(packet.meta)
            targets = tuple(h for h in (to_id(ref) for ref in packet.info) if h is not None)
            if name == "OVERRIDE_HISTORY" and unit is not None:
                unit.override_history = True
            events.append(Event(
                self._tick(), unit_id, "META", None, meta=name, amount=to_int(packet.data), targets=targets,
                semantic=name in ("DAMAGE", "HEALING"),
            ))
            for target in targets:
                target_view = view_of(game, target)
                if target_view is not None:
                    events[-1].target_views[target] = target_view
        elif isinstance(packet, (Choices, ChosenEntities)):
            self._apply(packet)
            kind = "CHOICES" if isinstance(packet, Choices) else "CHOSEN"
            targets = tuple(h for h in (to_id(ref) for ref in packet.choices) if h is not None)
            events.append(Event(self._tick(), unit_id, kind, None, targets=targets, semantic=True,
                                target_views={h: v for h in targets if (v := view_of(game, h)) is not None}))
        elif isinstance(packet, Options):
            self._apply(packet)
            self.last_options = self._options_snapshot(packet)
        else:
            self._apply(packet)
        return events

    def _tick(self) -> int:
        self.ordinal += 1
        return self.ordinal - 1

    def _options_snapshot(self, packet: Options) -> OptionsSnapshot:
        entries: list[OptionEntry] = []
        for option in packet.options:
            main = to_id(option.entity) if option.entity is not None else None
            if main is None:
                continue
            targets: list[tuple[int, EntityView | None, str | None, int | None]] = []
            for item in option.options:
                handle = to_id(item.entity) if item.entity is not None else None
                if handle is None:
                    continue
                code = None if item.error is None else safe_code(item.error)
                targets.append((handle, view_of(self.game, handle), code if isinstance(code, str) else None, None))
                if item.optype == "subOption":
                    for sub in item.options:
                        sub_handle = to_id(sub.entity) if sub.entity is not None else None
                        if sub_handle is not None:
                            sub_code = None if sub.error is None else safe_code(sub.error)
                            targets.append((sub_handle, view_of(self.game, sub_handle),
                                            sub_code if isinstance(sub_code, str) else None, handle))
            entries.append(OptionEntry(main, option.error is None, targets))
        return OptionsSnapshot(to_int(packet.id) or 0, entries)

    # -- block walk ---------------------------------------------------------------------------

    def _walk_packets(self, packets, unit: Unit, window: Window) -> None:
        for packet in packets:
            if isinstance(packet, Block):
                self._walk_block(packet, unit, window)
            elif isinstance(packet, SubSpell):
                self._apply(packet)
                self._tick()
                window.subspell_packets += len(packet.packets)
                self.stats["subspell_packets"] += len(packet.packets)
                self._walk_packets(packet.packets, unit, window)
            else:
                for event in self._event_from(packet, unit, window):
                    window.events.append(event)

    def _walk_block(self, block: Block, parent: Unit | None, window: Window) -> Unit:
        keyword = block.trigger_keyword
        unit = Unit(
            unit_id=f"u{len(window.units)}",
            block_type=_block_type_name(block),
            owner=to_id(block.entity),
            parent=parent.unit_id if parent is not None else None,
            depth=(parent.depth + 1) if parent is not None else 0,
            keyword=None if keyword is None else safe_code(keyword),
            target=to_id(block.target) or None,
            ordinal=self._tick(),
        )
        window.units.append(unit)
        self._apply(block)
        self._walk_packets(block.packets, unit, window)
        return unit

    def _finish_window(self, window: Window) -> None:
        touched: set[int] = set()
        for event in window.events:
            if event.entity is not None:
                touched.add(event.entity)
            touched.update(event.targets)
        for unit in window.units:
            if unit.owner is not None:
                touched.add(unit.owner)
            if unit.target is not None:
                touched.add(unit.target)
        for event in list(window.events):
            if event.view is not None:
                for ref in (event.view.creator, event.view.attached, event.view.last_affected_by):
                    if ref:
                        touched.add(ref)
        # follow creator chains so enchantment-of-enchantment attribution can resolve
        frontier = set(touched)
        for _ in range(4):
            nxt: set[int] = set()
            for handle in frontier:
                view = view_of(self.game, handle)
                if view is not None and view.creator and view.creator not in touched:
                    nxt.add(view.creator)
            touched |= nxt
            frontier = nxt
        for handle in touched:
            view = view_of(self.game, handle)
            if view is not None:
                window.final[handle] = view
                if view.zone in PUBLIC_ZONES:
                    self.public_ids.add(handle)

    def _enrich_late_creations(self, windows: list[Window]) -> None:
        """Complete creations whose identity/type/CREATOR/ATTACHED arrive after their window.

        The client often logs ``FULL_ENTITY`` with an empty card id inside a block and sends the
        ``SHOW_ENTITY`` that carries ``CARDTYPE``/``CREATOR``/``ATTACHED`` in a later root block. A
        window-end snapshot alone would type such an entity as unknown (measured: 148 enchantment
        creations in the audit corpus). The enriched fields come from the end-of-game entity; zone and
        controller stay as seen at window end so visibility is decided by what was public *then*.
        """
        for window in windows:
            for event in window.events:
                if event.kind != "CREATE" or event.entity is None:
                    continue
                current = window.final.get(event.entity)
                if current is not None and current.card_type and current.card_id:
                    continue
                late = view_of(self.game, event.entity)
                if late is None or not (late.card_type or late.card_id):
                    continue
                window.final[event.entity] = replace(
                    late, zone=current.zone if current else late.zone,
                    controller=current.controller if current and current.controller is not None else late.controller,
                )
                self.stats["late_enriched_creations"] += 1
                for ref in (late.creator, late.attached):
                    if ref and ref not in window.final:
                        extra = view_of(self.game, ref)
                        if extra is not None:
                            window.final[ref] = extra
        for window in windows:
            for event in window.events:
                final = window.final.get(event.entity) if event.kind == "CREATE" else None
                if final is not None and final.card_type == "ENCHANTMENT":
                    self.stats["enchantment_creations"] += 1
                    if final.creator and final.attached:
                        self.stats["enchantment_creations_with_creator_and_attached"] += 1

    def walk(self) -> GameWalk:
        windows: list[Window] = []
        for packet in self.tree.packets:
            if isinstance(packet, Block):
                self.stats["root_blocks"] += 1
                step = self.game.tags.get(GameTag.STEP)
                turn = to_int(self.game.tags.get(GameTag.TURN)) or 0
                root_entity = to_id(packet.entity)
                window = Window(
                    ordinal=len(windows), root_type=_block_type_name(packet), root_entity=root_entity,
                    root_ordinal=self.ordinal, turn=turn,
                    step=(safe_code(step) if step is not None else None),
                )
                if window.root_type == "PLAY" and root_entity is not None:
                    self.public_ids.add(root_entity)  # starting a play reveals the card
                window.before_state, window.before_hash = self._state()
                window.options = self.last_options
                self._walk_block(packet, None, window)
                self._finish_window(window)
                window.after_state, window.after_hash = self._state()
                windows.append(window)
            else:
                for event in self._event_from(packet, None, None):
                    if windows and event.kind == "TAG" and event.semantic:
                        windows[-1].gap_events.append(event)
        self._enrich_late_creations(windows)
        return GameWalk(windows, dict(self.stats))


def _zone_name(value) -> str | None:
    if value is None:
        return None
    from hearthstone.enums import Zone

    try:
        return Zone(int(value)).name
    except ValueError:
        return str(int(value))
