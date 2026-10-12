"""Offline comparison of model-shadow journals: who recommends what, where, and how fast (no game state needed).

Everything here is derived from the journal rows themselves (public descriptors only). Agreement between models is
not quality: no row knows what the player did, and no claim about playing strength is made.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PRIMARY_ROLE = "primary"
BUCKETS = (("1-5", 1, 5), ("6-10", 6, 10), ("11-20", 11, 20), ("21-40", 21, 40), ("41+", 41, 10**6))
MANA_BUCKETS = (("0-1", 0, 1), ("2", 2, 2), ("3-4", 3, 4), ("5+", 5, 99))
EVENTS = ("MODEL_SHADOW", "MODEL_SHADOW_ERROR", "MODEL_SHADOW_DISCARDED", "MODEL_SHADOW_INVALIDATION")


def read_journal(paths) -> list[dict]:
    rows = []
    for path in sorted(Path(p) for p in paths):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def action_root(action: dict) -> tuple:
    return (action["type"], action.get("hand_index"), action.get("card_id"), action.get("source_card_id"),
            action.get("source_board_position"), action.get("source_is_hero"))


def action_target(action: dict) -> tuple | None:
    if "target_kind" not in action:
        return None
    return (action["target_kind"], action.get("target_side"), action.get("target_board_position"),
            action.get("target_card_id"))


def describe(action: dict) -> str:
    kind = action["type"]
    if kind == "END_TURN":
        return "END_TURN"
    text = f"{kind} {action.get('card_id') or action.get('source_card_id') or '?'}"
    if "target_kind" in action:
        text += f" -> {action.get('target_side')} {action['target_kind']} {action.get('target_card_id') or ''}".rstrip()
    if action.get("play_position"):
        text += f" @{action['play_position']}"
    return text


def _entry(row: dict, name: str) -> dict | None:
    for entry in row["models"]:
        if entry["name"] == name:
            return entry
    return None


def _ok(entry: dict | None) -> bool:
    return entry is not None and entry.get("status") == "OK"


def _top1(entry: dict) -> dict:
    return entry["top3"][0]["action"]


def percentiles(values) -> dict | None:
    if not values:
        return None
    return {"n": len(values), "p50": round(float(np.percentile(values, 50)), 3),
            "p95": round(float(np.percentile(values, 95)), 3), "max": round(float(max(values)), 3)}


def _bucket(size: int) -> str:
    return next(name for name, low, high in BUCKETS if low <= size <= high)


def _share(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def integrity(rows: list[dict], primary_rows: list[dict] | None) -> dict:
    events = Counter(r["event"] for r in rows)
    shadows = [r for r in rows if r["event"] == "MODEL_SHADOW"]
    ids = Counter(r["decision_id"] for r in shadows)
    identities: dict[str, set] = defaultdict(set)
    status: dict[str, Counter] = defaultdict(Counter)
    problems = Counter()
    for row in shadows:
        if len(row["actions"]) != row["menu_size"]:
            problems["actions_len_differs_from_menu_size"] += 1
        input_digests = defaultdict(set)    # models are comparable when they share an input representation
        for entry in row["models"]:
            identities[entry["name"]].add(entry["checkpoint_sha256"])
            status[entry["name"]][entry["status"] + (f":{entry['reason']}" if entry.get("reason") else "")] += 1
            if entry["status"] == "OK":
                if len(entry["ranks"]) != row["menu_size"] or sorted(entry["ranks"]) != list(range(1, row["menu_size"] + 1)):
                    problems["invalid_rank_vector"] += 1
                if entry.get("inputs_sha256"):
                    input_digests[entry.get("input_representation")].add(entry["inputs_sha256"])
        if any(len(v) > 1 for v in input_digests.values()):
            problems["models_saw_different_inputs"] += 1
        primary = row["models"][0]
        if primary["role"] != PRIMARY_ROLE:
            problems["first_entry_not_primary"] += 1
        elif primary.get("reproduced") is not True:
            problems["primary_not_reproduced"] += 1
    checked = mismatched = 0
    if primary_rows is not None:
        shown = {r["decision_id"]: r for r in primary_rows if r.get("event") == "RECOMMENDATION"}
        for row in shadows:
            recommendation = shown.get(row["decision_id"])
            if recommendation is None:
                problems["no_matching_recommendation_row"] += 1
                continue
            checked += 1
            if (recommendation["state_hash"] != row["state_hash"]
                    or recommendation["checkpoint_sha256"] != row["models"][0]["checkpoint_sha256"]
                    or [t["action"] for t in recommendation["top3"]] != [t["action"] for t in row["models"][0]["top3"]]):
                mismatched += 1
    return {
        "rows_by_event": dict(events), "decisions": len(shadows), "matches": len({r["match_id"] for r in shadows}),
        "duplicate_decision_rows": sum(c - 1 for c in ids.values() if c > 1),
        "checkpoint_identities": {n: sorted(v) for n, v in identities.items()},
        "multiple_checkpoint_versions_in_one_journal": sorted(n for n, v in identities.items() if len(v) > 1),
        "status_by_model": {n: dict(c) for n, c in status.items()},
        "displayed_top3_checked_against_prediction_journal": checked if primary_rows is not None else None,
        "displayed_top3_mismatches": mismatched if primary_rows is not None else None,
        "problems": dict(problems)}


def latency(rows: list[dict]) -> dict:
    by_model: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    live, total = [], []
    for row in rows:
        if row["event"] != "MODEL_SHADOW":
            continue
        total.append(row["total_ms"])
        for entry in row["models"]:
            if entry["status"] == "OK" and "inference_ms" in entry:
                by_model[entry["name"]]["all"].append(entry["inference_ms"])
                by_model[entry["name"]][_bucket(row["menu_size"])].append(entry["inference_ms"])
            if entry["role"] == PRIMARY_ROLE:
                live.append(entry["live_latency_ms"])
    order = ["all"] + [name for name, _, _ in BUCKETS]
    return {"model_inference_ms_encode_plus_forward": {
                n: {b: percentiles(v[b]) for b in order if b in v} for n, v in sorted(by_model.items())},
            "primary_live_recommendation_ms": percentiles(live), "shadow_total_ms_per_decision": percentiles(total)}


def _pair_rows(rows, a: str, b: str):
    for row in rows:
        if row["event"] != "MODEL_SHADOW":
            continue
        ea, eb = _entry(row, a), _entry(row, b)
        if _ok(ea) and _ok(eb):
            yield row, ea, eb


def agreement(rows: list[dict], names: list[str]) -> dict:
    out = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            n = same = a_in_b = b_in_a = 0
            jaccard = []
            by_class: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for row, ea, eb in _pair_rows(rows, a, b):
                n += 1
                ta, tb = [t["index"] for t in ea["top3"]], [t["index"] for t in eb["top3"]]
                same += ta[0] == tb[0]
                a_in_b += ta[0] in tb
                b_in_a += tb[0] in ta
                jaccard.append(len(set(ta) & set(tb)) / len(set(ta) | set(tb)))
                by_class[row["self_class"]][0] += 1
                by_class[row["self_class"]][1] += ta[0] == tb[0]
            out[f"{a}|{b}"] = {
                "decisions": n, "top1_agree": _share(same, n), f"{a}_top1_in_{b}_top3": _share(a_in_b, n),
                f"{b}_top1_in_{a}_top3": _share(b_in_a, n),
                "mean_top3_jaccard": round(float(np.mean(jaccard)), 4) if jaccard else None,
                "top1_agree_by_self_class": {c: {"decisions": v[0], "top1_agree": _share(v[1], v[0])}
                                             for c, v in sorted(by_class.items())}}
    return out


def _example(row: dict, entries: dict[str, dict]) -> dict:
    return {"decision_id": row["decision_id"], "turn": row["turn"], "self_class": row["self_class"],
            "opponent_class": row["opponent_class"], "mana": row["mana"], "menu_size": row["menu_size"],
            "top1": {name: describe(_top1(e)) for name, e in entries.items()}}


def categories(rows: list[dict], names: list[str], *, examples: int = 5) -> dict:
    shadows = [r for r in rows if r["event"] == "MODEL_SHADOW"]
    result: dict = {"per_model": {}, "disagreements": {}}

    def face(action):
        return action["type"] == "ATTACK" and action.get("target_kind") == "HERO" and action.get("target_side") == "OPPONENT"

    for name in names:
        ok = [(r, _entry(r, name)) for r in shadows if _ok(_entry(r, name))]
        hp_legal = [(r, e) for r, e in ok if any(a["type"] == "HERO_POWER" for a in r["actions"])]
        by_class = {}
        for klass in sorted({r["self_class"] for r, _ in ok}):
            sub = [(r, e) for r, e in hp_legal if r["self_class"] == klass]
            by_class[klass] = {"hero_power_legal_decisions": len(sub),
                               "top1_hero_power": _share(sum(e["top1_type"] == "HERO_POWER" for _, e in sub), len(sub))}
        dh = [(r, e) for r, e in hp_legal if r["self_class"] == "DEMONHUNTER"]
        dh_mana = {label: {"decisions": len(sub), "top1_hero_power": _share(sum(e["top1_type"] == "HERO_POWER" for _, e in sub), len(sub))}
                   for label, low, high in MANA_BUCKETS
                   for sub in [[(r, e) for r, e in dh if low <= r["mana"] <= high]]}
        lethal = [(r, e) for r, e in ok if r["face_attack_lethal_candidate"]]
        multi = [(r, e) for r, e in ok if r["menu_size"] > 1]
        result["per_model"][name] = {
            "decisions": len(ok), "top1_type_counts": dict(Counter(e["top1_type"] for _, e in ok)),
            "hero_power": {"legal_decisions": len(hp_legal),
                           "top1_share_when_legal": _share(sum(e["top1_type"] == "HERO_POWER" for _, e in hp_legal), len(hp_legal)),
                           "by_self_class": by_class, "demon_hunter_by_available_mana": dh_mana},
            "lethal_candidates": {"decisions": len(lethal),
                                  "top1_face_attack": sum(face(_top1(e)) for _, e in lethal),
                                  "top1_other_attack": sum(_top1(e)["type"] == "ATTACK" and not face(_top1(e)) for _, e in lethal),
                                  "top1_not_attack": sum(_top1(e)["type"] != "ATTACK" for _, e in lethal),
                                  "top1_end_turn": sum(e["top1_type"] == "END_TURN" for _, e in lethal)},
            "end_turn": {"decisions_with_alternatives": len(multi),
                         "top1_end_turn": sum(e["top1_type"] == "END_TURN" for _, e in multi),
                         "top1_end_turn_share": _share(sum(e["top1_type"] == "END_TURN" for _, e in multi), len(multi))}}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            kinds: dict[str, list] = defaultdict(list)
            for row, ea, eb in _pair_rows(shadows, a, b):
                ta, tb = _top1(ea), _top1(eb)
                pair = {a: ea, b: eb}
                if ta["type"] == "HERO_POWER" != tb["type"]:
                    kinds[f"hero_power_only_{a}"].append((row, pair))
                if tb["type"] == "HERO_POWER" != ta["type"]:
                    kinds[f"hero_power_only_{b}"].append((row, pair))
                if action_root(ta) == action_root(tb) and action_target(ta) is not None and action_target(ta) != action_target(tb):
                    kinds["same_source_different_target"].append((row, pair))
                if ta["type"] == "ATTACK" and tb["type"] == "ATTACK" and ta != tb:
                    kinds["both_attack_different_attack"].append((row, pair))
                if (ta["type"] == "ATTACK") != (tb["type"] == "ATTACK"):
                    kinds[f"attack_only_{a if ta['type'] == 'ATTACK' else b}"].append((row, pair))
                if row["face_attack_lethal_candidate"] and ta != tb:
                    kinds["lethal_candidate_different_top1"].append((row, pair))
                if ea["top1_type"] == "END_TURN" and eb["top1_type"] != "END_TURN" and row["menu_size"] > 1:
                    kinds[f"end_turn_only_{a}"].append((row, pair))
                if eb["top1_type"] == "END_TURN" and ea["top1_type"] != "END_TURN" and row["menu_size"] > 1:
                    kinds[f"end_turn_only_{b}"].append((row, pair))
            result["disagreements"][f"{a}|{b}"] = {
                kind: {"count": len(items), "examples": [_example(r, p) for r, p in items[:examples]]}
                for kind, items in sorted(kinds.items())}
    return result


def per_match(rows: list[dict], names: list[str]) -> dict:
    out: dict[str, dict] = {}
    for row in rows:
        if row["event"] != "MODEL_SHADOW":
            continue
        item = out.setdefault(row["match_id"][:8], {"self_class": row["self_class"], "decisions": 0,
                                                    "top1_agree_with_primary": Counter(), "compared": Counter()})
        item["decisions"] += 1
        primary = _entry(row, names[0])
        for name in names[1:]:
            other = _entry(row, name)
            if _ok(primary) and _ok(other):
                item["compared"][name] += 1
                item["top1_agree_with_primary"][name] += primary["top3"][0]["index"] == other["top3"][0]["index"]
    return {m: {"self_class": v["self_class"], "decisions": v["decisions"],
                "top1_agree_with_primary": {n: _share(v["top1_agree_with_primary"][n], v["compared"][n]) for n in v["compared"]}}
            for m, v in sorted(out.items())}


def analyse(rows: list[dict], primary_rows: list[dict] | None = None, *, examples: int = 5) -> dict:
    names: list[str] = []
    for row in rows:
        if row["event"] == "MODEL_SHADOW":
            for entry in row["models"]:
                if entry["name"] not in names:
                    names.append(entry["name"])
    return {"integrity": integrity(rows, primary_rows), "latency": latency(rows), "models": names,
            "agreement": agreement(rows, names), "categories": categories(rows, names, examples=examples),
            "per_match": per_match(rows, names)}


def render(report: dict) -> str:
    """A short human-readable summary of ``analyse`` output."""
    lines = []
    i = report["integrity"]
    lines.append(f"decisions {i['decisions']} in {i['matches']} matches; events {i['rows_by_event']}")
    lines.append(f"problems: {i['problems'] or 'none'}; duplicates {i['duplicate_decision_rows']}; "
                 f"displayed Top-3 mismatches: {i['displayed_top3_mismatches']}")
    for name, status in i["status_by_model"].items():
        lines.append(f"  {name}: {status}")
    for name, table in report["latency"]["model_inference_ms_encode_plus_forward"].items():
        a = table.get("all")
        if a:
            lines.append(f"  {name} inference ms: p50 {a['p50']} p95 {a['p95']} max {a['max']} (n={a['n']})")
    for pair, a in report["agreement"].items():
        lines.append(f"{pair}: top1 agree {a['top1_agree']} (n={a['decisions']}), Top-3 Jaccard {a['mean_top3_jaccard']}")
    for name, m in report["categories"]["per_model"].items():
        hp = m["hero_power"]
        lines.append(f"{name}: HERO_POWER top1 when legal {hp['top1_share_when_legal']} ({hp['legal_decisions']}); "
                     f"END_TURN top1 {m['end_turn']['top1_end_turn_share']}; lethal candidates {m['lethal_candidates']}")
    for pair, kinds in report["categories"]["disagreements"].items():
        lines.append(f"{pair} disagreements: " + ", ".join(f"{k}={v['count']}" for k, v in kinds.items()))
    return "\n".join(lines)
