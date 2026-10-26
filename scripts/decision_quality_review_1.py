"""DECISION-QUALITY-REVIEW-1: blind expert review of real decisions from new matches.

Phases, each write-once (existing outputs are never overwritten):

  --inventory  find raw match logs absent from every earlier split, checkpoint and evaluation
               (by ID, before opening a file), import them with the canonical importer and count
               eligible decisions. fresh_holdout is excluded by ID only and never opened.
  --lock       deterministic pilot, main and repeat samples chosen from state/menu features only,
               plus the blind payload the labeling tool shows.
  --serve      local labeling tool on 127.0.0.1; labels are appended to a private file.
  --freeze     hash one rater's finished labels of a batch; for the pilot also evaluates the
               pre-registered pilot criteria that unlock the main batch.

Nothing here runs a Policy, Strategic Scorer or Outcome forecast, and no file written before
labels are frozen contains the player's chosen action or the game result. The later model
comparison re-imports the pinned raw logs (SHA-256 in the lock) to obtain them.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import statistics
import sys
import threading
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

PRIVATE = ROOT / "data/processed_decision_quality_review_1"
REPORT = ROOT / "reports/decision_quality_review_1"
TOOL_HTML = ROOT / "scripts/decision_quality_review_1_tool.html"
SPLIT_PLAN = ROOT / "data/processed_policy_prepare_1/split_plan.json"
EVAL_1 = ROOT / "data/processed_new_matches_eval_1/protocol.private.json"
EVAL_2 = ROOT / "data/processed_new_matches_eval_2/protocol.private.json"
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
COLLECTED = ROOT / "data/raw/collected"

SEED = "decision-quality-review-1/20261026"
PILOT_UNIQUE = 15
PILOT_REPEATS = 3
MAIN_UNIQUE = 80
MAIN_REPEATS = 20
MAIN_PER_MATCH_CAP = 8
MIN_MENU = 3
MAIN_MIN_MATCHES = 12
MAIN_MIN_OPPONENT_CLASSES = 5

# Fields that must never reach the labeling payload (checked recursively).
FORBIDDEN_KEYS = frozenset({"chosen_action_index", "final_result", "decision_id", "game_id", "provenance",
                            "options_line", "selection_line", "state_hash", "position_id", "repeat_of"})
DISPLAY_REASONS = ("DISPLAY_PROBLEM", "CARD_TEXT_MISSING")
INSUFFICIENT_REASONS = ("DISPLAY_PROBLEM", "CARD_TEXT_MISSING", "HIDDEN_INFORMATION_NEEDED",
                        "RULES_UNCLEAR", "OTHER")
ACTION_MARKS = ("ACCEPTABLE", "BLUNDER", "UNSURE")
CONFIDENCE = ("LOW", "MEDIUM", "HIGH")

PILOT_CRITERIA = {
    "P1_complete": "every pilot screen has a saved label",
    "P2_display": "DISPLAY_PROBLEM flagged on at most 2 of 18 screens",
    "P3_display_insufficient": "INSUFFICIENT_INFORMATION for a display or missing-text reason on at most 3 of 15 unique positions",
    "P4_workload": "median active time per screen at most 180 seconds",
    "P5_blind_payload": "automated audit: no forbidden field in the served payload",
}


# ----- small helpers -----------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_once(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def rank(*parts: Any) -> str:
    return sha256_bytes(canonical([SEED, *parts]).encode("utf-8"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


# ----- inventory ---------------------------------------------------------------------------------

def exclusion_reason(stem: str, heldout: set[str], used: set[str], examined_files: set[str], name: str) -> str | None:
    """Decided from the file name and earlier manifests only, before the file is opened."""
    if len(stem) != 16 or any(c not in "0123456789abcdef" for c in stem):
        return "LEGACY_FILENAME_WITHOUT_MATCH_KEY"
    if any(g.startswith(stem) for g in heldout):
        return "PROTECTED_FRESH_HOLDOUT_ID_ONLY"
    if any(g.startswith(stem) for g in used):
        return "MATCH_ID_USED_BEFORE"
    if name in examined_files:
        return "SOURCE_IN_EVAL_2_INVENTORY"
    return None


def used_match_ids(heldout: set[str]) -> tuple[set[str], dict]:
    """Every match ID any split, checkpoint, usage registry or earlier evaluation has touched."""
    import new_matches_eval_1 as base
    history, models = base._load_history(heldout)  # checkpoint identity/split metadata only, no forward pass
    used = set(history)
    eval_1, eval_2 = read_json(EVAL_1), read_json(EVAL_2)
    used.update(eval_1["eligible_match_ids"])
    used.update(eval_2["eligible_match_ids"], eval_2["history_ids"], eval_2["prior_match_ids"])
    used.update(r["game_id"] for r in eval_2["source_inventory"] if r.get("game_id"))
    return used - heldout, {"checkpoints": sorted(models), "eval_1_sha256": sha256_file(EVAL_1),
                            "eval_2_sha256": sha256_file(EVAL_2), "split_plan_sha256": sha256_file(SPLIT_PLAN)}


def eligible(example: dict) -> str | None:
    state = example["state"]
    if state.get("active_player") != "SELF":
        return "NOT_SELF_TURN"
    if state.get("pending_choice_owner") is not None:
        return "CHOICE_PENDING"
    if len(example["legal_actions"]) < MIN_MENU:
        return "MENU_TOO_SMALL"
    return None


def blind_position(example: dict) -> dict:
    """The only fields kept before labels are frozen: visible state, full legal menu, private join keys."""
    return {"decision_id": example["decision_id"], "game_id": example["game_id"],
            "state_hash": example["provenance"]["state_hash"],
            "state": example["state"], "legal_actions": example["legal_actions"]}


def run_inventory() -> None:
    out = PRIVATE / "inventory.private.json"
    pool_path = PRIVATE / "pool.private.jsonl"
    if out.exists() or pool_path.exists():
        raise SystemExit(f"refusing to overwrite {out.relative_to(ROOT)}")
    import new_matches_eval_1 as base
    from manamind.cards.catalog import CardCatalog
    from manamind.integrations.powerlog.policy_import import PolicyImportError

    plan = read_json(SPLIT_PLAN)
    heldout = set(plan["parts"]["fresh_holdout"])
    if len(heldout) != 9:
        raise ValueError("expected nine protected fresh_holdout IDs")
    used, identity = used_match_ids(heldout)
    examined = {Path(r["source"]).name for r in read_json(EVAL_2)["source_inventory"]}
    catalog = CardCatalog.from_json(CATALOG)
    sources, matches, pool = [], [], []
    for path in sorted(COLLECTED.glob("*.log")):
        reason = exclusion_reason(path.stem, heldout, used, examined, path.name)
        if reason:
            sources.append({"source": path.name, "category": "EXCLUDED", "reason": reason})
            continue
        digest = sha256_file(path)
        try:
            examples, summary = base._load_match_rows(path, catalog)
        except (PolicyImportError, ValueError, OSError) as error:
            code = error.reason if isinstance(error, PolicyImportError) else type(error).__name__
            sources.append({"source": path.name, "category": "IMPORT_FAILED", "reason": code, "raw_sha256": digest})
            continue
        game = summary["game_id"]
        if game in heldout or game in used or not game.startswith(path.stem):
            raise ValueError("imported match overlaps a protected or used ID")
        reasons = Counter()
        kept = 0
        for example in examples:
            why = eligible(example)
            if why:
                reasons[why] += 1
                continue
            pool.append(blind_position(example))
            kept += 1
        classes = {e["state"]["self_player"].get("player_class") or "UNKNOWN" for e in examples}
        opponents = {e["state"]["opponent"].get("player_class") or "UNKNOWN" for e in examples}
        matches.append({"game_id": game, "source": path.name, "raw_sha256": digest,
                        "self_class": classes.pop() if len(classes) == 1 else "UNKNOWN",
                        "opponent_class": opponents.pop() if len(opponents) == 1 else "UNKNOWN",
                        "decisions_total": summary["decisions_total"], "decisions_labeled": len(examples),
                        "importer_skips": dict(summary["skip_reasons"]), "eligible_decisions": kept,
                        "ineligible": dict(reasons)})
        sources.append({"source": path.name, "category": "IMPORTED", "game_id": game, "raw_sha256": digest})
    if len({m["game_id"] for m in matches}) != len(matches):
        raise ValueError("duplicate match IDs among new sources")
    pool.sort(key=lambda p: p["decision_id"])
    pool_text = "".join(canonical(p) + "\n" for p in pool)
    inventory = {
        "schema": "manamind.decision_quality_review_1/inventory/1", "created_at_utc": now(),
        "source_commit": git_head(), "code_sha256": sha256_file(Path(__file__)),
        "identity_inputs": identity, "protected_fresh_holdout": {"count": len(heldout), "opened": False},
        "used_match_ids_excluded": len(used), "sources": sources, "matches": matches,
        "pool_decisions": len(pool), "pool_sha256": sha256_bytes(pool_text.encode("utf-8")),
        "contains_chosen_action_or_result": False,
    }
    write_once(pool_path, pool_text)
    write_once(out, json.dumps(inventory, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(inventory_summary(inventory), ensure_ascii=False, indent=1))


def inventory_summary(inventory: dict) -> dict:
    by_class = defaultdict(lambda: {"matches": 0, "eligible_decisions": 0})
    for m in inventory["matches"]:
        by_class[m["self_class"]]["matches"] += 1
        by_class[m["self_class"]]["eligible_decisions"] += m["eligible_decisions"]
    return {"sources": dict(Counter(f"{s['category']}:{s.get('reason') or ''}" for s in inventory["sources"])),
            "imported_matches": len(inventory["matches"]), "pool_decisions": inventory["pool_decisions"],
            "self_classes": dict(sorted(by_class.items())),
            "opponent_classes": dict(Counter(m["opponent_class"] for m in inventory["matches"]))}


# ----- sampling ----------------------------------------------------------------------------------

def menu_bucket(position: dict) -> str:
    size = len(position["legal_actions"])
    return "3-5" if size <= 5 else "6-10" if size <= 10 else "11+"


def turn_of(position: dict) -> int:
    return int(position["state"].get("turn_number") or 0)


def select_samples(pool: list[dict], classes: dict[str, str]) -> dict:
    """Deterministic, outcome-blind selection: hash order, per-(match, turn) uniqueness, caps and strata."""
    by_rank = sorted(pool, key=lambda p: rank("order", p["decision_id"]))
    # Pilot: one position per match, round-robin over SELF classes for diversity.
    per_class = defaultdict(list)
    seen_games = set()
    for p in by_rank:
        if p["game_id"] not in seen_games:
            seen_games.add(p["game_id"])
            per_class[classes[p["game_id"]]].append(p)
    pilot = []
    order = sorted(per_class, key=lambda c: rank("class", c))
    while len(pilot) < PILOT_UNIQUE and any(per_class.values()):
        for c in order:
            if per_class[c] and len(pilot) < PILOT_UNIQUE:
                pilot.append(per_class[c].pop(0))
    blocked = {(p["game_id"], turn_of(p)) for p in pilot}
    # Main: strata by menu size, round-robin, cap per match, one position per (match, turn).
    strata = defaultdict(list)
    for p in by_rank:
        if (p["game_id"], turn_of(p)) not in blocked:
            strata[menu_bucket(p)].append(p)
    main, per_match, used_turns = [], Counter(), set()
    buckets = ["3-5", "6-10", "11+"]
    while len(main) < MAIN_UNIQUE and any(strata[b] for b in buckets):
        for b in buckets:
            while strata[b]:
                p = strata[b].pop(0)
                key = (p["game_id"], turn_of(p))
                if per_match[p["game_id"]] >= MAIN_PER_MATCH_CAP or key in used_turns:
                    continue
                main.append(p)
                per_match[p["game_id"]] += 1
                used_turns.add(key)
                break
            if len(main) >= MAIN_UNIQUE:
                break
    pilot_repeats = sorted(pilot, key=lambda p: rank("pilot-repeat", p["decision_id"]))[:PILOT_REPEATS]
    main_repeats = sorted(main, key=lambda p: rank("main-repeat", p["decision_id"]))[:MAIN_REPEATS]
    return {"pilot": pilot, "pilot_repeats": pilot_repeats, "main": main, "main_repeats": main_repeats}


def screens_for(batch: str, unique: list[dict], repeats: list[dict]) -> list[dict]:
    """Unique positions in shuffled order, then repeats shuffled again; every menu in canonical order."""
    first = sorted(unique, key=lambda p: rank(batch, "screen", p["decision_id"]))
    second = sorted(repeats, key=lambda p: rank(batch, "repeat-screen", p["decision_id"]))
    screens = []
    for n, (p, is_repeat) in enumerate([(p, False) for p in first] + [(p, True) for p in second], start=1):
        menu_order = canonical_menu(p)
        screens.append({"screen_id": f"{batch[0].upper()}{n:03d}", "position_id": position_id(p),
                        "repeat": is_repeat, "menu_order": menu_order})
    return screens


FAMILY_ORDER = {"PLAY_CARD": 0, "PREPARE_CARD": 1, "HERO_POWER": 2, "ACTIVATE_LOCATION": 3, "ATTACK": 4, "END_TURN": 9}


def canonical_menu(position: dict) -> list[int]:
    """Readable fixed order independent of the log, the player's choice and every model:
    family, then hand slot or attacker, then target (enemy hero first), then board slot."""
    def key(i: int) -> tuple:
        a = position["legal_actions"][i]
        source = a.get("hand_index") if a.get("type") in ("PLAY_CARD", "PREPARE_CARD") else (
            -1 if a.get("source_is_hero") else a.get("source_board_position"))
        target = (a.get("target_side") != "OPPONENT", a.get("target_kind") != "HERO",
                  a.get("target_board_position") or 0) if a.get("target_kind") else (False, False, -1)
        return (FAMILY_ORDER.get(a.get("type"), 5), source if isinstance(source, int) else 99, target,
                a.get("play_position") or 0, i)
    return sorted(range(len(position["legal_actions"])), key=key)


def position_id(position: dict) -> str:
    return "pos_" + rank("position", position["decision_id"])[:16]


# ----- blind rendering ---------------------------------------------------------------------------

class CardTexts:
    """Names and rules text from the read-only metadata layer, pinned catalog as fallback; missing stays missing."""

    def __init__(self) -> None:
        from manamind.card_metadata import CardMetadata, Status
        self.meta, self.status = CardMetadata.load(), Status
        self.missing: Counter = Counter()

    def card(self, card_id: str | None) -> dict:
        if not card_id:
            return {"name": "Неизвестная карта", "text": None, "known": False}
        found = self.meta.lookup(card_id)
        if found.status == self.status.FOUND:
            d = self.meta.describe(card_id)
            text = rich_text(d.text) if d.text else ""
            if text and not re.sub(r"\[\?\]|[\s.]", "", text):
                text = None  # the whole text is client-generated: show it as unavailable
            return {"name": d.name or card_id, "text": text, "known": True, "card_type": d.card_type,
                    "base_cost": d.cost, "base_attack": d.attack, "base_health": d.health or d.durability}
        self.missing[card_id] += 1
        return {"name": card_id, "text": None, "known": False}


_TAG = re.compile(r"</?(b|i)>")


def rich_text(text: str) -> str:
    """Escape, then re-allow only <b>/<i>; drop layout markers and $/# damage/heal marks."""
    from manamind.card_metadata.snapshot import strip_text_artifacts
    raw = strip_text_artifacts(text).replace(" ", " ").replace("\n", " ")
    if raw.startswith("[x]"):
        raw = raw[3:]
    raw = re.sub(r"[$#][a-z]?(\d)", r"\1", raw)  # $3, #5 and hero-power forms like $d2 / $a1
    raw = re.sub(r"\{\d+\}", "[?]", raw)  # values the client fills in during play (e.g. Herald) are not in the snapshot
    safe = html.escape(raw, quote=False)
    safe = re.sub(r"&lt;(/?)(b|i)&gt;", r"<\1\2>", safe)
    return re.sub(r"&lt;/?[a-z]+&gt;", "", safe)


KEYWORDS = (("taunt", "Taunt"), ("divine_shield", "Divine Shield"), ("poisonous", "Poisonous"),
            ("lifesteal", "Lifesteal"), ("windfury", "Windfury"), ("reborn", "Reborn"), ("stealth", "Stealth"),
            ("rush", "Rush"), ("charge", "Charge"), ("frozen", "Frozen"), ("immune", "Immune"),
            ("dormant", "Dormant"), ("silenced", "Silenced"))


def render_card(texts: CardTexts, card: dict | None) -> dict | None:
    if not card:
        return None
    info = texts.card(card.get("card_id"))
    return {"name": info["name"], "text": info["text"], "known_text": info["text"] is not None,
            "type": card.get("card_type") or info.get("card_type"),
            "cost": card.get("current_cost") if card.get("current_cost") is not None else card.get("cost"),
            "attack": card.get("current_attack") if card.get("current_attack") is not None else card.get("attack"),
            "health": card.get("current_health") if card.get("current_health") is not None else card.get("health"),
            "durability": card.get("current_durability") if card.get("current_durability") is not None
            else card.get("durability"),
            "race": card.get("race"), "mechanics": list(card.get("mechanics") or [])}


def render_entity(texts: CardTexts, entity: dict) -> dict:
    out = render_card(texts, entity.get("card")) or {}
    out.update(position=entity.get("board_position"), attack=entity.get("current_attack"),
               health=entity.get("current_health"), max_health=entity.get("max_health"),
               can_attack=entity.get("can_attack"),
               keywords=[label for key, label in KEYWORDS if entity.get(key)])
    for key in ("can_activate", "on_cooldown"):
        if key in entity:
            out[key] = entity[key]
    return out


def render_player(texts: CardTexts, player: dict) -> dict:
    return {
        "class": player.get("player_class"),
        "hero_health": player.get("hero_health"), "hero_max_health": player.get("hero_max_health"),
        "armor": player.get("armor"), "hero_attack": player.get("hero_attack"),
        "hero_frozen": player.get("hero_frozen"), "hero_divine_shield": player.get("hero_divine_shield"),
        "available_mana": player.get("available_mana"), "max_mana": player.get("max_mana"),
        "overloaded_mana": player.get("overloaded_mana"), "pending_overload": player.get("pending_overload"),
        "spell_damage": player.get("spell_damage"), "healing_bonus": player.get("healing_bonus"),
        "deck_size": player.get("deck_size"), "hand_size": player.get("hand_size"), "fatigue": player.get("fatigue"),
        "secret_count": player.get("secret_count"),
        "known_secrets": [render_card(texts, c) for c in player.get("known_secrets") or []],
        "hero_power": render_card(texts, player.get("hero_power")), "hero_power_ready": player.get("hero_power_ready"),
        "weapon": render_card(texts, player.get("weapon")),
        "board": [render_entity(texts, e) for e in player.get("board") or []],
        "locations": [render_entity(texts, e) for e in player.get("locations") or []],
        "active_effects": [render_card(texts, c) if isinstance(c, dict) and "card_id" in c else
                           {"name": str(c), "text": None} for c in player.get("active_effects") or []],
    }


def side_label(side: str | None) -> str:
    return {"SELF": "свой", "OPPONENT": "вражеский"}.get(side or "", "?")


def target_name(state: dict, texts: CardTexts, action: dict) -> str:
    kind, side = action.get("target_kind"), action.get("target_side")
    if not kind:
        return ""
    if kind == "HERO":
        return f"{side_label(side)} герой"
    player = state["self_player"] if side == "SELF" else state["opponent"]
    zone = player.get("locations") if kind == "LOCATION" else player.get("board")
    pos = action.get("target_board_position")
    name = texts.card(action.get("target_card_id"))["name"]
    for e in zone or []:
        if e.get("board_position") == pos:
            return f"{side_label(side)} {name} [{e.get('current_attack')}/{e.get('current_health')}] (поз. {pos})"
    return f"{side_label(side)} {name} (поз. {pos})"


def describe(state: dict, texts: CardTexts, action: dict) -> dict:
    """Human-readable label; the raw action dict is not sent to the page."""
    kind = action.get("type")
    target = target_name(state, texts, action)
    tail = f" → {target}" if target else ""
    if kind == "END_TURN":
        return {"family": "END_TURN", "label": "Закончить ход"}
    if kind in ("PLAY_CARD", "PREPARE_CARD"):
        card = texts.card(action.get("card_id"))
        verb = "Подготовить (Prepare)" if kind == "PREPARE_CARD" else "Сыграть"
        pos = action.get("play_position")
        place = f", на позицию {pos}" if action.get("card_type") in ("MINION", "LOCATION") and pos else ""
        hand = action.get("hand_index")
        hand_text = f" [рука #{hand + 1}]" if isinstance(hand, int) else ""
        return {"family": kind, "label": f"{verb}: {card['name']}{hand_text} ({action.get('card_cost')} маны){place}{tail}",
                "card": card["name"], "text": card["text"]}
    if kind == "ATTACK":
        if action.get("source_is_hero"):
            source = "Ваш герой"
        else:
            name = texts.card(action.get("source_card_id") or action.get("card_id"))["name"]
            source = f"{name} [{action.get('source_attack')}/{action.get('source_health')}] (поз. {action.get('source_board_position')})"
        return {"family": "ATTACK", "label": f"Атака: {source}{tail}"}
    if kind == "HERO_POWER":
        card = texts.card(action.get("source_card_id") or action.get("card_id"))
        return {"family": "HERO_POWER", "label": f"Сила героя: {card['name']}{tail}", "text": card["text"]}
    if kind == "ACTIVATE_LOCATION":
        card = texts.card(action.get("source_card_id") or action.get("card_id"))
        return {"family": "ACTIVATE_LOCATION", "label": f"Активировать локацию: {card['name']}{tail}",
                "text": card["text"]}
    card = texts.card(action.get("card_id") or action.get("source_card_id"))
    return {"family": str(kind), "label": f"{kind}: {card['name']}{tail}", "text": card["text"]}


def render_screen(texts: CardTexts, position: dict, screen: dict) -> dict:
    state = position["state"]
    hand = []
    for index, card in enumerate(state.get("self_hand") or [], start=1):
        item = render_card(texts, card) or {"name": "Неизвестная карта"}
        item["slot"] = index
        hand.append(item)
    menu = [{"choice": n, **describe(state, texts, position["legal_actions"][i])}
            for n, i in enumerate(screen["menu_order"], start=1)]
    for item in menu:
        item["group"] = re.sub(r", на позицию \d+", "", item["label"])
    return {"screen_id": screen["screen_id"], "turn_number": state.get("turn_number"),
            "self": render_player(texts, state["self_player"]), "opponent": render_player(texts, state["opponent"]),
            "hand": hand, "opponent_known_cards": [render_card(texts, c) for c in state.get("opponent_known_cards") or []],
            "menu": menu}


def audit_payload(value: Any, path: str = "$") -> list[str]:
    problems = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_KEYS:
                problems.append(f"{path}.{key}")
            problems += audit_payload(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            problems += audit_payload(item, f"{path}[{i}]")
    return problems


# ----- lock --------------------------------------------------------------------------------------

def run_lock() -> None:
    inventory_path, pool_path = PRIVATE / "inventory.private.json", PRIVATE / "pool.private.jsonl"
    inventory = read_json(inventory_path)
    pool_text = pool_path.read_text(encoding="utf-8")
    if sha256_bytes(pool_text.encode("utf-8")) != inventory["pool_sha256"]:
        raise ValueError("pool changed since inventory")
    pool = [json.loads(line) for line in pool_text.splitlines()]
    classes = {m["game_id"]: m["self_class"] for m in inventory["matches"]}
    samples = select_samples(pool, classes)
    opponents = {m["game_id"]: m["opponent_class"] for m in inventory["matches"]}
    main_matches = {p["game_id"] for p in samples["main"]}
    # The product targets one or two of the user's own decks, so diversity is required of opponents;
    # SELF classes are reported per class rather than gated (decided from the inventory, before any label).
    main_status = ("READY" if len(samples["main"]) == MAIN_UNIQUE and len(main_matches) >= MAIN_MIN_MATCHES
                   and len({opponents[g] for g in main_matches}) >= MAIN_MIN_OPPONENT_CLASSES
                   else "INSUFFICIENT_DATA")
    texts = CardTexts()
    by_id = {position_id(p): p for p in pool}
    batches = {}
    for batch, unique, repeats in (("pilot", samples["pilot"], samples["pilot_repeats"]),
                                   ("main", samples["main"], samples["main_repeats"])):
        screens = screens_for(batch, unique, repeats)
        payload = {"batch": batch, "screens": [render_screen(texts, by_id[s["position_id"]], s) for s in screens]}
        problems = audit_payload(payload)
        if problems:
            raise ValueError(f"blind payload audit failed: {problems[:5]}")
        payload_text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        manifest = {"batch": batch, "screens": screens,
                    "positions": {position_id(p): {"decision_id": p["decision_id"], "game_id": p["game_id"],
                                                   "state_hash": p["state_hash"], "menu_size": len(p["legal_actions"]),
                                                   "menu_bucket": menu_bucket(p), "turn_number": turn_of(p),
                                                   "self_class": classes[p["game_id"]]}
                                  for p in unique}}
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
        write_once(PRIVATE / f"{batch}.payload.private.json", payload_text)
        write_once(PRIVATE / f"{batch}.manifest.private.json", manifest_text)
        batches[batch] = {
            "unique_positions": len(unique), "repeat_screens": len(repeats), "screens": len(screens),
            "matches": len({p["game_id"] for p in unique}),
            "self_classes": dict(Counter(classes[p["game_id"]] for p in unique)),
            "opponent_classes": dict(Counter(opponents[p["game_id"]] for p in unique)),
            "menu_buckets": dict(Counter(menu_bucket(p) for p in unique)),
            "turn_buckets": dict(Counter("1-8" if turn_of(p) <= 8 else "9-16" if turn_of(p) <= 16 else "17+"
                                         for p in unique)),
            "max_positions_per_match": max(Counter(p["game_id"] for p in unique).values()),
            "payload_sha256": sha256_bytes(payload_text.encode("utf-8")),
            "manifest_sha256": sha256_bytes(manifest_text.encode("utf-8")),
            "identity_sha256": sha256_bytes(canonical(sorted(p["decision_id"] for p in unique)).encode("utf-8")),
            "cards_without_text_rendered": sum(1 for s in payload["screens"] for c in iter_cards(s) if not c),
        }
    batches["main"]["status"] = main_status
    lock = {
        "schema": "manamind.decision_quality_review_1/lock/1", "created_at_utc": now(), "source_commit": git_head(),
        "code_sha256": {p: sha256_file(ROOT / p) for p in ("scripts/decision_quality_review_1.py",
                                                           "scripts/decision_quality_review_1_tool.html")},
        "inventory_sha256": sha256_file(inventory_path), "pool_sha256": inventory["pool_sha256"],
        "raw_log_sha256": {m["source"]: m["raw_sha256"] for m in inventory["matches"]},
        "inventory": inventory_summary(inventory), "seed": SEED, "batches": batches,
        "card_metadata_snapshot": texts.meta.snapshot_id, "card_ids_missing_from_metadata": len(texts.missing),
        "blind": {"model_outputs_computed": False, "chosen_action_or_result_written": False,
                  "forbidden_payload_keys": sorted(FORBIDDEN_KEYS)},
        "pilot_criteria": PILOT_CRITERIA,
    }
    lock_text = json.dumps(lock, ensure_ascii=False, indent=1) + "\n"
    write_once(PRIVATE / "lock.private.json", lock_text)
    public = {k: v for k, v in lock.items() if k != "raw_log_sha256"}
    public["raw_logs"] = {"count": len(lock["raw_log_sha256"]),
                          "manifest_sha256": sha256_bytes(canonical(lock["raw_log_sha256"]).encode("utf-8"))}
    public["private_lock_sha256"] = sha256_bytes(lock_text.encode("utf-8"))
    write_once(REPORT / "lock.json", json.dumps(public, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: public[k] for k in ("inventory", "batches")}, ensure_ascii=False, indent=1))


def iter_cards(screen: dict):
    """known_text flags of every card on a screen (hand, boards, heroes' powers/weapons)."""
    for card in screen["hand"]:
        yield card.get("known_text", False)
    for side in ("self", "opponent"):
        player = screen[side]
        for group in ("board", "locations"):
            for card in player[group]:
                yield card.get("known_text", False)
        for single in ("hero_power", "weapon"):
            if player[single]:
                yield player[single].get("known_text", False)


# ----- labels ------------------------------------------------------------------------------------

def validate_label(label: dict, screen: dict) -> list[str]:
    errors = []
    size = len(screen["menu"])
    marks = label.get("marks", {})
    if not isinstance(marks, dict):
        return ["marks must be an object"]
    for key, value in marks.items():
        if not str(key).isdigit() or not 1 <= int(key) <= size:
            errors.append(f"unknown choice {key}")
        if value not in ACTION_MARKS:
            errors.append(f"bad mark {value}")
    best = label.get("best", [])
    if any(str(b) not in marks or marks[str(b)] != "ACCEPTABLE" for b in best):
        errors.append("best must be marked ACCEPTABLE")
    status = label.get("status")
    if status == "LABELED":
        if not any(v == "ACCEPTABLE" for v in marks.values()):
            errors.append("LABELED needs at least one ACCEPTABLE action")
    elif status == "INSUFFICIENT_INFORMATION":
        reasons = label.get("insufficient_reasons", [])
        if not reasons or any(r not in INSUFFICIENT_REASONS for r in reasons):
            errors.append("INSUFFICIENT_INFORMATION needs a known reason")
    else:
        errors.append("status must be LABELED or INSUFFICIENT_INFORMATION")
    if label.get("confidence") not in CONFIDENCE:
        errors.append("confidence required")
    return errors


def labels_path(rater: str, batch: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", rater):
        raise ValueError("rater must be lowercase letters, digits, - or _")
    return PRIVATE / "labels" / rater / f"{batch}.labels.jsonl"


def latest_labels(path: Path) -> dict[str, dict]:
    latest = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                latest[row["screen_id"]] = row
    return latest


def batch_unlocked(batch: str, rater: str) -> tuple[bool, str]:
    if batch == "pilot":
        return True, ""
    lock = read_json(PRIVATE / "lock.private.json")
    if lock["batches"]["main"].get("status") != "READY":
        return False, "main sample INSUFFICIENT_DATA"
    freeze = PRIVATE / "labels" / rater / "pilot.freeze.json"
    if not freeze.exists():
        return False, "pilot labels are not frozen"
    if read_json(freeze).get("pilot_verdict") != "PASS":
        return False, "pilot criteria did not pass"
    return True, ""


def make_server(batch: str, rater: str, port: int) -> ThreadingHTTPServer:
    ok, why = batch_unlocked(batch, rater)
    if not ok:
        raise SystemExit(f"batch '{batch}' is locked: {why}")
    lock = read_json(PRIVATE / "lock.private.json")
    payload_text = (PRIVATE / f"{batch}.payload.private.json").read_text(encoding="utf-8")
    if sha256_bytes(payload_text.encode("utf-8")) != lock["batches"][batch]["payload_sha256"]:
        raise ValueError("payload changed since lock")
    payload = json.loads(payload_text)
    screens = {s["screen_id"]: s for s in payload["screens"]}
    frozen = PRIVATE / "labels" / rater / f"{batch}.freeze.json"
    path = labels_path(rater, batch)
    path.parent.mkdir(parents=True, exist_ok=True)
    page = TOOL_HTML.read_text(encoding="utf-8")
    write_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, value: Any) -> None:
            self._send(code, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802 - http.server API
            if self.path == "/":
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/batch":
                self._json(200, {"batch": batch, "rater": rater, "frozen": frozen.exists(),
                                 "screens": payload["screens"], "labels": latest_labels(path)})
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path != "/api/label":
                return self._send(404, b"not found", "text/plain")
            if frozen.exists():
                return self._json(409, {"errors": ["labels of this batch are frozen"]})
            try:
                label = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"errors": ["invalid JSON"]})
            screen = screens.get(label.get("screen_id"))
            if screen is None:
                return self._json(400, {"errors": ["unknown screen"]})
            errors = validate_label(label, screen)
            if errors:
                return self._json(400, {"errors": errors})
            row = {key: label.get(key) for key in ("screen_id", "status", "marks", "best", "insufficient_reasons",
                                                   "confidence", "display_problem", "remembers_game",
                                                   "needs_independent_review", "comment", "active_seconds")}
            row.update(rater=rater, batch=batch, saved_at_utc=now())
            with write_lock, open(path, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical(row) + "\n")
            self._json(200, {"saved": True})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(batch: str, rater: str, port: int, open_browser: bool) -> None:
    server = make_server(batch, rater, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Разметка '{batch}' для '{rater}': {url}  (Ctrl+C — остановить; метки сохраняются при каждом «Сохранить»)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def pilot_verdict(screens: list[dict], labels: dict[str, dict], manifest: dict) -> dict:
    repeat_ids = {s["screen_id"] for s in manifest["screens"] if s["repeat"]}
    unique_ids = [s["screen_id"] for s in manifest["screens"] if not s["repeat"]]
    times = [labels[s]["active_seconds"] for s in labels if isinstance(labels[s].get("active_seconds"), (int, float))]
    display_flags = sum(bool(labels[s].get("display_problem")) for s in labels)
    display_insufficient = sum(1 for s in unique_ids if s in labels and labels[s]["status"] == "INSUFFICIENT_INFORMATION"
                               and set(labels[s].get("insufficient_reasons") or []) & set(DISPLAY_REASONS))
    checks = {
        "P1_complete": len(labels) == len(screens),
        "P2_display": display_flags <= 2,
        "P3_display_insufficient": display_insufficient <= 3,
        "P4_workload": bool(times) and statistics.median(times) <= 180,
        "P5_blind_payload": not audit_payload({"screens": screens}),
    }
    return {"checks": checks, "pilot_verdict": "PASS" if all(checks.values()) else "FAIL",
            "screens": len(screens), "labeled": len(labels), "repeat_screens": len(repeat_ids),
            "display_problem_screens": display_flags, "display_insufficient_unique": display_insufficient,
            "median_active_seconds": statistics.median(times) if times else None,
            "projected_main_hours": round(statistics.median(times) * (MAIN_UNIQUE + MAIN_REPEATS) / 3600, 1)
            if times else None}


def run_freeze(batch: str, rater: str) -> None:
    path = labels_path(rater, batch)
    out = path.parent / f"{batch}.freeze.json"
    if out.exists():
        raise SystemExit(f"already frozen: {out.relative_to(ROOT)}")
    payload = read_json(PRIVATE / f"{batch}.payload.private.json")
    manifest = read_json(PRIVATE / f"{batch}.manifest.private.json")
    labels = latest_labels(path)
    freeze = {"schema": "manamind.decision_quality_review_1/freeze/1", "batch": batch, "rater": rater,
              "frozen_at_utc": now(), "labels_sha256": sha256_file(path) if path.exists() else None,
              "screens": len(payload["screens"]), "labeled_screens": len(labels),
              "status_counts": dict(Counter(r["status"] for r in labels.values())),
              "model_outputs_seen_before_freeze": False}
    if batch == "pilot":
        freeze.update(pilot_verdict(payload["screens"], labels, manifest))
    elif len(labels) != len(payload["screens"]):
        raise SystemExit(f"{len(payload['screens']) - len(labels)} screens are not labeled yet")
    write_once(out, json.dumps(freeze, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(freeze, ensure_ascii=False, indent=1))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--inventory", action="store_true")
    phase.add_argument("--lock", action="store_true")
    phase.add_argument("--serve", action="store_true")
    phase.add_argument("--freeze", action="store_true")
    parser.add_argument("--batch", choices=("pilot", "main"), default="pilot")
    parser.add_argument("--rater", default="user")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.inventory:
        run_inventory()
    elif args.lock:
        run_lock()
    elif args.serve:
        serve(args.batch, args.rater, args.port, not args.no_browser)
    else:
        run_freeze(args.batch, args.rater)


if __name__ == "__main__":
    main()
