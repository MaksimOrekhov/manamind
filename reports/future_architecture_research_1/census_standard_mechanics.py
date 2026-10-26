"""Read-only census of the pinned Standard catalog: grammar coverage + mechanic families."""
import json, re, sys, collections
sys.path.insert(0, "src")
from manamind.outcome.grammar import parse_text, normalise

cat = json.load(open("data/cards/standard_current_enUS.json", encoding="utf-8"))["cards"]
N = len(cat)
full = 0; vanilla = 0; partial = 0
by_type = collections.Counter(); full_by_type = collections.Counter()
for c in cat:
    t = c.get("text") or ""
    by_type[c["type"]] += 1
    if not t.strip():
        vanilla += 1; full += 1; full_by_type[c["type"]] += 1; continue
    p = parse_text(t)
    ok = not p.trigger_sentences and all(cl.kind != "OPAQUE" for cl in p.clauses)
    if ok:
        full += 1; full_by_type[c["type"]] += 1
    elif any(cl.kind != "OPAQUE" for cl in p.clauses):
        partial += 1
print(f"cards={N} textless={vanilla} fully_parsed_by_outcome_grammar={full} ({full/N:.1%}) some_clause_parsed={partial}")
print("by type:", {k: f"{full_by_type[k]}/{v}" for k, v in by_type.items()})

def plain(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>|\[x\]", "", t or "").replace("\xa0", " ")).lower()

fam = {
 "trigger_whenever_after": r"\b(whenever|after)\b",
 "start_end_of_turn": r"\b(start|end) of (your|each|the)",
 "deathrattle": r"deathrattle",
 "battlecry": r"battlecry",
 "aura_static (your X have/cost)": r"\b(your|all|other) [a-z ]*(have|has|cost) ",
 "cost_modification": r"costs? \(\d+\)|cost (less|more)|costs? \d+ less",
 "random_any": r"\brandom",
 "discover": r"\bdiscover",
 "generate_to_hand (add/get)": r"\b(add|get) (a|an|two|three|\d)",
 "transform": r"\btransform",
 "copy": r"\bcop(y|ies)\b",
 "shuffle_into_deck": r"shuffle",
 "history/counter (this game/this turn/if you've)": r"this game|if you('ve| have)|for each|this turn",
 "choose_one": r"choose one",
 "secret_quest": r"\bsecret\b|\bquest",
 "summon": r"\bsummon",
 "draw": r"\bdraw",
 "deal_damage": r"deal \$?\d+ damage",
 "set_expansion_keywords": r"\b(imbue|kindred|dark gift|herald|shatter|rewind|fabled|prepare|corpse|excavate|forge|tradeable|starship|infuse|manathirst|finale|spellburst|frenzy|overheal|quickdraw|colossal|dormant|titan|elusive)\b",
}
cnt = collections.Counter(); 
for c in cat:
    t = plain(c.get("text"))
    for k, rx in fam.items():
        if re.search(rx, t): cnt[k] += 1
for k in fam: print(f"{k:50s} {cnt[k]:4d} {cnt[k]/N:5.1%}")
kw = collections.Counter()
for c in cat:
    for m in c.get("mechanics", []) or []: kw[m] += 1
print("top mechanics tags:", kw.most_common(45))
# set-specific keyword census
setkw = collections.Counter()
for c in cat:
    t = plain(c.get("text"))
    for w in ["imbue","kindred","dark gift","herald","shatter","rewind","fabled","prepare","corpse","excavate","forge","tradeable","starship","infuse","manathirst","finale","spellburst","frenzy","overheal","quickdraw","colossal","dormant","titan","elusive","overload","combo","outcast","lifesteal","rush","taunt","divine shield","reborn","poisonous","windfury","stealth","freeze","silence","discover","echo","magnetic","twinspell","choose one"]:
        if re.search(r"\b"+w+r"\b", t): setkw[w] += 1
print("text keywords:", setkw.most_common())
print("sets:", collections.Counter(c["set"] for c in cat).most_common())
