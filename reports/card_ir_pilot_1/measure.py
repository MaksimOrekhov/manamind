"""CARD-IR-PILOT-1 stage A measurements over the locked sample (deterministic; reads only pinned metadata).

    python -I reports/card_ir_pilot_1/measure.py --output reports/card_ir_pilot_1/results.json

Vocabulary growth is a post-hoc count over the final vocabulary in the locked authoring order and as a mean over seeded
permutations. The author saw every sampled text before writing the schema, so the curve measures how many new
elements each card needs given the earlier cards, not a blind chronology of design.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
PILOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_ir import ELEMENTS, RULES, normalise_text, validate_declaration  # noqa: E402
from manamind.card_ir.render import render  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.card_metadata.snapshot import plain_text, strip_text_artifacts  # noqa: E402

PERMUTATIONS = 1000
PERMUTATION_SEED = 20261028
PROGRAM_LIKE = {"control:set", "value:var", "value:arith", "control:repeat_while"}
WEAK_BASES = {"UNVERIFIED", "ASSUMPTION", "UNKNOWN"}
# Gap markers are the absence of a primitive, not a primitive.
HOLES = {"value:unknown", "cond:unknown"}
# Node kinds of the language versus values of an enumeration inside a node kind.
STRUCTURAL = {"ability", "control", "op", "card_source", "value", "cond", "modifier"}


def load_declarations() -> dict[str, dict]:
    docs = {}
    for path in sorted((PILOT / "declarations").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        docs[doc["card_id"]] = doc
    return docs


def ir_nodes(value) -> int:
    if isinstance(value, dict):
        return 1 + sum(ir_nodes(item) for item in value.values())
    if isinstance(value, list):
        return sum(ir_nodes(item) for item in value)
    return 0


def new_per_card(order: list[str], elements: dict[str, set[str]]) -> list[int]:
    seen: set[str] = set()
    counts = []
    for card in order:
        counts.append(len(elements[card] - seen))
        seen |= elements[card]
    return counts


def thirds(counts: list[float]) -> dict[str, float]:
    n = len(counts)
    cut = [round(n * k / 3) for k in range(4)]
    parts = [counts[cut[k]:cut[k + 1]] for k in range(3)]
    first, middle, last = (round(mean(part), 3) for part in parts)
    return {"first": first, "middle": middle, "last": last,
            "last_over_first": round(last / first, 3) if first else None}


def permutation_curve(cards: list[str], elements: dict[str, set[str]], seed: int, *, any_new: bool = False) -> list[float]:
    """Mean new elements at each position (or, with ``any_new``, the share of orders where that card needs any)."""
    rng = random.Random(seed)
    totals = [0.0] * len(cards)
    for _ in range(PERMUTATIONS):
        order = list(cards)
        rng.shuffle(order)
        for index, count in enumerate(new_per_card(order, elements)):
            totals[index] += (count > 0) if any_new else count
    return [round(total / PERMUTATIONS, 3) for total in totals]


def heaps_fit(curve: list[float]) -> dict:
    """Least-squares fit of V(n) = K * n^beta on the cumulative permutation-mean vocabulary (n >= 2)."""
    cumulative, total = [], 0.0
    for count in curve:
        total += count
        cumulative.append(total)
    points = [(math.log(n), math.log(v)) for n, v in enumerate(cumulative, start=1) if n >= 2 and v > 0]
    mx = mean(x for x, _ in points)
    my = mean(y for _, y in points)
    beta = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x, _ in points)
    k = math.exp(my - beta * mx)
    return {"beta": round(beta, 3), "k": round(k, 2), "observed_at_n": round(cumulative[-1], 1), "n": len(curve),
            "extrapolated": {str(n): round(k * n ** beta) for n in (100, 300, 1000)}}


def frame_texts(meta: CardMetadata, protocol: dict) -> list[tuple[str, str, tuple[str, ...]]]:
    """The locked random frame (before removing curated cards): id, normalised lower text, mechanics."""
    scope = json.loads((ROOT / "data/cards/standard_scope_20261001.json").read_text(encoding="utf-8"))
    sets = set(scope["standard_sets"]) | {"BE"}
    excluded = set(scope["excluded_card_ids"])
    types = ("MINION", "SPELL", "WEAPON", "LOCATION", "HERO")
    rows = []
    for record in meta.records():
        if record.get("collectible") is True and record.get("set") in sets and record.get("type") in types \
                and record["id"] not in excluded and plain_text(record.get("text")):
            text = normalise_text(strip_text_artifacts(record.get("text", ""))).lower()
            rows.append((record["id"], text, tuple(record.get("mechanics", []))))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")

    meta = CardMetadata.load()
    protocol = json.loads((PILOT / "protocol.json").read_text(encoding="utf-8"))
    docs = load_declarations()
    sample = [row["id"] for row in protocol["sample"]]
    stratum = {row["id"]: row["stratum"] for row in protocol["sample"]}
    appearances = {row["id"]: row["appearances"] for row in protocol["sample"]}
    engine = [row["id"] for row in protocol["engine_validation"]["cards"]]
    closure = sorted(card for card, doc in docs.items() if doc["role"] == "closure")
    missing = sorted(set(sample + engine) - set(docs))
    if missing:
        raise SystemExit(f"declarations missing for {missing}")

    cards: dict[str, dict] = {}
    elements: dict[str, set[str]] = {}
    for card_id, doc in docs.items():
        report = validate_declaration(doc, meta)
        if report.errors:
            raise SystemExit(f"{card_id} is invalid: {report.errors[:3]}")
        elements[card_id] = set(report.elements)
        decisions = doc["decisions"]
        cards[card_id] = {
            "role": doc["role"], "stratum": stratum.get(card_id), "appearances": appearances.get(card_id),
            "status": doc["status"], "words": len(normalise_text(doc["text"]).split()),
            "ir_nodes": ir_nodes(doc["abilities"]) + ir_nodes(doc.get("keywords", [])),
            "elements": sorted(elements[card_id]), "rules": sorted(report.rules),
            "dependencies": sorted(f"{dep['kind']}/{dep['scope']}" for dep in doc["dependencies"]),
            "decisions": len(decisions),
            "decisions_unresolved": sum(1 for d in decisions if d["chosen"] == "UNRESOLVED"),
            "decisions_outcome_weak_basis": sum(1 for d in decisions if d["risk"] == "OUTCOME" and d["basis"] in WEAK_BASES),
            "unexpressed": [item["span"] for item in doc.get("unexpressed", [])],
            "program_like": sorted(elements[card_id] & PROGRAM_LIKE),
            "rendered": render(doc, meta),
        }

    def status_counts(ids):
        return dict(sorted(Counter(cards[c]["status"] for c in ids).items()))

    curated = [c for c in sample if appearances[c] is not None]
    total_apps = sum(appearances[c] for c in curated)
    weighted = Counter()
    for card in curated:
        weighted[cards[card]["status"]] += appearances[card]
    statuses = {
        "sample": status_counts(sample), "closure": status_counts(closure), "engine_validation": status_counts(engine),
        "curated_weighted_by_appearances": {k: round(v / total_apps, 4) for k, v in sorted(weighted.items())},
        "random_part": status_counts([c for c in sample if appearances[c] is None]),
    }

    # vocabulary growth --------------------------------------------------------------------------------------------
    order = protocol["authoring_order"]["ids"]
    locked = new_per_card(order, elements)
    perm = permutation_curve(sample, elements, PERMUTATION_SEED)
    pilot_vocab = set().union(*(elements[c] for c in sample))
    engine_after_pilot = new_per_card(order + engine, elements)[len(order):]
    pilot_after_engine = new_per_card(engine + order, elements)[len(engine):]
    both = sample + engine

    def restricted(keep) -> dict[str, set[str]]:
        return {card: {e for e in found if keep(e)} for card, found in elements.items()}

    subsets = {
        "generic": restricted(lambda e: ELEMENTS[e].tier == "GENERIC" and e not in HOLES),
        "mechanic": restricted(lambda e: ELEMENTS[e].tier == "MECHANIC"),
        "structural": restricted(lambda e: ELEMENTS[e].category in STRUCTURAL and e not in HOLES),
        "enumeration": restricted(lambda e: ELEMENTS[e].category not in STRUCTURAL),
    }
    combined_curve = permutation_curve(both, elements, PERMUTATION_SEED + 1)
    by_subset = {}
    for offset, (name, subset) in enumerate(subsets.items(), start=2):
        curve = permutation_curve(both, subset, PERMUTATION_SEED + offset)
        by_subset[name] = {"vocabulary": len(set().union(*(subset[c] for c in both))), "thirds": thirds(curve),
                           "heaps": heaps_fit(curve)}
    growth = {
        "authoring_order": [{"card": c, "new": n} for c, n in zip(order, locked)],
        "authoring_order_thirds": thirds(locked),
        "permutation_mean_curve": perm,
        "permutation_thirds": thirds(perm),
        "pilot_vocabulary_size": len(pilot_vocab),
        "engine_cards_new_after_pilot": dict(zip(engine, engine_after_pilot)),
        "engine_cards_needing_new_after_pilot": sum(1 for n in engine_after_pilot if n),
        "engine_new_elements_after_pilot": sorted(set().union(*(elements[c] for c in engine)) - pilot_vocab),
        "pilot_cards_needing_new_after_engine": sum(1 for n in pilot_after_engine if n),
        "pilot_new_elements_after_engine": sum(pilot_after_engine),
        "engine_vocabulary_size": len(set().union(*(elements[c] for c in engine))),
        "combined_permutation_thirds": thirds(combined_curve),
        "combined_share_of_cards_needing_any_new_by_third": thirds(
            permutation_curve(both, elements, PERMUTATION_SEED + 6, any_new=True)),
        "combined_share_needing_new_generic_structural_by_third": thirds(
            permutation_curve(both, subsets["structural"], PERMUTATION_SEED + 7, any_new=True)),
        "combined_heaps_fit_extrapolation": heaps_fit(combined_curve),
        "combined_by_subset": by_subset,
        "vocabulary_size_all_declarations": len(set().union(*elements.values())),
        "vocabulary_size_defined": len(ELEMENTS),
        "by_tier": dict(sorted(Counter(ELEMENTS[e].tier for e in set().union(*elements.values())).items())),
        "by_category": dict(sorted(Counter(ELEMENTS[e].category for e in set().union(*elements.values())).items())),
    }

    # uniqueness and reuse screen -----------------------------------------------------------------------------------
    users: dict[str, list[str]] = {}
    for card in both:
        for element in elements[card]:
            users.setdefault(element, []).append(card)
    singletons = {e: users[e][0] for e in sorted(users) if len(users[e]) == 1}
    frame = frame_texts(meta, protocol)
    signature_hits = {}
    for element_id, element in sorted(ELEMENTS.items()):
        if element.signature:
            pattern = re.compile(element.signature)
            signature_hits[element_id] = sum(1 for _, text, _ in frame if pattern.search(text))
    sample_unique = {}
    for card in sample:
        own = sorted(e for e, owner in singletons.items() if owner == card)
        if own:
            sample_unique[card] = [{"element": e, "tier": ELEMENTS[e].tier, "frame_cards_with_signature": signature_hits.get(e)}
                                   for e in own]
    generic_unique = sorted(c for c, items in sample_unique.items() if any(i["tier"] == "GENERIC" for i in items))
    generic_unique_no_holes = sorted(c for c, items in sample_unique.items()
                                     if any(i["tier"] == "GENERIC" and i["element"] not in HOLES for i in items))
    # Screen: a generic singleton whose phrase occurs in at most 2 frame cards is rare phrasing in current Standard.
    rare_phrasing = sorted(c for c, items in sample_unique.items() if any(
        i["tier"] == "GENERIC" and i["frame_cards_with_signature"] is not None and i["frame_cards_with_signature"] <= 2
        for i in items))
    uniqueness = {
        "scope": "pilot sample (21) + engine validation (26)",
        "pre_registered_metric": "sample cards using a GENERIC element that no other card of the 47 uses",
        "sample_cards_with_generic_singleton_excluding_holes": len(generic_unique_no_holes),
        "sample_cards_with_rare_phrasing_generic_singleton": rare_phrasing,
        "singletons": [{"element": e, "card": c, "tier": ELEMENTS[e].tier, "frame_cards_with_signature": signature_hits.get(e)}
                       for e, c in singletons.items()],
        "sample_cards_with_any_singleton": len(sample_unique),
        "sample_cards_with_generic_singleton": len(generic_unique),
        "sample_cards_with_generic_singleton_ids": generic_unique,
        "sample_unique_detail": sample_unique,
        "elements_used_by_one_sample_card_only_within_sample": sum(
            1 for e in pilot_vocab if sum(1 for c in sample if e in elements[c]) == 1),
        "reuse_screen_frame_size": len(frame),
        "elements_by_number_of_users": dict(sorted(Counter(len(v) for v in users.values()).items())),
    }

    # gaps: dependencies, decisions, rules --------------------------------------------------------------------------
    deps = Counter(d for c in sample for d in cards[c]["dependencies"])
    all_decisions = [d for c in sample for d in docs[c]["decisions"]]
    rule_users = Counter(r for c in sample for r in cards[c]["rules"])
    unknown_rules = sorted(r for r in rule_users if RULES[r].basis == "UNKNOWN")
    gaps = {
        "sample_dependencies_by_kind_scope": dict(sorted(deps.items())),
        "sample_cards_with_core_gap": sorted(c for c in sample if any(d.endswith("/CORE") for d in cards[c]["dependencies"])
                                             or cards[c]["unexpressed"]),
        "sample_decisions": len(all_decisions),
        "sample_decisions_by_basis": dict(sorted(Counter(d["basis"] for d in all_decisions).items())),
        "sample_decisions_by_risk": dict(sorted(Counter(d["risk"] for d in all_decisions).items())),
        "sample_decisions_unresolved": sum(1 for d in all_decisions if d["chosen"] == "UNRESOLVED"),
        "sample_outcome_decisions_with_weak_basis": sum(
            1 for d in all_decisions if d["risk"] == "OUTCOME" and d["basis"] in WEAK_BASES),
        "universal_rules_needed_by_sample": {r: {"cards": n, "basis": RULES[r].basis} for r, n in sorted(rule_users.items())},
        "universal_rules_by_basis": dict(sorted(Counter(RULES[r].basis for r in rule_users).items())),
        "sample_cards_needing_an_unknown_basis_rule": sum(
            1 for c in sample if any(RULES[r].basis == "UNKNOWN" for r in cards[c]["rules"])),
        "unknown_basis_rules": unknown_rules,
        "program_like_cards": sorted(c for c in docs if cards[c]["program_like"]),
    }

    # metadata invariants -------------------------------------------------------------------------------------------
    split_marked = [(cid, mech) for cid, text, mech in frame if re.search(r"\$\d+ damage randomly split", text)]
    split_plain = [(cid, mech) for cid, text, mech in frame if re.search(r"(?<!\$)\b\d+ damage randomly split", text)]
    weapons = [r for r in meta.records() if r.get("type") == "WEAPON" and r.get("collectible") is True]
    metadata = {
        "split_damage_with_dollar": len(split_marked),
        "split_damage_with_dollar_and_ImmuneToSpellpower": sum(1 for _, m in split_marked if "ImmuneToSpellpower" in m),
        "split_damage_without_dollar": len(split_plain),
        "split_damage_without_dollar_and_ImmuneToSpellpower": sum(1 for _, m in split_plain if "ImmuneToSpellpower" in m),
        "collectible_weapons": len(weapons),
        "collectible_weapons_with_durability_0_and_health_set": sum(
            1 for r in weapons if r.get("durability") == 0 and isinstance(r.get("health"), int)),
        "enchantment_ids_referenced": sorted({ref for c in docs for ref in validate_declaration(docs[c], meta).card_refs
                                              if (meta.get(ref) or {}).get("type") == "ENCHANTMENT"}),
    }

    sizes = {
        "sample_mean_text_words": round(mean(cards[c]["words"] for c in sample), 2),
        "sample_mean_ir_nodes": round(mean(cards[c]["ir_nodes"] for c in sample), 2),
        "sample_mean_elements_per_card": round(mean(len(elements[c]) for c in sample), 2),
        "sample_mean_decisions_per_card": round(mean(cards[c]["decisions"] for c in sample), 2),
        "sample_max_ir_nodes": max(cards[c]["ir_nodes"] for c in sample),
    }

    payload = {
        "protocol_id": protocol["protocol_id"], "snapshot": meta.snapshot_id, "ir_version": "card-ir/0.1",
        "counts": {"sample": len(sample), "closure": len(closure), "engine_validation": len(engine), "declarations": len(docs)},
        "statuses": statuses, "growth": growth, "uniqueness": uniqueness, "gaps": gaps, "metadata": metadata,
        "sizes": sizes, "element_signature_hits": signature_hits, "cards": dict(sorted(cards.items())),
    }
    args.output.write_bytes((json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(json.dumps({k: payload[k] for k in ("counts", "statuses", "sizes")}, indent=1))
    print("growth thirds (locked / permutation / combined):", growth["authoring_order_thirds"],
          growth["permutation_thirds"], growth["combined_permutation_thirds"])
    print("engine cards needing new elements after the pilot:", growth["engine_cards_needing_new_after_pilot"],
          growth["engine_new_elements_after_pilot"])
    print("sample cards with a singleton:", uniqueness["sample_cards_with_any_singleton"],
          "generic:", uniqueness["sample_cards_with_generic_singleton"], generic_unique)


if __name__ == "__main__":
    main()
