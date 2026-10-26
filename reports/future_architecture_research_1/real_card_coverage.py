"""Read-only: which card IDs appear in real decisions, frequency concentration, and decision-level coverage
by (a) ManaEngine declarations, (b) the outcome text grammar. Prints aggregates only (no game IDs / names).

NOTE (review v2): this initial v1 diagnostic reads board["card_id"], but board and Location slots nest the card
under board["card"], so it counts no board entities. Kept unchanged for history; corpus_inventory.py replaces it."""
import sys, json, re, collections
from pathlib import Path
sys.path.insert(0, "src")
from manamind.training.real_policy import load_examples
from manamind.outcome.grammar import parse_text

root = Path(sys.argv[1])
rows = load_examples(root)
cat = {c["id"]: c for c in json.load(open("data/cards/standard_current_enUS.json", encoding="utf-8"))["cards"]}
snap = {c["id"]: c for c in json.load(open("data/cards/source_snapshots/cards_collectible_20261001_enUS.json", encoding="utf-8"))}
me = json.load(open("experiments/manaengine/data/card_abilities.json", encoding="utf-8"))["cards"]
me_ok = {k for k, v in me.items() if v.get("support_state") in ("SUPPORTED", "VERIFIED_VANILLA")}

def grammar_ok(cid):
    c = cat.get(cid) or snap.get(cid)
    if c is None: return None
    t = c.get("text") or ""
    if not t.strip(): return True
    p = parse_text(t)
    return not p.trigger_sentences and all(cl.kind != "OPAQUE" for cl in p.clauses)

def ids(state):
    out = []
    for side in ("self_player", "opponent"):
        p = state[side]
        for m in p.get("board") or []: out.append(("board_" + side, m.get("card_id")))
        for m in p.get("locations") or []: out.append(("loc_" + side, m.get("card_id")))
        if p.get("weapon"): out.append(("weapon_" + side, p["weapon"].get("card_id")))
    for h in state.get("self_hand") or []: out.append(("hand", h.get("card_id")))
    return [(z, c) for z, c in out if c]

freq = collections.Counter(); zones = collections.Counter()
dec_cov = collections.Counter(); games = set()
for r in rows:
    games.add(r["game_id"])
    items = ids(r["state"])
    cs = {c for _, c in items}
    for z, c in items:
        freq[c] += 1; zones[(z, c in cat, c in snap)] += 1
    dec_cov["n"] += 1
    if all(c in me_ok for c in cs): dec_cov["all_manaengine"] += 1
    g = [grammar_ok(c) for c in cs]
    if all(x is True for x in g): dec_cov["all_grammar"] += 1
    if all(c in cat for c in cs): dec_cov["all_in_standard_catalog"] += 1
    if all((c in cat or c in snap) for c in cs): dec_cov["all_with_text_source"] += 1
print(f"decisions={len(rows)} matches={len(games)} unique_card_ids={len(freq)} appearances={sum(freq.values())}")
tot = sum(freq.values()); acc = 0
for i, (c, n) in enumerate(freq.most_common(), 1):
    acc += n
    for th in (0.5, 0.8, 0.9, 0.95):
        if acc - n < th * tot <= acc: print(f"  {int(th*100)}% of appearances covered by top {i} card IDs")
print("decision-level coverage:", {k: f"{v}/{dec_cov['n']} ({v/dec_cov['n']:.1%})" for k, v in dec_cov.items() if k != "n"})
in_cat = sum(n for c, n in freq.items() if c in cat); in_snap = sum(n for c, n in freq.items() if c in snap)
print(f"appearances with Standard catalog record {in_cat/tot:.1%}; with any pinned text source {in_snap/tot:.1%}")
print("unique ids supported by ManaEngine:", len([c for c in freq if c in me_ok]), "| fully parsed by grammar:", len([c for c in freq if grammar_ok(c) is True]))
