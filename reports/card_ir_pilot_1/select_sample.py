"""Lock the CARD-IR-PILOT-1 stage A sample before any IR is written (protocol lock).

Reads only pinned metadata (no game data, no ``fresh_holdout``): the CARD-METADATA-2 candidate list, the current
HearthstoneJSON snapshot, the Standard scope file and the ManaEngine declarations. Selection is deterministic.

    python -I reports/card_ir_pilot_1/select_sample.py --output reports/card_ir_pilot_1/protocol.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.card_metadata.snapshot import plain_text, strip_text_artifacts  # noqa: E402

CANDIDATES = ROOT / "reports/card_metadata_2/card_ir_pilot_candidates.json"
SCOPE = ROOT / "data/cards/standard_scope_20261001.json"
ENGINE = ROOT / "experiments/manaengine/data/card_abilities.json"
SEED = 20261026
CURATED_QUOTA = {"S1_new_collectible": 4, "S2_new_to_source_noncollectible_token": 3, "S3_known_before_trigger_text": 4,
                 "S4_known_before_one_shot_text": 3, "S5_control_grammar_parses": 2}
RANDOM_SIZE = 5
FRAME_TYPES = ("MINION", "SPELL", "WEAPON", "LOCATION", "HERO")
# ManaEngine fields that describe one card's behaviour beyond the generic {kind, target, amount} effect list.
ENGINE_GENERIC_KEYS = {"ability", "support_state", "reviewed_rules_text", "effects"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def type_first(rows: list[dict], quota: int) -> list[dict]:
    """The most frequent card of each type (in order of first appearance), then the rest by frequency."""
    picked, seen_types = [], set()
    for row in rows:
        if row["type"] not in seen_types:
            seen_types.add(row["type"])
            picked.append(row)
        if len(picked) == quota:
            return picked
    for row in rows:
        if row not in picked:
            picked.append(row)
        if len(picked) == quota:
            break
    return picked


def largest_remainder(counts: dict[str, int], size: int) -> dict[str, int]:
    total = sum(counts.values())
    exact = {key: size * value / total for key, value in counts.items()}
    alloc = {key: int(value) for key, value in exact.items()}
    for key in sorted(exact, key=lambda k: (-(exact[k] - alloc[k]), k))[: size - sum(alloc.values())]:
        alloc[key] += 1
    return {key: value for key, value in alloc.items() if value}


def card_row(meta: CardMetadata, card_id: str, stratum: str, rule: str, appearances: int | None) -> dict:
    record = meta.get(card_id)
    text = strip_text_artifacts(record.get("text", ""))
    return {
        "stratum": stratum, "id": card_id, "name": record.get("name"), "type": record.get("type"),
        "set": record.get("set"), "card_class": record.get("cardClass"), "collectible": record.get("collectible") is True,
        "cost": record.get("cost"), "attack": record.get("attack"), "health": record.get("health"),
        "durability": record.get("durability"), "mechanics": record.get("mechanics", []),
        "referenced_tags": record.get("referencedTags", []), "appearances": appearances, "rule": rule,
        "text": text, "text_sha256": sha256_text(text),
    }


def engine_validation_set() -> list[dict]:
    """The first declaration (file order) of every ability family: each family is one typed C++ handler surface."""
    cards = json.loads(ENGINE.read_text(encoding="utf-8"))["cards"]
    chosen: dict[str, str] = {}
    for card_id, decl in cards.items():
        chosen.setdefault(decl["ability"], card_id)
    return [{"id": card_id, "ability": ability, "support_state": cards[card_id]["support_state"],
             "fields": sorted(set(cards[card_id]) - ENGINE_GENERIC_KEYS),
             "reviewed_rules_text": cards[card_id].get("reviewed_rules_text")}
            for ability, card_id in chosen.items()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; refusing to overwrite")

    meta = CardMetadata.load()
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    by_stratum: dict[str, list[dict]] = {}
    for row in candidates:
        by_stratum.setdefault(row["stratum"], []).append(row)

    curated = []
    for stratum, quota in CURATED_QUOTA.items():
        rows = sorted(by_stratum[stratum], key=lambda r: (-r["appearances"], r["id"]))
        for row in type_first(rows, quota):
            curated.append(card_row(meta, row["id"], stratum, "type_first_by_appearances", row["appearances"]))

    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    frame_sets = set(scope["standard_sets"]) | {"BE"}
    excluded = set(scope["excluded_card_ids"]) | {row["id"] for row in curated}
    frame = [r for r in meta.records()
             if r.get("collectible") is True and r.get("set") in frame_sets and r.get("type") in FRAME_TYPES
             and r["id"] not in excluded and plain_text(r.get("text"))]
    by_type: dict[str, list[str]] = {}
    for record in frame:
        by_type.setdefault(record["type"], []).append(record["id"])
    allocation = largest_remainder({k: len(v) for k, v in sorted(by_type.items())}, RANDOM_SIZE)
    rng = random.Random(SEED)
    drawn = []
    for card_type in sorted(allocation):
        for card_id in rng.sample(sorted(by_type[card_type]), allocation[card_type]):
            drawn.append(card_row(meta, card_id, f"R_random_{card_type.lower()}", f"random.Random({SEED}).sample", None))

    sample = curated + drawn
    authoring_order = [row["id"] for row in sample]
    random.Random(SEED + 1).shuffle(authoring_order)

    protocol = {
        "protocol_id": "card_ir_pilot_1_stage_a_v1",
        "locked_on": "2026-10-26",
        "status": "LOCKED_BEFORE_IR_AUTHORING",
        "hypothesis": (
            "Card effects of current Standard can be written as compositions of a small, slowly growing vocabulary of "
            "generic primitives, so that most new cards are data and manual work goes to new primitives, not to cards."),
        "baseline": {
            "outcome_grammar_full_parse": "6.0% of Standard (census, FUTURE-ARCHITECTURE-RESEARCH-1); 24.9% of real appearances (CARD-METADATA-2)",
            "manaengine": "125 declarations, 26 ability families of which 21 are named single-card handlers; 11.8% of real appearances declared",
            "manual_estimate_20260929": "about 50% of 100 cards expressible with existing RosettaStone primitives",
        },
        "inputs": {
            "candidates": {"path": "reports/card_metadata_2/card_ir_pilot_candidates.json", "sha256": sha256_file(CANDIDATES)},
            "snapshot": {"snapshot_id": meta.snapshot_id, "raw_sha256": meta.info.raw_sha256},
            "standard_scope": {"path": "data/cards/standard_scope_20261001.json", "sha256": sha256_file(SCOPE)},
            "manaengine_declarations": {"path": "experiments/manaengine/data/card_abilities.json", "sha256": sha256_file(ENGINE)},
            "text_rule": "strip_text_artifacts(record.text): layout '&' and debug tail removed; HTML, [x], $ and # kept",
            "game_data_read": "none; appearance counts are copied from the candidate list",
        },
        "selection": {
            "curated": {
                "quota": CURATED_QUOTA,
                "rule": ("within each CARD-METADATA-2 stratum, order by appearances (desc, then id); take the most frequent "
                         "card of each card type in order of first appearance; fill any remaining quota by appearances"),
            },
            "random": {
                "frame": ("collectible MINION/SPELL/WEAPON/LOCATION/HERO records of the current snapshot whose set is in the "
                          "pinned Standard scope sets or BE (BE is played in Ranked Standard on build 254477; the profile is "
                          "not changed), minus the scope's excluded IDs, minus the curated cards, minus empty-text cards"),
                "frame_size": len(frame),
                "frame_by_type": {k: len(v) for k, v in sorted(by_type.items())},
                "allocation": allocation,
                "allocation_rule": "largest remainder, proportional to the frame's type counts",
                "seed": SEED,
                "method": "random.Random(seed).sample(sorted ids of the type, n), types in alphabetical order",
            },
            "closure_rule": ("cards that a sampled text names and that the IR must reference (tokens, generated cards) get "
                             "their own declarations as closure items; they are reported separately and never replace a "
                             "sampled card"),
            "no_substitution": "a card that cannot be described stays in the sample and is reported as PARTIAL or UNSUPPORTED",
        },
        "authoring_order": {"seed": SEED + 1, "ids": authoring_order,
                            "note": "vocabulary growth is reported in this order and as a mean over 1000 seeded permutations"},
        "sample": sample,
        "engine_validation": {
            "rule": ("first declaration in file order of every ManaEngine ability family (each family is one typed C++ "
                     "handler); written in IR from the card text, then compared with the engine declaration. All 125 "
                     "declarations are additionally classified by a construct-mapping table (census, not a sample)"),
            "cards": engine_validation_set(),
        },
        "metrics": {
            "expressibility": ("per card FULL (complete, no open unknown) / FULL_DEP (complete structure, correctness "
                               "depends on a typed external dependency such as pool membership) / PARTIAL (a text span "
                               "is unexpressed or its reading is unresolved) / UNSUPPORTED; every unexpressed span listed"),
            "vocabulary": ("elements = op, selector, predicate, value, condition, event, duration, keyword rule, extension; "
                           "new elements per card in authoring order, mean over permutations, singletons"),
            "unique_primitive_cards": "cards that use at least one element no other card in the pilot uses",
            "extensions": "card- or mechanic-specific elements, counted apart from generic primitives",
            "unknowns": "typed external dependencies and unresolved rules per card",
            "manual_decisions": "interpretation decisions recorded per card, with their basis",
            "engine_translation": "ManaEngine validation declarations expressible in IR v0 without loss; constructs that needed C++ semantics",
        },
        "criteria": {
            "alarm": ["> 40% of sampled cards need a card-unique primitive",
                      "vocabulary growth is roughly linear: permutation-mean new elements per card in the last third "
                      ">= 0.75 x the first third"],
            "positive": ["FULL + FULL_DEP >= 75% of sampled cards, with no hidden simplification",
                         "<= 25% of sampled cards need a card-unique primitive that is not a reusable mechanic rule",
                         "permutation-mean new elements per card in the last third < 0.5 x the first third",
                         ">= 90% of the ManaEngine family representatives translate without loss"],
            "uniqueness_scope": ("an element is unique if no other card of pilot + engine validation uses it; reuse "
                                 "potential of singletons is screened by a text signature over the frame (heuristic)"),
            "not_a_claim": "stage A cannot establish compiler accuracy, false-acceptance rate or execution correctness",
        },
    }
    payload = json.dumps(protocol, ensure_ascii=False, indent=2) + "\n"
    args.output.write_bytes(payload.encode("utf-8"))
    print(f"curated {len(curated)}, random {len(drawn)} from frame {len(frame)} {allocation}; "
          f"engine validation {len(protocol['engine_validation']['cards'])}")


if __name__ == "__main__":
    main()
