# Independent expectations — minion_set_enchant_v1

Frozen before coding, 2026-10-02. Scope: RLK_048, TLC_233, TIME_447;
ICC_210e (+1/+1), ULD_191e (+0/+2). These expectations come from the
pinned card texts and reviewed targeting/lifetime rules, not generated tasks.

## TLC_233 recipient timing

After the source enters the board and entry auras are effective, take one
snapshot of **other own board minions whose current Attack is <= 2** at
Battlecry resolution. Apply both +1/+1 and Taunt to that same set. Attack
0 becomes 1; Attack 2 becomes 3 and still receives Taunt. Attack 3 is
excluded, even if its printed Attack is 1. The source, heroes, Locations,
enemy board and both hands are excluded. A later buff cannot add a recipient
to this already selected set. A repeated activation makes a new selection.

Blizzard's [35.6.2 patch notes](https://hearthstone.blizzard.com/en-gb/news/24271882/35-6-2-patch-notes)
confirm the pinned +1/+1 amount. They do not specify snapshot timing. The
single recipient set is a rules interpretation to be checked by independent
boundary/aura scenarios; no observed official-client replay is claimed.

## TIME_447 target and hand effect

Requires one legal character: own/enemy minion or own/enemy hero. Ordinary
spell restrictions (enemy Stealth, either side's Elusive) apply. Locations,
weapons and hand cards are not legal character targets. An already shielded
character remains legal; empty hand does not prevent casting. Invalid or
absent targets must not cast or buff the hand.

First grant Divine Shield to the chosen character, then grant +2 maximum
and current Health to every minion card in the controller's hand. No Attack
change, no buff to spells/weapons or opponent hand. The selected target's
controller/type does not alter the hand effect. A hand minion retains its
buff when played; printed base metadata stays unchanged.

## Lifetime and interactions

RLK_048 affects own board minions only: +1/+1 and both spell/hero-power
target protections (Elusive). Attacks and Battlecry targeting remain legal.
Existing damage is preserved when maximum Health increases. Repeated buffs
stack numeric values. Silence removes these stats/keywords; bounce returns
the base card; copied enchanted minions retain their effects independently.
Each execution replaces its own selected task stack; no previous activation
may supply recipients. Heroes are valid Shield targets but never mass-buff
recipients. Tests use literal numeric expectations, never declaration-derived
expected values. The four pre-existing control owners remain unchanged.

No dynamic outcome pools are created by these effects or their two fixed
stat enchantments. This is an explicit review conclusion, not inference from
the absence of heuristic graph edges. DK session setup remains a separate
blocker; native DK spell effects do not certify a playable DK session.
