"""Read-only probe: can the 65 parity plays be joined to EVIDENCE-0B windows by an exact identity key
(game, turn_number, card_id, SELF PLAY) with uniqueness on both sides? fresh_holdout never opened."""
import json, glob, os
from collections import Counter, defaultdict
plan = json.load(open('data/processed_policy_prepare_1/split_plan.json'))
allowed = set(plan['parts']['train']) | set(plan['parts']['validation']) | set(plan['parts']['test_seen'])
prot16 = {g[:16] for g in plan['parts']['fresh_holdout']}
assert not {g[:16] for g in allowed} & prot16
CARDS = {"CORE_EX1_238", "CORE_AT_055", "CORE_ICC_055", "FIR_906"}
pol = []
for gid in sorted(allowed):
    p = f'data/processed_policy_prepare_1/dataset/{gid}.jsonl'
    if not os.path.exists(p):
        continue
    for line in open(p, encoding='utf-8'):
        r = json.loads(line); a = r['legal_actions'][r['chosen_action_index']]
        if a.get('type') == 'PLAY_CARD' and a.get('card_id') in CARDS:
            pol.append((gid[:16], r['state']['turn_number'], a['card_id'], r['provenance']['state_hash'],
                        a.get('target_side'), a.get('target_kind')))
ev = defaultdict(list)
for d in glob.glob('data/processed_evidence/collected/*'):
    k = os.path.basename(d)[:16]
    if k in prot16 or not any(k == x[0] for x in pol):
        continue
    for line in open(os.path.join(d, 'observations.jsonl'), encoding='utf-8'):
        o = json.loads(line); s = o['subject']
        if s.get('card_id') in CARDS and s.get('side') == 'SELF' and o['window']['root_block_type'] == 'PLAY':
            tgt = [f['data']['target'] for f in o['facts'] if f['kind'] == 'PLAY_TARGET']
            ev[(k, o['provenance']['turn'], s['card_id'])].append((o['public_states']['before_hash'], tgt))
pc = Counter(x[:3] for x in pol)
print('policy plays', len(pol), 'evidence SELF plays', sum(map(len, ev.values())))
print('games of policy plays with evidence dir', len({x[0] for x in pol} & {k[0] for k in ev}))
uniq = [x for x in pol if pc[x[:3]] == 1 and len(ev.get(x[:3], [])) == 1]
hashj = [x for x in pol if any(h == x[3] for h, _ in ev.get(x[:3], []))]
tgt_ok = [x for x in uniq if (lambda t: len(t) == 1 and t[0].get('side') == x[4] and t[0].get('card_type') == x[5])(ev[x[:3]][0][1])]
print('unique (game,turn_number,card) joins', len(uniq), 'of which PLAY_TARGET side/type agrees', len(tgt_ok))
print('exact before_hash joins', len(hashj))
