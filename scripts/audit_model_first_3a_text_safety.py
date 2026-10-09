"""Read-only audit of text duplicates, split overlap, and state text coverage."""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from manamind.research.card_text_features import (  # noqa: E402
    FEATURE_SCHEMA_VERSION, CardTextAdapter, _terms,
)


def _functional_signature(card: dict, normalized: str) -> tuple:
    return (normalized, card.get("type"), card.get("cost"), card.get("attack"), card.get("health"),
            card.get("cardClass"), tuple(sorted(card.get("mechanics") or [])))


def _trigrams(text: str) -> set[tuple[str, ...]]:
    terms = _terms(text)
    return {tuple(terms[index:index + 3]) for index in range(max(0, len(terms) - 2))}


def _numeric_template(text: str) -> str:
    """Diagnostic-only digit masking; preserves $, #, parentheses, sign and slash."""
    return re.sub(r"\d+", "<NUM>", text)


def _walk_card_records(state: dict):
    occurrences = []

    def walk(value, parent=None):
        if isinstance(value, dict):
            card_id = value.get("card_id")
            if isinstance(card_id, str):
                base_fields = {key for key in ("cost", "attack", "health") if value.get(key) is not None}
                current_source = parent if isinstance(parent, dict) else value
                current_fields = {key for key in ("current_cost", "current_attack", "current_health",
                                                   "current_durability", "current_spell_damage")
                                  if current_source.get(key) is not None}
                occurrences.append({"card_id": card_id, "base_fields": base_fields,
                                    "current_fields": current_fields})
            for key, item in value.items():
                walk(item, value)
        elif isinstance(value, list):
            for item in value:
                walk(item, parent)

    walk(state)
    return occurrences


def _load_rows(dataset: Path) -> list[dict]:
    from manamind.training.real_policy import load_examples
    return load_examples(dataset)


def audit(catalog_path: Path, *, dataset: Path | None = None,
          split_manifest: Path | None = None, near_threshold: float = 0.7,
          max_pairs: int = 100) -> dict:
    if (dataset is None) != (split_manifest is None):
        raise ValueError("Existing dataset and frozen split manifest must be supplied together")
    adapter = CardTextAdapter(catalog_path)
    usable_ids = {card_id for card_id in adapter.cards if adapter.text_usable[card_id]}
    present_ids = {card_id for card_id in adapter.cards if adapter.text_present[card_id]}
    exact_groups: dict[str, list[str]] = defaultdict(list)
    functional_groups: dict[tuple, list[str]] = defaultdict(list)
    for card_id, card in adapter.cards.items():
        status = adapter.text_status[card_id]
        if not status["text_usable"]:
            continue
        normalized = status["normalized_text"]
        exact_groups[normalized].append(card_id)
        functional_groups[_functional_signature(card, normalized)].append(card_id)
    exact_duplicates = [{"ids": sorted(ids), "normalized_text": normalized}
                        for normalized, ids in sorted(exact_groups.items()) if len(ids) > 1]
    functional_twins = [{"ids": sorted(ids), "signature": {
        "normalized_text": signature[0], "type": signature[1], "cost": signature[2],
        "attack": signature[3], "health": signature[4], "cardClass": signature[5],
        "mechanics": list(signature[6])}}
        for signature, ids in sorted(functional_groups.items(), key=lambda item: repr(item[0])) if len(ids) > 1]

    split_audit = {"provided": dataset is not None, "split_created": False,
                   "functional_twins_between_train_and_test": [],
                   "near_text_template_overlaps_between_train_and_test": [],
                   "number_masked_template_overlaps_between_train_and_test": [],
                   "identical_normalized_text_ids_between_train_and_test": []}
    real_coverage = None
    if dataset is not None and split_manifest is not None:
        rows = _load_rows(dataset)
        manifest = json.loads(split_manifest.read_text(encoding="utf-8"))
        split = manifest.get("split", manifest).get("game_ids", {})
        train_games, test_games = set(split.get("train", [])), set(split.get("test", []))
        if not train_games or not test_games or train_games & test_games:
            raise ValueError("Expected an existing nonempty, disjoint train/test match manifest")
        train_ids: set[str] = set()
        test_ids: set[str] = set()
        state_occurrences = Counter()
        coverage_by_id: dict[str, Counter] = defaultdict(Counter)
        for row in rows:
            target = train_ids if row["game_id"] in train_games else test_ids if row["game_id"] in test_games else None
            if target is not None:
                target.update(o["card_id"] for o in _walk_card_records(row["state"]))
            for occurrence in _walk_card_records(row["state"]):
                card_id = occurrence["card_id"]
                state_occurrences[card_id] += 1
                stats = coverage_by_id[card_id]
                stats["state_occurrences"] += 1
                stats["records_with_base_metadata"] += bool(occurrence["base_fields"])
                stats["base_fields_present"] += len(occurrence["base_fields"])
                stats["records_with_current_instance_values"] += bool(occurrence["current_fields"])
                stats["current_fields_present"] += len(occurrence["current_fields"])

        train_known = train_ids & usable_ids
        test_known = test_ids & usable_ids
        by_text_train: dict[str, list[str]] = defaultdict(list)
        for card_id in train_known:
            by_text_train[adapter.text_status[card_id]["normalized_text"]].append(card_id)
        for test_id in sorted(test_known):
            normalized = adapter.text_status[test_id]["normalized_text"]
            for train_id in by_text_train.get(normalized, []):
                if train_id != test_id:
                    split_audit["identical_normalized_text_ids_between_train_and_test"].append(
                        {"train_id": train_id, "test_id": test_id, "normalized_text": normalized})
            card = adapter.cards[test_id]
            signature = _functional_signature(card, normalized)
            twins = [train_id for train_id in by_text_train.get(normalized, []) if train_id != test_id
                     and _functional_signature(adapter.cards[train_id], normalized) == signature]
            for train_id in twins:
                split_audit["functional_twins_between_train_and_test"].append(
                    {"train_id": train_id, "test_id": test_id})

        train_texts = {card_id: adapter.text_status[card_id]["normalized_text"] for card_id in train_known}
        test_texts = {card_id: adapter.text_status[card_id]["normalized_text"] for card_id in test_known}
        train_templates: dict[str, list[str]] = defaultdict(list)
        for card_id, text in train_texts.items():
            train_templates[_numeric_template(text)].append(card_id)
        number_template_pairs = []
        for test_id, text in sorted(test_texts.items()):
            template = _numeric_template(text)
            for train_id in train_templates.get(template, []):
                if train_id != test_id and train_texts[train_id] != text:
                    number_template_pairs.append({"train_id": train_id, "test_id": test_id,
                        "number_masked_template": template})
        split_audit["number_masked_template_overlaps_between_train_and_test"] = number_template_pairs
        near_pairs = []
        for train_id, test_id in itertools.product(sorted(train_texts), sorted(test_texts)):
            if train_id == test_id:
                continue
            left = _trigrams(train_texts[train_id]); right = _trigrams(test_texts[test_id])
            union = left | right
            similarity = len(left & right) / len(union) if union else float(train_texts[train_id] == test_texts[test_id])
            if similarity >= near_threshold:
                near_pairs.append({"train_id": train_id, "test_id": test_id, "trigram_jaccard": round(similarity, 4)})
        split_audit["near_text_template_overlaps_between_train_and_test"] = sorted(
            near_pairs, key=lambda item: (-item["trigram_jaccard"], item["train_id"], item["test_id"]))[:max_pairs]
        split_audit["near_pair_count_at_threshold"] = len(near_pairs)
        split_audit["threshold"] = near_threshold
        split_audit["train_ids"] = len(train_ids)
        split_audit["test_ids"] = len(test_ids)
        split_audit["note"] = "Inspects the supplied frozen split only; similarity is a candidate report, not a universal semantic detector."

        known_state_ids = {card_id for card_id in state_occurrences if card_id in adapter.cards}
        unknown_state_ids = set(state_occurrences) - set(adapter.cards)
        known_missing_text = {card_id for card_id in known_state_ids if not adapter.text_present[card_id]}
        known_masked_text = {card_id for card_id in known_state_ids if not adapter.text_usable[card_id]}
        real_coverage = {
            "distinct_state_ids": len(state_occurrences),
            "state_occurrences": sum(state_occurrences.values()),
            "known_catalog": {"distinct_ids": len(known_state_ids),
                "state_occurrences": sum(state_occurrences[c] for c in known_state_ids),
                "text_present_ids": len(known_state_ids & present_ids),
                "text_usable_ids": len(known_state_ids & usable_ids),
                "text_missing_ids": len(known_missing_text),
                "warning_or_missing_mask_ids": len(known_masked_text),
                "ids_missing_text": sorted(known_missing_text)},
            "unknown_to_catalog": {"distinct_ids": len(unknown_state_ids),
                "state_occurrences": sum(state_occurrences[c] for c in unknown_state_ids),
                "text_present_ids": 0, "text_usable_ids": 0,
                "warning_or_missing_mask_ids": len(unknown_state_ids),
                "base_metadata_records": sum(coverage_by_id[c]["records_with_base_metadata"] for c in unknown_state_ids),
                "instance_value_records": sum(coverage_by_id[c]["records_with_current_instance_values"] for c in unknown_state_ids)},
            "metadata_presence_by_knownness": {
                "known_base_metadata_records": sum(coverage_by_id[c]["records_with_base_metadata"] for c in known_state_ids),
                "known_instance_value_records": sum(coverage_by_id[c]["records_with_current_instance_values"] for c in known_state_ids),
                "unknown_base_metadata_records": sum(coverage_by_id[c]["records_with_base_metadata"] for c in unknown_state_ids),
                "unknown_instance_value_records": sum(coverage_by_id[c]["records_with_current_instance_values"] for c in unknown_state_ids)},
            "metadata_presence_rates_by_knownness": {
                "known_base_metadata_records": (sum(coverage_by_id[c]["records_with_base_metadata"] for c in known_state_ids)
                                                 / max(1, sum(state_occurrences[c] for c in known_state_ids))),
                "known_instance_value_records": (sum(coverage_by_id[c]["records_with_current_instance_values"] for c in known_state_ids)
                                                  / max(1, sum(state_occurrences[c] for c in known_state_ids))),
                "unknown_base_metadata_records": (sum(coverage_by_id[c]["records_with_base_metadata"] for c in unknown_state_ids)
                                                   / max(1, sum(state_occurrences[c] for c in unknown_state_ids))),
                "unknown_instance_value_records": (sum(coverage_by_id[c]["records_with_current_instance_values"] for c in unknown_state_ids)
                                                    / max(1, sum(state_occurrences[c] for c in unknown_state_ids)))},
            "known_unknown_coverage_differs": bool(unknown_state_ids) and bool(known_state_ids)}

    return {"schema_version": 1, "text_feature_schema_version": FEATURE_SCHEMA_VERSION,
            "source": {"catalog_sha256": adapter.catalog_sha256,
                       "catalog_profile": json.loads(Path(catalog_path).read_text(encoding="utf-8")).get("profile_id"),
                       "normalization_config_sha256": adapter.config_sha256},
            "text_coverage": {"catalog_cards": len(adapter.cards), "text_present": len(present_ids),
                "text_usable_full_features": len(usable_ids),
                "warning_or_missing_mask": len(adapter.cards) - len(usable_ids),
                "missing_text": sum(not status["text_present"] for status in adapter.text_status.values()),
                "with_normalization_warnings": sum(bool(status["normalization_warnings"])
                    and status["text_present"] for status in adapter.text_status.values()),
                "warning_counts": dict(sorted(Counter(warning for status in adapter.text_status.values()
                    for warning in status["normalization_warnings"]).items()))},
            "exact_text_duplicates_different_ids": exact_duplicates,
            "functional_twins_catalog": functional_twins,
            "split_overlap": split_audit,
            "real_state_coverage": real_coverage,
            "limitations": ["Bold/italic markers preserve formatting only; no mechanics are inferred from emphasis.",
                "Ambiguous variants, placeholders, unsupported markup and special separators mask the entire text.",
                "Text similarity thresholds find candidates only and cannot prove all semantic duplicates."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/cards/standard_current_enUS.json")
    parser.add_argument("--dataset", type=Path, help="Existing policy-observation dataset; read only")
    parser.add_argument("--split-manifest", type=Path, help="Existing frozen split manifest; no split is created")
    parser.add_argument("--near-threshold", type=float, default=0.7)
    parser.add_argument("--max-pairs", type=int, default=100)
    parser.add_argument("--output", type=Path, help="Create a new JSON report; existing file is never overwritten")
    args = parser.parse_args()
    result = audit(args.catalog, dataset=args.dataset, split_manifest=args.split_manifest,
                   near_threshold=args.near_threshold, max_pairs=args.max_pairs)
    rendered = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
