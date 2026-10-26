"""CARD-IR-B1-INDEPENDENT-REVIEW diagnostics. Write-once output, frozen checkers, pinned snapshot only.

1. counterfactual: v0.1 declarations written by the reviewer for B1 cards where the B1 author may have been
   overconservative. Shows what the frozen v0.1 vocabulary and validator accept and which status they compute.
2. wrong_but_accepted: declarations that are wrong as Hearthstone semantics (each with a concrete game case) and are
   checked against the frozen validator, the A lexical lint and the B1 semantic lint.
3. probes: single contract questions (e.g. can a '$' amount be written without its mark).
4. reuse: how many cards of the B1 frame mention each candidate v0.2 element (text regex screen, not a parser).

No games, no holdout, no generation by API, no change to Stage A/B1 declarations or to the checkers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from manamind.card_ir import validate_declaration  # noqa: E402
from manamind.card_ir.lint import lint_declaration  # noqa: E402
from manamind.card_ir.render import render  # noqa: E402
from manamind.card_ir.semantic_lint import lint_semantics  # noqa: E402
from manamind.card_ir.validate import normalise_text  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.card_metadata.snapshot import plain_text, strip_text_artifacts  # noqa: E402

SOURCE = "Reviewer-written probe (Claude Opus 5.5); not a gold declaration"


def base(meta, card_id, **fields):
    text = strip_text_artifacts(meta.get(card_id)["text"])
    doc = {"ir": "card-ir/0.1", "card_id": card_id, "snapshot": meta.snapshot_id, "role": "sample", "text": text,
           "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "abilities": [], "dependencies": [],
           "decisions": []}
    doc.update(fields)
    return doc


def dep(dep_id, kind, scope, detail):
    return {"id": dep_id, "kind": kind, "scope": scope, "detail": detail, "source_needed": SOURCE, "card_level": True}


def target(where=None, kind="MINION"):
    choose = {"pick": "CHOSEN", "type": kind, "side": "ANY", "zone": "PLAY"}
    if where:
        choose["where"] = where
    return {"bind": "target", "choose": choose}


def damage(n, to=None, mark="$"):
    amount = {"n": n, "mark": mark} if mark else n
    return {"op": "DEAL_DAMAGE", "to": to or {"ref": "target"}, "amount": amount}


ALIVE = {"cmp": [{"stat": "HEALTH", "of": {"ref": "target"}}, ">", 0]}
NON_PALADIN = {"pick": "ALL", "type": "MINION", "side": "ANY",
               "exclude": [{"pick": "ALL", "type": "MINION", "side": "ANY", "where": [{"card_class": "PALADIN"}]}]}
SPLIT_ENEMIES = {"repeat": {"stat": "ATTACK", "of": "SELF"},
                 "do": {"op": "DEAL_DAMAGE", "to": {"pick": "RANDOM", "n": 1, "type": "CHARACTER", "side": "ENEMY"},
                        "amount": 1}}


def counterfactual(meta):
    """The reviewer's best faithful v0.1 encodings (status computed by the validator, not chosen)."""
    return {
        "JAIL_118": base(
            meta, "JAIL_118",
            abilities=[{"kind": "play", "label": "BATTLECRY", "span": "Battlecry: Destroy all non-Paladin minions.",
                        "effect": {"op": "DESTROY", "to": NON_PALADIN}}],
            dependencies=[dep("multiclass", "UNKNOWN_RULE", "CONDITIONAL",
                              "Whether pred:card_class PALADIN matches a multi-class minion listing Paladin")],
            decisions=[{"id": "multiclass", "question": "Does a multi-class minion with Paladin count as Paladin?",
                        "alternatives": ["Paladin among its classes", "single-class Paladin only"],
                        "chosen": "UNRESOLVED", "basis": "UNKNOWN", "risk": "EDGE", "dep": "multiclass",
                        "discriminating_case": "A Paladin/Priest minion on board survives only in the first reading."}],
            status="FULL_DEP"),
        "TIME_216": base(
            meta, "TIME_216",
            abilities=[{"kind": "play", "label": "SPELL", "span": "Deal $5 damage to a minion. If it survives, draw 2 cards.",
                        "target": target(),
                        "effect": {"seq": [damage(5), {"if": ALIVE, "then": {"op": "DRAW", "player": "SELF", "count": 2}}]}}],
            dependencies=[dep("pending_destroy", "UNKNOWN_RULE", "CONDITIONAL",
                              "Health > 0 does not see a minion set pending destroy by a reaction (counts as dying)")],
            status="FULL_DEP"),
        "FIR_953": base(
            meta, "FIR_953",
            keywords=[{"keyword": "RUSH", "span": "Rush."}],
            abilities=[{"kind": "trigger",
                        "span": "After this attacks a minion and survives, deal this minion's Attack damage split among all enemies.",
                        "event": {"type": "ATTACK_DECLARED", "subject": "SELF",
                                  "defender": {"pick": "ALL", "type": "MINION", "side": "ENEMY"}},
                        "timing": "AFTER",
                        "condition": {"cmp": [{"stat": "HEALTH", "of": "SELF"}, ">", 0]},
                        "effect": SPLIT_ENEMIES}],
            dependencies=[dep("attacker_role", "UNKNOWN_RULE", "CORE",
                              "v0.1 does not define the subject role of ATTACK_DECLARED; read here as the attacker")],
            decisions=[{"id": "subject", "question": "Is ATTACK_DECLARED.subject the attacker?",
                        "alternatives": ["attacker", "undefined"], "chosen": "attacker", "basis": "ASSUMPTION",
                        "risk": "OUTCOME", "dep": "attacker_role",
                        "discriminating_case": "An enemy minion attacks Magma Hound: no trigger in the card's reading."}],
            status="PARTIAL"),
    }


def wrong_but_accepted(meta):
    """Each entry: (declaration, concrete game case where it differs from the card)."""
    torch = base(meta, "CATA_585",
                 abilities=[{"kind": "play", "label": "SPELL", "span": "Deal $8 damage to a damaged minion.",
                             "target": target([{"damaged": True}]), "effect": damage(8)}],
                 reminders=[{"span": "Return this to hand with any excess damage.", "why": "flavour"}], status="FULL")
    frost = base(meta, "CORE_RLK_063",
                 abilities=[{"kind": "play", "label": "SPELL", "span": "Deal $5 damage.", "target": target(kind="CHARACTER"),
                             "effect": damage(5)},
                            {"kind": "play", "label": "SPELL", "span": "Summon a 5/5 Frostwyrm.",
                             "effect": {"op": "SUMMON", "count": 1,
                                        "what": {"card": "RLK_063t", "resolved": "NAME_IN_SET", "dep": "token"}}}],
                 reminders=[{"span": "Freeze all enemy minions.", "why": "reminder"}],
                 dependencies=[dep("token", "TOKEN_IDENTITY", "DATA", "RLK_063t by name")], status="FULL_DEP")
    return {
        "TIME_216/unconditional_draw": (base(
            meta, "TIME_216",
            abilities=[{"kind": "play", "label": "SPELL", "span": "Deal $5 damage to a minion. If it survives, draw 2 cards.",
                        "target": target(), "effect": {"seq": [damage(5), {"op": "DRAW", "player": "SELF", "count": 2}]}}],
            status="FULL"), "Target an enemy 3/3: it dies; the card draws 0, the declaration draws 2."),
        "JAIL_118/destroy_all": (base(
            meta, "JAIL_118",
            abilities=[{"kind": "play", "label": "BATTLECRY", "span": "Battlecry: Destroy all non-Paladin minions.",
                        "effect": {"op": "DESTROY", "to": {"pick": "ALL", "type": "MINION", "side": "ANY"}}}],
            status="FULL"), "Board with a Silver Hand Recruit: the card keeps it (and V'ama), the declaration kills both."),
        "JAIL_118/enemy_only": (base(
            meta, "JAIL_118",
            abilities=[{"kind": "play", "label": "BATTLECRY", "span": "Battlecry: Destroy all non-Paladin minions.",
                        "effect": {"op": "DESTROY", "to": {**NON_PALADIN, "side": "ENEMY"}}}],
            status="FULL"), "A friendly neutral minion survives in the declaration but dies to the card (control)."),
        "JAIL_399/shuffle_not_bottom": (base(
            meta, "JAIL_399",
            keywords=[{"keyword": "TAUNT", "span": "Taunt."}],
            abilities=[{"kind": "deathrattle",
                        "span": "Deathrattle: Put two 8/8 Demons with Taunt and Lifesteal on the bottom of your deck.",
                        "effect": {"repeat": 2, "do": {"op": "SHUFFLE_INTO_DECK", "player": "SELF",
                                                       "what": {"card": "JAIL_399t1", "resolved": "DESCRIPTION_MATCH",
                                                                "dep": "token"}}}}],
            dependencies=[dep("token", "TOKEN_IDENTITY", "DATA", "JAIL_399t1 by prefix and stats")],
            status="FULL_DEP"), "Next draw after the Deathrattle: the card never draws a Grandmother Imp from a "
                                "non-empty deck, the declaration may."),
        "CORE_SCH_713/this_turn": (base(
            meta, "CORE_SCH_713",
            abilities=[{"kind": "play", "label": "BATTLECRY",
                        "span": "Battlecry: Your opponent's spells cost (1) more next turn.",
                        "effect": {"op": "ADD_PLAYER_EFFECT", "player": "OPPONENT", "duration": "THIS_TURN",
                                   "modifier": {"cost": {"reduce": -1}}, "applies_to": [{"card_type": "SPELL"}]}}],
            status="FULL"), "Opponent's 1-mana spell on their next turn: the card makes it cost 2, the declaration 1."),
        "FIR_953/hero_attack": (base(
            meta, "FIR_953",
            keywords=[{"keyword": "RUSH", "span": "Rush."}],
            abilities=[{"kind": "trigger",
                        "span": "After this attacks a minion and survives, deal this minion's Attack damage split among all enemies.",
                        "event": {"type": "HERO_ATTACK", "player": "SELF"}, "timing": "AFTER", "effect": SPLIT_ENEMIES}],
            status="FULL"), "Your hero attacks with a weapon while Magma Hound stays idle: only the declaration fires."),
        "CATA_585/reminder_loophole": (torch, "Any damaged 2-Health target: the card returns Torch(6); the declaration "
                                               "never returns it, and adds Spell Damage the card ignores."),
        "CORE_RLK_063/reminder_loophole": (frost, "Enemy minions attack next turn in the declaration; the card froze them."),
        "EDR_895/everything_reminder": (base(
            meta, "EDR_895",
            reminders=[{"span": "Battlecry: Start a three turn lunar cycle. When the Full Moon rises, your cards cost (1) "
                                "this game.", "why": "reminder"}],
            status="FULL"), "Three own turns later: the card sets all your card costs to 1, the declaration does nothing."),
    }


def probes(meta):
    """Contract questions answered by running the frozen validator."""
    torch_unmarked = base(meta, "CATA_585",
                          abilities=[{"kind": "play", "label": "SPELL", "span": "Deal $8 damage to a damaged minion.",
                                      "target": target([{"damaged": True}]), "effect": damage(8, mark=None)}],
                          unexpressed=[{"span": "Return this to hand with any excess damage.", "why": "probe"}],
                          status="PARTIAL")
    # "Costs (1) less for each X": with any counter the literal (1) has no IR number to match (no multiplication).
    per_each = base(meta, "CATA_452",
                    abilities=[{"kind": "play", "label": "SPELL", "span": "Summon a 6/6 Dragon.",
                                "effect": {"op": "SUMMON", "count": 1,
                                           "what": {"card": "CATA_452t", "resolved": "DESCRIPTION_MATCH", "dep": "token"}}},
                               {"kind": "aura", "active_in": "HAND",
                                "span": "Costs (1) less for each damage you dealt with spells this turn.",
                                "modifier": {"cost": {"reduce": {"counter": {"event": "SPELL_CAST", "player": "SELF",
                                                                             "scope": "THIS_TURN"}}}}}],
                    dependencies=[dep("token", "TOKEN_IDENTITY", "DATA", "CATA_452t by prefix and stats")],
                    status="FULL_DEP")
    return {"CATA_585/ImmuneToSpellpower_without_mark": torch_unmarked,
            "CATA_452/one_less_for_each_counter": per_each}


def run(doc, meta):
    report = validate_declaration(doc, meta)
    old, new = lint_declaration(doc), lint_semantics(doc)
    return {"validator": report.errors, "old_lint": old, "new_lint": new, "computed_status": report.computed_status,
            "declared_status": doc.get("status"), "accepted": not (report.errors or old or new),
            "render": render(doc, meta), "declaration": doc}


REUSE = {
    # candidate v0.2 element -> regex over normalised lower-case text of the frame
    "op:FREEZE": r"\bfreeze\b",
    "pred:alive / 'survives'": r"\bsurviv",
    "event roles: 'after X attacks'": r"\bafter (this|a|an|your|a friendly|it)\b[^.]*\battacks\b",
    "split among": r"\bsplit among\b",
    "duration:NEXT_TURN ('next turn')": r"\bnext turn\b",
    "duration:THIS_GAME / permanent ('this game')": r"\bthis game\b",
    "delayed start ('in N turns', 'N-turn')": r"\bin (\d+|two|three|four|five) turns\b|\b(two|three|four|five|\d+)[ -]turns?\b",
    "event:TURN_START": r"\bat the start of\b|\bstart of (your|the|each|their) (next )?turn\b",
    "deck position (top/bottom)": r"\b(top|bottom) of (your|the|their|your opponent's) deck\b",
    "zone move to hand ('return ... hand')": r"\breturn\b[^.]*\bhand\b",
    "counter: damage amount": r"\bdamage\b[^.]*\b(dealt|taken|you've dealt|you dealt)\b|\bfor each damage\b",
    "counter: damage this turn/game (broad)": r"\bdamage\b[^.]*\bthis (turn|game)\b",
    "player-wide cost aura ('your X cost', 'opponent's X cost')":
        r"\b(your|your opponent's|enemy) (cards|spells|minions|weapons)\b[^.]*\bcosts? \(\d+\)",
    "value arith mul ('(N) less/more for each')": r"\(\d+\) (less|more) for each\b|\bcosts? \(\d+\) less for each\b",
    "excess damage": r"\bexcess\b",
    "class negation ('non-X')": r"\bnon-[a-z]+",
    "runtime placeholders {0}/{1}": None,
    "herald": r"\bherald\b",
}


def reuse(meta):
    scope = json.loads((ROOT / "data/cards/standard_scope_20261001.json").read_text(encoding="utf-8"))
    excluded = {p.stem for p in (ROOT / "reports/card_ir_pilot_1/declarations").glob("*.json")}
    excluded |= set(scope["excluded_card_ids"])
    frame = [r for r in meta.records() if r.get("collectible") is True
             and r.get("set") in set(scope["standard_sets"]) | {"BE"}
             and r.get("type") in ("MINION", "SPELL", "WEAPON", "LOCATION", "HERO")
             and r["id"] not in excluded and plain_text(r.get("text"))]
    ids = sorted(r["id"] for r in frame)
    out = {"frame_size": len(frame),
           "frame_ids_sha256": hashlib.sha256(
               (json.dumps(ids, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).hexdigest(),
           "note": "B1 frame (pinned Standard sets + BE, collectible, nonempty text, A declarations and scope "
                   "exclusions removed). Text screen only: a match is a mention, not an occurrence of the semantics.",
           "counts": {}}
    for name, pattern in REUSE.items():
        if pattern is None:
            hits = [r for r in frame if re.search(r"\{\d\}", strip_text_artifacts(r["text"]))]
        else:
            hits = [r for r in frame if re.search(pattern, normalise_text(strip_text_artifacts(r["text"])).lower())]
        out["counts"][name] = len(hits)
    # '$' amounts on cards tagged ImmuneToSpellpower: split/repeat spells vs single-packet spells like Torch.
    immune = [r for r in frame if "ImmuneToSpellpower" in (r.get("mechanics") or []) and "$" in (r.get("text") or "")]
    split = [r for r in immune if re.search(r"\bsplit\b|\brandom", normalise_text(r["text"]).lower())]
    out["immune_to_spellpower_with_dollar"] = {"cards": len(immune), "split_or_random": len(split),
                                               "other_ids": sorted(r["id"] for r in immune if r not in split)}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    meta = CardMetadata.load()
    result = {
        "id": "CARD-IR-B1-INDEPENDENT-REVIEW/diagnostics",
        "snapshot": meta.snapshot_id,
        "checkers": "frozen validate.py, lint.py (A) and semantic_lint.py (B1) at the B1 commit",
        "counterfactual": {k: run(v, meta) for k, v in counterfactual(meta).items()},
        "wrong_but_accepted": {k: {**run(doc, meta), "game_case": case}
                               for k, (doc, case) in wrong_but_accepted(meta).items()},
        "probes": {k: run(v, meta) for k, v in probes(meta).items()},
        "reuse": reuse(meta),
    }
    data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with args.output.open("xb") as stream:
        stream.write(data)
    for group in ("counterfactual", "wrong_but_accepted", "probes"):
        for key, item in result[group].items():
            flags = [k for k in ("validator", "old_lint", "new_lint") if item[k]]
            print(f"{group:20} {key:38} status={item['computed_status']:9} accepted={item['accepted']!s:5} "
                  f"caught_by={flags or '-'}")
    for name, count in result["reuse"]["counts"].items():
        print(f"reuse {name:50} {count}")


if __name__ == "__main__":
    main()
