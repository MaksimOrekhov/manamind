"""Read-only inventory of local real-match data and card-frequency analysis on the widest permitted corpus.

Run from the main checkout root (ignored data lives there). Protected ``fresh_holdout`` matches are excluded by ID
before any game file is opened: raw logs and LIVE recordings by their 16-hex key, Policy files by their full game_id
file name. Only aggregates are printed (no game IDs, names or log lines). Nothing is written.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from manamind.outcome.grammar import parse_text  # noqa: E402

ROOT = Path(".")
RAW = ROOT / "data/raw"
POLICY = ROOT / "data/processed_policy_real/collected"
SPLIT_PLAN = ROOT / "data/processed_policy_prepare_1/split_plan.json"
USAGE = ROOT / "data/processed_policy_prepare_1/usage_registry.json"
EVAL1 = ROOT / "data/processed_new_matches_eval_1/protocol.private.json"
EVAL2 = ROOT / "data/processed_new_matches_eval_2/protocol.private.json"
HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def pct(a, b):
    return f"{a}/{b} ({a / b:.1%})" if b else f"{a}/0"


# ---------------------------------------------------------------- protected IDs (metadata only)
plan = load(SPLIT_PLAN)
held = set(plan["parts"]["fresh_holdout"])
assert len(held) == 9, "expected nine protected IDs"
held16 = {g[:16] for g in held}

# ---------------------------------------------------------------- A. physical files (names/sizes only)
collected = sorted((RAW / "collected").glob("*.log"))
keyed = [p for p in collected if HEX16.match(p.stem)]
legacy = [p for p in collected if not HEX16.match(p.stem)]
live_dirs = [d for s in sorted((RAW / "live").glob("Hearthstone_*")) if s.is_dir() for d in s.iterdir() if d.is_dir()]
live_slices = [d / "slice.log" for d in live_dirs if (d / "slice.log").exists()]
pending = list((RAW / "collected/.pending").rglob("*.log")) if (RAW / "collected/.pending").exists() else []
loose = [p for p in RAW.glob("*.log")]
all_logs = list(RAW.rglob("*.log"))
state = load(RAW / "collected/collector_state.json")["games"]
print("== A. Physical log files ==")
print(f"all *.log under data/raw: {len(all_logs)}")
print(f"  data/raw/collected match slices: {len(collected)} (keyed by match id {len(keyed)}, legacy names {len(legacy)})")
print(f"  LIVE recordings: {len(live_dirs)} match directories in {len(list((RAW / 'live').glob('Hearthstone_*')))} "
      f"client sessions; slice.log copies {len(live_slices)}")
print(f"  loose files in data/raw: {len(loose)}; collector pending slices: {len(pending)}")
print(f"collector_state game sections: {len(state)} -> {dict(Counter(state.values()))}")
print(f"protected keys among collected keyed logs: {sum(p.stem in held16 for p in keyed)}; "
      f"among LIVE dirs: {sum(d.name in held16 for d in live_dirs)}")

# ---------------------------------------------------------------- B. identities
K = {p.stem for p in keyed}
L = {d.name for d in live_dirs}
policy_files = sorted(p for p in POLICY.glob("*.jsonl") if HEX64.match(p.stem))
P = {p.stem for p in policy_files}
P16 = {g[:16] for g in P}
print("\n== B. Match identities ==")
print(f"keyed raw match logs: {len(K)} unique keys; LIVE dirs: {len(L)} unique keys, "
      f"{len(L & K)} also keyed raw, {len(L - K)} LIVE-only")
print(f"Policy match files: {len(P)} unique game_ids; {len(P16 & K)} have a keyed raw log; "
      f"{len(P16 - K)} come from legacy/loose logs (identity known only via the Policy file)")
print(f"keyed raw logs without a Policy file (rejected by the strict Policy importer): {len(K - P16)}")
print(f"identity-level unique completed Ranked Standard matches (keyed raw U Policy): {len(K | P16)}; "
      f"protected among them: {len((K | P16) & held16)}")
print("limit: legacy logs rejected by the Policy importer have no identity without opening them (not opened).")

# ---------------------------------------------------------------- C. usage overlap
usage = {e["match_id"]: e["status"] for e in load(USAGE)["entries"]}
parts = {g: part for part, ids in plan["parts"].items() for g in ids}
e1 = set(load(EVAL1)["eligible_match_ids"])
e2p = load(EVAL2)
e2_strict = set(e2p["eligible_match_ids"])
e2_all = {m["game_id"] for m in e2p["matches"]}
retrain = {p.stem for p in (ROOT / "data/processed_policy_real/real_policy_retrain_1").glob("*.jsonl")}
obs1 = {p.stem for p in (ROOT / "data/processed_policy_real/refresh_obs1_final").glob("*.jsonl")}
usable = sorted(P - held)
cats = Counter()
for g in usable:
    if g in parts:
        cats[f"prepare-corpus split: {parts[g]}"] += 1
    elif g in e1:
        cats["EVAL-1 eligible"] += 1
    elif g in e2_all:
        cats["EVAL-2 completed (incl. 12 strict)"] += 1
    else:
        cats["not in any registry (collected after EVAL-2)"] += 1
print("\n== C. Usage of non-protected Policy matches ==")
print(f"non-protected Policy matches: {len(usable)} (protected excluded by file name: {len(P & held)})")
for k, v in sorted(cats.items()):
    print(f"  {k}: {v}")
print(f"  of them in real_policy_retrain_1 (initial 55-match corpus): {len(set(usable) & retrain)}; "
      f"in refresh_obs1_final (32): {len(set(usable) & obs1)}; EVAL-2 strict: {len(set(usable) & e2_strict)}")
print(f"  usage registry statuses (prepare corpus, 92): {dict(Counter(usage.values()))}")

# ---------------------------------------------------------------- D. card frequencies
cat = {c["id"]: c for c in load("data/cards/standard_current_enUS.json")["cards"]}
snap = {c["id"]: c for c in load("data/cards/source_snapshots/cards_collectible_20261001_enUS.json")}
me = load("experiments/manaengine/data/card_abilities.json")["cards"]
me_ok = {k for k, v in me.items() if v.get("support_state") in ("SUPPORTED", "VERIFIED_VANILLA")}
_parse_cache = {}


def text_record(cid):
    return cat.get(cid) or snap.get(cid)


def template_parsed(cid):
    if cid not in _parse_cache:
        rec = text_record(cid)
        if rec is None:
            _parse_cache[cid] = False
        else:
            text = rec.get("text") or ""
            parsed = parse_text(text) if text.strip() else None
            _parse_cache[cid] = parsed is None or (
                not parsed.trigger_sentences and all(cl.kind != "OPAQUE" for cl in parsed.clauses))
    return _parse_cache[cid]


def id_kind(cid):
    if cid in cat:
        return "standard_catalog"
    if cid in snap:
        return "collectible_snapshot_non_standard"
    if cid.startswith("HERO_") or "_HP" in cid or cid.endswith("hp"):
        return "hero_power_like"
    if cid == "GAME_005":
        return "coin"
    if re.search(r"t\d*[a-z]?$", cid) or "_t" in cid:
        return "token_like_suffix"
    return "other_noncollectible"


EFFECT_ZONES = ("hand", "self_board", "opp_board", "self_weapon", "opp_weapon", "self_location", "opp_location")


def entities(state):
    # Board and Location slots nest the card under "card"; hand, weapon and Hero Power entries are cards themselves.
    # (The initial real_card_coverage.py read board["card_id"] and therefore silently counted no board entities.)
    out = []
    for side, tag in (("self_player", "self"), ("opponent", "opp")):
        p = state[side]
        out += [(f"{tag}_board", (m.get("card") or {}).get("card_id")) for m in p.get("board") or []]
        out += [(f"{tag}_location", (m.get("card") or {}).get("card_id")) for m in p.get("locations") or []]
        if p.get("weapon"):
            out.append((f"{tag}_weapon", p["weapon"].get("card_id")))
        if p.get("hero_power"):
            out.append((f"{tag}_hero_power", p["hero_power"].get("card_id")))
    out += [("hand", h.get("card_id")) for h in state.get("self_hand") or []]
    out += [("opp_revealed", c if isinstance(c, str) else c.get("card_id")) for c in state.get("opponent_known_cards") or []]
    return [(z, c) for z, c in out if c]


matches = {}
for path in policy_files:
    g = path.stem
    if g in held:  # protected: never opened
        continue
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    matches[g] = rows


def analyse(name, ids):
    freq, zone_freq, zone_ids = Counter(), Counter(), defaultdict(Counter)
    dec = Counter()
    self_cls, opp_cls = Counter(), Counter()
    cls_freq = defaultdict(Counter)
    for g in ids:
        rows = matches[g]
        if not rows:
            continue
        s0 = rows[0]["state"]
        sc = s0["self_player"].get("player_class") or "UNKNOWN"
        oc = s0["opponent"].get("player_class") or "UNKNOWN"
        self_cls[sc] += 1
        opp_cls[oc] += 1
        for r in rows:
            items = entities(r["state"])
            eff = [(z, c) for z, c in items if z in EFFECT_ZONES]
            for z, c in items:
                zone_ids[z][c] += 1
                zone_freq[z] += 1
            for z, c in eff:
                freq[c] += 1
                own = z.startswith("self") or z == "hand"
                cls_freq[f"SELF {sc}" if own else f"OPP {oc}"][c] += 1
            cs = {c for _, c in eff}
            dec["n"] += 1
            dec["all_text_source"] += all(text_record(c) for c in cs)
            dec["all_template_parsed"] += all(template_parsed(c) for c in cs)
            dec["all_engine_declared"] += all(c in me_ok for c in cs)
    tot = sum(freq.values())
    ranked = freq.most_common()
    print(f"\n== D. {name}: matches={len(ids)} decisions={dec['n']} effect-zone appearances={tot} "
          f"unique effect-zone card IDs={len(freq)} ==")
    print("  SELF classes:", dict(self_cls.most_common()), "| OPP classes:", dict(opp_cls.most_common()))
    shares = {k: sum(n for _, n in ranked[:k]) / tot for k in (10, 25, 50, 100)}
    print("  top-K share:", {k: f"{v:.1%}" for k, v in shares.items()})
    acc, need = 0, {}
    for i, (_, n) in enumerate(ranked, 1):
        acc += n
        for th in (0.5, 0.8, 0.9, 0.95):
            if th not in need and acc >= th * tot:
                need[th] = i
    print("  IDs needed for share:", {f"{int(t * 100)}%": v for t, v in need.items()})
    print("  by zone (appearances | unique | text source | template-parsed | engine-declared, appearance-weighted):")
    for z in sorted(zone_ids):
        c = zone_ids[z]
        n = sum(c.values())
        ts = sum(v for k, v in c.items() if text_record(k))
        tp = sum(v for k, v in c.items() if template_parsed(k))
        ed = sum(v for k, v in c.items() if k in me_ok)
        print(f"    {z:16s} {n:6d} | {len(c):4d} | {ts / n:6.1%} | {tp / n:6.1%} | {ed / n:6.1%}")
    kinds = Counter()
    for c, n in freq.items():
        kinds[id_kind(c)] += n
    print("  effect-zone appearances by ID source:", {k: f"{v / tot:.1%}" for k, v in kinds.most_common()})
    print("  decision-level (effect zones):", {k: pct(v, dec["n"]) for k, v in dec.items() if k != "n"})
    print("  per SELF/OPP class: matches-in-class, unique IDs, IDs for 80% of that class's appearances")
    for key in sorted(cls_freq):
        c = cls_freq[key]
        n = sum(c.values())
        acc, k80 = 0, 0
        for i, (_, v) in enumerate(c.most_common(), 1):
            acc += v
            if acc >= 0.8 * n:
                k80 = i
                break
        side, klass = key.split(" ", 1)
        mc = self_cls[klass] if side == "SELF" else opp_cls[klass]
        print(f"    {key:22s} matches={mc:3d} unique={len(c):4d} ids_for_80%={k80}")
    return freq


everything = analyse("ALL non-protected Policy matches", usable)
initial = analyse("INITIAL corpus real_policy_retrain_1", sorted(set(usable) & retrain))
older = sorted(g for g in usable if g in usage)
newer = sorted(g for g in usable if g not in usage)
older_freq = analyse("OLDER: prepare-corpus matches (collected up to 2026-10-15)", older)
newer_freq = analyse("NEWER: matches collected after the prepare corpus", newer)

print("\n== E. Does a short list learned on older matches cover newer matches? ==")
tot_new = sum(newer_freq.values())
for k in (25, 50, 100, 200):
    top = {c for c, _ in older_freq.most_common(k)}
    cov = sum(n for c, n in newer_freq.items() if c in top) / tot_new
    print(f"  top-{k} IDs of OLDER corpus cover {cov:.1%} of NEWER effect-zone appearances")
print(f"  NEWER IDs never seen in OLDER: {len(set(newer_freq) - set(older_freq))} of {len(newer_freq)}; "
      f"their share of NEWER appearances: "
      f"{sum(n for c, n in newer_freq.items() if c not in older_freq) / tot_new:.1%}")

print("\n== F. Accumulation of unique effect-zone IDs with more matches (deterministic order by game_id) ==")
seen, curve = set(), {}
for i, g in enumerate(usable, 1):
    for r in matches[g]:
        seen |= {c for z, c in entities(r["state"]) if z in EFFECT_ZONES}
    if i in (10, 25, 50, 75, 100, 125) or i == len(usable):
        curve[i] = len(seen)
print("  matches -> unique IDs:", curve)

print("\n== G. Decision structure (for the performance section) ==")
labeled = [len(rows) for rows in matches.values()]
audits = [load(POLICY / f"{g}.audit.json") for g in usable if (POLICY / f"{g}.audit.json").exists()]
totals = [a["decisions_total"] for a in audits]
menus = [len(r["legal_actions"]) for rows in matches.values() for r in rows]
turns = [max(r["state"]["turn_number"] for r in rows) for rows in matches.values() if rows]
per_turn = [n for rows in matches.values() for n in Counter(r["state"]["turn_number"] for r in rows).values()]
q = statistics.quantiles
print(f"  SELF labeled decisions per match: mean {statistics.mean(labeled):.1f}, median {statistics.median(labeled)}")
print(f"  SELF decisions per match incl. importer-skipped: mean {statistics.mean(totals):.1f}, "
      f"median {statistics.median(totals)}")
print(f"  last observed turn_number per match (both players' turns): mean {statistics.mean(turns):.1f}, "
      f"median {statistics.median(turns)}")
print(f"  SELF labeled decisions per SELF turn: mean {statistics.mean(per_turn):.2f}, p90 {q(per_turn, n=10)[8]:.0f}, "
      f"max {max(per_turn)}")
print(f"  legal menu size: mean {statistics.mean(menus):.1f}, median {statistics.median(menus)}, "
      f"p90 {q(menus, n=10)[8]:.0f}, max {max(menus)}")

print("\n== H. Effect-zone IDs without any pinned text record, by set prefix ==")
from manamind.outcome.grammar import board_profile  # noqa: E402

for name, ids in (("OLDER", older), ("NEWER", newer)):
    miss, total = Counter(), 0
    for g in ids:
        for r in matches[g]:
            for z, c in entities(r["state"]):
                if z in EFFECT_ZONES:
                    total += 1
                    if not text_record(c):
                        miss[re.sub(r"_.*", "", c)] += 1
    print(f"  {name}: missing {sum(miss.values()) / total:.1%} of appearances; by prefix (share of all appearances):",
          {k: f"{v / total:.1%}" for k, v in miss.most_common(6)})

print("\n== I. Board entities: what the Turn Engine must know about them ==")
# A card already on the board matters for my turn only through its keywords, triggers and static rules; its
# Battlecry is history. board_profile() splits text into trigger and static sentences (heuristic, text-only).
for zone in ("opp_board", "self_board"):
    kinds, total = Counter(), 0
    for g in usable:
        for r in matches[g]:
            for z, c in entities(r["state"]):
                if z != zone:
                    continue
                total += 1
                rec = text_record(c)
                if rec is None:
                    kinds["no text record"] += 1
                    continue
                triggers, statics = board_profile(rec.get("text") or "")
                kinds["keywords/stats only on board" if not triggers and not statics else
                      "has trigger or static rule"] += 1
    print(f"  {zone}: " + ", ".join(f"{k} {v / total:.1%}" for k, v in kinds.most_common()))
