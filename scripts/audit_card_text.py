"""Read-only audit of card rule text in the pinned Standard catalog (CARD-TEXT-AUDIT-1).

Measures how usable the existing ``text`` field is for a future Text/Hybrid Policy. Nothing here is a
text encoder: the normalisation below is an analysis probe so that duplicates and keywords can be
counted, and it is not a recommendation for the production pipeline. No network, no model, no writes
except the optional ``--output`` JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/cards/standard_current_enUS.json"
SNAPSHOT = ROOT / "data/cards/source_snapshots/cards_collectible_20261001_enUS.json"

# Keyword phrase (lower case) -> structured ``mechanics`` tag that should accompany an intrinsic keyword.
KEYWORD_TAGS = {
    "battlecry": "BATTLECRY", "deathrattle": "DEATHRATTLE", "taunt": "TAUNT", "discover": "DISCOVER",
    "rush": "RUSH", "lifesteal": "LIFESTEAL", "divine shield": "DIVINE_SHIELD", "stealth": "STEALTH",
    "reborn": "REBORN", "elusive": "ELUSIVE", "combo": "COMBO", "quest": "QUEST", "secret": "SECRET",
    "overload": "OVERLOAD", "poisonous": "POISONOUS", "tradeable": "TRADEABLE", "outcast": "OUTCAST",
    "windfury": "WINDFURY", "charge": "CHARGE", "choose one": "CHOOSE_ONE", "colossal": "COLOSSAL",
    "spell damage": "SPELLPOWER", "start of game": "START_OF_GAME_KEYWORD",
}
# Keywords that appear in text but have no counterpart in ``mechanics`` at all in this snapshot.
TEXT_ONLY_KEYWORDS = ("kindred", "imbue", "herald", "rewind", "prepare", "dormant", "dark gift", "fabled",
                      "shatter", "corpse", "reward", "titan", "counter")
# Coarse surface patterns only: counts of wording, not a rules taxonomy and not evidence of any implementation.
EFFECT_PHRASES = {
    "deal_damage": r"\bdeal(s)? [$#]?\{?\d*\}? ?damage|\bdeal damage", "restore_health": r"\brestore", "draw": r"\bdraw",
    "summon": r"\bsummon", "get_or_add_card": r"\b(get|add) (a|an|two|three|\d|random)", "discover": r"\bdiscover",
    "random": r"\brandom", "give_stats": r"[+-]\d+(/[+-]\d+| attack| health)", "destroy": r"\bdestroy",
    "cost_change": r"\bcosts? \(\d+\) (less|more)|\bcosts? \(\d+\)|reduce the cost|\bcosts? (less|more)", "transform": r"\btransform",
    "copy": r"\bcop(y|ies)", "shuffle": r"\bshuffle", "conditional_if": r"\bif\b", "for_each": r"for each",
    "this_game_history": r"this game|this turn|have died|you've (played|cast)|you played|you cast", "trigger_whenever_after": r"\b(whenever|after you|after this|after a|after your)\b",
    "start_end_of_turn": r"(start|end) of (your|each|the) turn", "choose_option": r"\bchoose\b", "while_or_has_aura": r"\bwhile\b|\bhas\b|\ball (friendly|enemy)",
    "quoted_granted_text": r"[\"']\w[^\"']*:", "opponent_deck_or_hand": r"opponent'?s? (hand|deck)|enemy deck", "mana_crystals": r"mana crystal",
}
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
CURLY = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def flat(text: str) -> str:
    """Analysis-only normal form: no markup, no layout, ASCII quotes, one space between words."""
    text = text.replace("[x]", "")
    text = TAG_RE.sub("", text)
    for src, dst in CURLY.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def variants(text: str) -> list[str]:
    """Split on the '@' (and the lone '1' used by three FIR_ cards) variant separators."""
    return text.split("@") if "@" in text else re.split(r"(?<=</i>)1(?=[A-Z])", text)


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", flat(text).lower())


def shingles(tokens: list[str]) -> frozenset:
    n = 3 if len(tokens) >= 3 else 1
    return frozenset(tuple(tokens[i:i + n]) for i in range(max(1, len(tokens) - n + 1)))


def percentiles(values: list[int]) -> dict:
    values = sorted(values)
    pick = lambda q: values[min(len(values) - 1, int(q * len(values)))]  # noqa: E731
    return {"min": values[0], "p50": pick(.5), "p90": pick(.9), "p99": pick(.99), "max": values[-1]}


def audit(catalog_path: Path, snapshot_path: Path) -> dict:
    catalog = load(catalog_path)
    cards = catalog["cards"]
    snapshot = load(snapshot_path)
    snap_by_id = {c["id"]: c for c in snapshot}
    out: dict = {}

    out["source"] = {
        "catalog": str(catalog_path.relative_to(ROOT)).replace("\\", "/"), "profile_id": catalog["profile_id"],
        "valid_as_of": catalog["valid_as_of"], "declared_source_sha256": catalog["source_sha256"],
        "snapshot_sha256_raw_bytes": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "snapshot_sha256_crlf_normalised": hashlib.sha256(snapshot_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "snapshot_cards": len(snapshot),
    }
    out["source"]["declared_hash_matches_snapshot_file"] = (
        catalog["source_sha256"] in (out["source"]["snapshot_sha256_raw_bytes"], out["source"]["snapshot_sha256_crlf_normalised"]))

    ids = [c["id"] for c in cards]
    out["identity"] = {
        "cards": len(cards), "unique_ids": len(set(ids)), "unique_dbf_ids": len({c["dbfId"] for c in cards}),
        "unique_names": len({c["name"] for c in cards}),
        "records_identical_to_snapshot": sum(snap_by_id.get(c["id"]) == c for c in cards),
        "id_prefix_counts": dict(Counter(i.split("_")[0] for i in ids).most_common()),
        "mixed_case_core_prefixes": sorted({i.split("_")[0] for i in ids if i.lower().startswith("core")}),
        "ids_not_matching_ascii_pattern": [i for i in ids if not re.fullmatch(r"[A-Za-z0-9_]+", i)],
        "field_presence": dict(Counter(k for c in cards for k in c).most_common()),
        "missing_card_class_but_has_classes": sorted(c["id"] for c in cards if "cardClass" not in c and "classes" in c),
    }

    # Coverage ---------------------------------------------------------------------------------
    by_type: dict = defaultdict(lambda: {"cards": 0, "with_text": 0})
    for c in cards:
        by_type[c["type"]]["cards"] += 1
        by_type[c["type"]]["with_text"] += bool(c.get("text"))
    no_text = [c for c in cards if not c.get("text")]
    out["coverage"] = {
        "with_text": len(cards) - len(no_text), "without_text": len(no_text),
        "by_type": dict(by_type),
        "without_text_cards": [{"id": c["id"], "name": c["name"], "type": c["type"], "cost": c["cost"],
                                "attack": c.get("attack"), "health": c.get("health"), "has_mechanics": bool(c.get("mechanics")),
                                "race": c.get("race"), "set": c["set"]} for c in no_text],
        "text_equals_flavor": sum(c.get("text") == c.get("flavor") for c in cards),
        "cards_with_collectionText": sorted(c["id"] for c in cards if "collectionText" in c),
        "cards_with_targetingArrowText": len([c for c in cards if "targetingArrowText" in c]),
        "cards_with_howToEarn": len([c for c in cards if "howToEarn" in c]),
        "no_mechanics_but_text": sum(1 for c in cards if c.get("text") and not c.get("mechanics")),
    }

    # Markup and characters --------------------------------------------------------------------
    texts = {c["id"]: c.get("text", "") for c in cards}
    patterns = {
        "bold_tag": r"<b>", "italic_tag": r"<i>", "any_tag": TAG_RE.pattern, "x_marker": r"^\[x\]", "newline": r"\n",
        "nbsp": "\xa0", "spell_damage_marker_$N": r"\$\{?\d", "healing_marker_#N": r"#\{?\d", "paren_number": r"\(\d+\)",
        "brace_placeholder": r"\{\d\}", "at_variant_separator": "@", "pipe_plural_syntax": r"\|\d\(",
        "nested_bold": r"<b>[^<]*<b>", "uppercase_tag": r"</?[BI]>", "curly_quote": "[\u2018\u2019\u201c\u201d]",
        "double_quote": '"', "ascii_apostrophe": "'",
    }
    out["markup_cards_with"] = {k: sum(bool(re.search(p, t)) for t in texts.values()) for k, p in patterns.items()}
    out["markup_examples"] = {k: [i for i, t in texts.items() if re.search(patterns[k], t)][:8]
                              for k in ("uppercase_tag", "nested_bold", "curly_quote", "brace_placeholder", "pipe_plural_syntax")}
    unbalanced = [i for i, t in texts.items()
                  if len(re.findall(r"<b>", t)) != len(re.findall(r"</b>", t)) or len(re.findall(r"<i>", t)) != len(re.findall(r"</[iI]>", t))]
    out["unbalanced_tags"] = unbalanced
    out["tag_inventory"] = dict(Counter(m for t in texts.values() for m in TAG_RE.findall(t)))
    out["nonascii_chars"] = {field: {f"U+{ord(ch):04X}": n for ch, n in Counter(
        ch for c in cards for ch in str(c.get(field, "")) if ord(ch) > 127).items()} for field in ("text", "name", "flavor")}
    out["control_chars_other_than_newline"] = sum(1 for t in texts.values() for ch in t if ord(ch) < 32 and ch != "\n")
    out["placeholder_inventory"] = dict(Counter(re.findall(r"\$\{?\d+\}?|#\{?\d+\}?|\{\d\}|\(\d+\)|\|\d\([^)]*\)", " ".join(texts.values()))).most_common(40))

    # Layout: are newlines semantic? ------------------------------------------------------------
    wraps = Counter()
    for t in texts.values():
        for m in re.finditer(r"(.)\n\xa0*(.)", t):
            prev, nxt = m.groups()
            wraps["after_sentence_or_tag_end" if prev in ".:!?)>" else "mid_phrase"] += 1
    x_texts = [t for t in texts.values() if t.startswith("[x]")]
    plain = [t for t in texts.values() if t and not t.startswith("[x]")]
    out["layout"] = {"x_marked_cards": len(x_texts), "plain_cards": len(plain), "plain_with_newline": sum("\n" in t for t in plain),
                     "newline_context": dict(wraps), "cards_with_nbsp_runs": sum(bool(re.search("\xa0", t)) for t in texts.values()),
                     "max_nbsp_run": max((len(m) for t in texts.values() for m in re.findall("\xa0+", t)), default=0)}

    # Variant strings --------------------------------------------------------------------------
    by_id_early = {c["id"]: c for c in cards}
    var_cards = {i: variants(t) for i, t in texts.items() if "@" in t or re.search(r"</i>1[A-Z]", t)}
    out["variants"] = {
        "cards": len(var_cards),
        "separator_at": sorted(i for i in var_cards if "@" in texts[i]),
        "separator_literal_1": sorted(i for i in var_cards if "@" not in texts[i]),
        "segment_shapes": {i: [len(flat(v)) for v in vs] for i, vs in var_cards.items()},
        "fragment_style_cards": sorted(i for i, vs in var_cards.items() if min(len(flat(v)) for v in vs[1:]) < 20),
        "collection_text_cards": len(out["coverage"]["cards_with_collectionText"]),
        "collection_text_equals_first_segment": sorted(i for i in out["coverage"]["cards_with_collectionText"]
                                                       if by_id_early[i]["collectionText"] == texts[i].split("@")[0]),
        "collection_text_differs_from_text": sorted(i for i in out["coverage"]["cards_with_collectionText"]
                                                    if by_id_early[i]["collectionText"] not in texts[i]),
        "display_text_not_equal_collectionText": sorted(i for i in var_cards if i in out["coverage"]["cards_with_collectionText"]
                                                          and next(c for c in cards if c["id"] == i)["collectionText"] not in texts[i]),
    }

    # Keywords vs mechanics --------------------------------------------------------------------
    def bold_text(t: str) -> str:
        return " ".join(flat(b).lower() for b in re.findall(r"<b>(.*?)</b>", t, flags=re.S))
    tag_without_word, bold_word_without_tag = defaultdict(list), defaultdict(list)
    for c in cards:
        t, mech = texts[c["id"]], set(c.get("mechanics", []))
        plain_text, bold = flat(t).lower(), bold_text(t)
        for phrase, tag in KEYWORD_TAGS.items():
            if tag in mech and phrase not in plain_text:
                tag_without_word[tag].append(c["id"])
            if tag not in mech and phrase in bold:
                bold_word_without_tag[tag].append(c["id"])
    bold_counts = Counter(flat(b) for t in texts.values() for b in re.findall(r"<b>(.*?)</b>", t, flags=re.S))
    out["keywords"] = {
        "mechanics_tag_counts": dict(Counter(m for c in cards for m in c.get("mechanics", [])).most_common()),
        "referenced_tag_counts": dict(Counter(m for c in cards for m in c.get("referencedTags", [])).most_common()),
        "distinct_bold_phrases": len(bold_counts), "top_bold_phrases": dict(bold_counts.most_common(40)),
        "tag_present_keyword_absent_in_text": {k: v for k, v in tag_without_word.items()},
        "bold_keyword_in_text_without_tag": {k: len(v) for k, v in sorted(bold_word_without_tag.items())},
        "text_only_keywords": {k: sum(k in flat(t).lower() for t in texts.values()) for k in TEXT_ONLY_KEYWORDS},
        "trigger_visual_cards": sum("TRIGGER_VISUAL" in c.get("mechanics", []) for c in cards),
        "cards_with_text_and_no_mechanics_but_keyword_phrase": sum(
            1 for c in cards if not c.get("mechanics") and re.search(r"<b>(Battlecry|Deathrattle|Discover)", texts[c["id"]])),
    }

    out["keywords"]["cards_with_any_text_only_keyword"] = sum(
        any(k in flat(texts[c["id"]]).lower() for k in TEXT_ONLY_KEYWORDS) for c in cards)
    out["effect_phrases_cards_matching"] = {name: sum(bool(re.search(pattern, flat(t), re.I)) for t in texts.values()) for name, pattern in EFFECT_PHRASES.items()}
    leading = [(c, m.group(1).strip()) for c in cards if c["type"] == "MINION" and (
        m := re.match(r"^(?:\[x\])?(?:<b>)+\s*([A-Za-z ]+?)[:.,]?</b>", texts[c["id"]]))]
    out["keywords"]["leading_keyword_minions"] = sum(kw.lower() in KEYWORD_TAGS for _, kw in leading)
    out["keywords"]["leading_keyword_minions_missing_tag"] = sorted(
        c["id"] for c, kw in leading if kw.lower() in KEYWORD_TAGS and KEYWORD_TAGS[kw.lower()] not in c.get("mechanics", []))

    # Duplicates and near-duplicates ------------------------------------------------------------
    flat_text = {i: flat(t) for i, t in texts.items() if t}
    exact: dict = defaultdict(list)
    for i, f in flat_text.items():
        exact[f].append(i)
    dup_groups = [g for g in exact.values() if len(g) > 1]
    masked: dict = defaultdict(list)
    for i, f in flat_text.items():
        masked[re.sub(r"\d+", "N", f)].append(i)
    masked_groups = [g for g in masked.values() if len(g) > 1]
    by_id = {c["id"]: c for c in cards}
    functional: dict = defaultdict(list)
    for i, f in flat_text.items():
        c = by_id[i]
        functional[(f, c["type"], c["cost"], c.get("attack"), c.get("health"), c.get("durability"))].append(i)
    functional_groups = [g for g in functional.values() if len(g) > 1]
    shingle = {i: shingles(words(texts[i])) for i in flat_text}
    best: dict = {}
    keys = sorted(shingle)
    for a_index, a in enumerate(keys):
        for b in keys[a_index + 1:]:
            inter = len(shingle[a] & shingle[b])
            if not inter:
                continue
            sim = inter / len(shingle[a] | shingle[b])
            for x, y in ((a, b), (b, a)):
                if sim > best.get(x, (0, ""))[0]:
                    best[x] = (sim, y)
    near = lambda lo: sum(1 for v in best.values() if lo <= v[0] < 1.0)  # noqa: E731
    out["duplicates"] = {
        "cards_with_text": len(flat_text), "distinct_flat_texts": len(exact),
        "exact_duplicate_groups": len(dup_groups), "cards_in_exact_duplicate_groups": sum(map(len, dup_groups)),
        "exact_duplicate_groups_detail": [{"text": flat_text[g[0]][:120], "ids": g} for g in dup_groups],
        "digit_masked_duplicate_groups": len(masked_groups), "cards_in_digit_masked_groups": sum(map(len, masked_groups)),
        "functional_duplicate_groups_same_text_type_cost_stats": len(functional_groups),
        "functional_duplicate_detail": [g for g in functional_groups],
        "nearest_other_card_trigram_jaccard": {"ge_0.9_not_exact": near(.9), "0.7_to_0.9": near(.7) - near(.9),
                                               "0.5_to_0.7": near(.5) - near(.7), "median": sorted(v[0] for v in best.values())[len(best) // 2]},
        "near_duplicate_pairs_ge_0.7": sorted(({"a": a, "b": v[1], "sim": round(v[0], 3)} for a, v in best.items() if .7 <= v[0] < 1 and a < v[1]),
                                              key=lambda r: -r["sim"])[:25],
    }

    # Identity leakage: words / names that reveal the card -------------------------------------
    token_sets = {i: set(words(texts[i])) for i in flat_text}
    df = Counter(w for s in token_sets.values() for w in s)
    own_name = [i for i in flat_text if re.search(r"\b" + re.escape(by_id[i]["name"].lower()) + r"\b", flat_text[i].lower())]
    out["identity_leakage"] = {
        "vocabulary_size": len(df), "tokens_in_exactly_one_card": sum(n == 1 for n in df.values()),
        "cards_with_a_token_unique_to_them": sum(any(df[w] == 1 for w in s) for s in token_sets.values()),
        "cards_with_a_token_in_le_2_cards": sum(any(df[w] <= 2 for w in s) for s in token_sets.values()),
        "unique_token_examples": sorted(w for w, n in df.items() if n == 1)[:25],
        "texts_that_contain_own_name": own_name,
        "texts_naming_another_catalog_card": sum(
            any(o != i and len(by_id[o]["name"]) >= 8 and by_id[o]["name"].lower() in flat_text[i].lower() for o in by_id) for i in flat_text),
    }

    # Length -----------------------------------------------------------------------------------
    out["length"] = {
        "words_per_card": percentiles([len(words(texts[i])) for i in flat_text]),
        "chars_per_card_raw": percentiles([len(t) for t in texts.values() if t]),
        "chars_per_card_flat": percentiles([len(f) for f in flat_text.values()]),
        "words_by_type_median": {ty: sorted(len(words(texts[i])) for i in flat_text if by_id[i]["type"] == ty)[sum(by_id[i]["type"] == ty for i in flat_text) // 2]
                                 for ty in sorted({c["type"] for c in cards})},
    }

    # Snapshot-wide context for unseen-card designs ---------------------------------------------
    catalog_ids = set(ids)
    out["snapshot_outside_standard"] = {"cards": len(snapshot) - len(catalog_ids & set(snap_by_id)),
                                         "with_text": sum(1 for c in snapshot if c["id"] not in catalog_ids and c.get("text"))}
    standard_flat = set(flat_text.values())
    out["snapshot_outside_standard"]["with_text_identical_to_a_standard_card"] = sum(
        1 for c in snapshot if c["id"] not in catalog_ids and c.get("text") and flat(c["text"]) in standard_flat)

    def full_key(c: dict) -> tuple:
        return (flat(c.get("text", "")), c["type"], c["cost"], c.get("attack"), c.get("health"), c.get("durability"), c.get("cardClass"))
    standard_keys = {full_key(c) for c in cards}
    out["snapshot_outside_standard"]["functional_twin_of_a_standard_card_same_text_type_cost_stats_class"] = sum(
        1 for c in snapshot if c["id"] not in catalog_ids and c.get("text") and full_key(c) in standard_keys)
    names = Counter(c["name"] for c in snapshot)
    out["snapshot_outside_standard"]["standard_core_cards_whose_name_is_shared_by_another_snapshot_id"] = sum(
        1 for c in cards if c["id"].lower().startswith("core_") and names[c["name"]] > 1)
    return out


def _walk_card_ids(node: object, path: str, sink: list) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("card_id"), str):
            sink.append((path, node["card_id"]))
        for key, value in node.items():
            if key != "card_id":
                _walk_card_ids(value, f"{path}/{key}", sink)
    elif isinstance(node, list):
        for value in node:
            _walk_card_ids(value, path + "[]", sink)


def real_data_coverage(real_dir: Path, catalog_path: Path, snapshot_path: Path) -> dict:
    """Count how often card IDs in local real-state JSONL rows have rule text (IDs and zone paths only)."""
    standard = {c["id"] for c in load(catalog_path)["cards"]}
    collectible = {c["id"]: c for c in load(snapshot_path)}

    def bucket(card_id: str) -> str:
        if card_id in standard:
            return "standard_catalog"
        if card_id in collectible:
            return "collectible_snapshot_only"
        return "absent_from_pinned_data"
    by_zone: dict = defaultdict(Counter)
    ids_by_bucket: dict = defaultdict(set)
    files = sorted(real_dir.glob("*.jsonl"))
    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                found: list = []
                _walk_card_ids(json.loads(line).get("state", {}), "state", found)
                for zone, card_id in found:
                    by_zone[zone][bucket(card_id)] += 1
                    ids_by_bucket[bucket(card_id)].add(card_id)
    return {"files": len(files), "distinct_ids_by_bucket": {k: len(v) for k, v in sorted(ids_by_bucket.items())},
            "occurrences_by_zone_and_bucket": {k: dict(v) for k, v in sorted(by_zone.items())},
            "absent_ids_sample": sorted(ids_by_bucket["absent_from_pinned_data"])[:30],
            "snapshot_only_ids_with_text": sorted(i for i in ids_by_bucket["collectible_snapshot_only"] if collectible[i].get("text")),
            "note": "card_id occurrences in state rows (repeated across positions of a game), not unique decisions."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--real-dir", type=Path, help="optional ignored data/processed_real directory; only card_id counts are read")
    parser.add_argument("--output", type=Path, help="write the summary JSON here (never overwrites an existing file)")
    args = parser.parse_args()
    summary = audit(args.catalog, args.snapshot)
    if args.real_dir:
        summary["real_data_card_id_coverage"] = real_data_coverage(args.real_dir, args.catalog, args.snapshot)
    text = json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"Refusing to overwrite {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
