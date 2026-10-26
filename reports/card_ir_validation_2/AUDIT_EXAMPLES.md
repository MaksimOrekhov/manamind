# Расширенный аудит — читаемые примеры

Сгенерировано через render_audit + validate_strict. Ошибочные варианты взяты из неизменённой диагностики Opus.
Сохранённый статус FULL не означает принятие: ниже явно показаны отказы строгого режима.

## Контрфактический Magma Hound: условие и роли видны

- Declared status: PARTIAL — representation label, not semantic approval
- keywords[0] TEXT: Rush. => Keyword RUSH
- abilities[0] TEXT: After this attacks a minion and survives, deal this minion's Attack damage split among all enemies. => Trigger [no keyword, timing=AFTER, active zone=PLAY (default; weapon EQUIPPED)]; ATTACK_DECLARED; subject (role UNDEFINED in v0.1)=this; defender=a enemy minion [zones=PLAY; mode=ALL]; ONLY IF this's health [read=CURRENT] > 0; limit=none declared; effect: repeat this's attack [read=CURRENT] times: [deal 1 damage to random 1 enemy character [zones=PLAY; mode=RANDOM]]
- Dependency <attacker_role> UNKNOWN_RULE/CORE: v0.1 does not define the subject role of ATTACK_DECLARED; read here as the attacker; source needed: Reviewer-written probe (Claude Opus 5.5); not a gold declaration
- Decision subject [OUTCOME/ASSUMPTION]: Is ATTACK_DECLARED.subject the attacker? => attacker; alternatives: attacker / undefined; dependency=attacker_role; distinguishing case: An enemy minion attacks Magma Hound: no trigger in the card's reading.
- Strict acceptance=True; complete=False; computed status=PARTIAL
- Rule R_AREA_SNAPSHOT [PROJECT_REVIEWED]: An ALL selector fixes its members when the step starts (mortally wounded included, new entities excluded)
- Rule R_DAMAGE [PROJECT_REVIEWED]: A damage packet: Divine Shield and Immune prevent it, a hero loses Armor first, damage events are dispatched after the step's mutations
- Rule R_LAST_KNOWN [UNVERIFIED]: A value read from an entity that has left play is its last known value
- Rule R_RANDOM_LIVE [COMMUNITY_RULES]: A RANDOM pick considers only live candidates (not mortally wounded, not pending destroy), is re-evaluated for every pick, and an empty candidate set does nothing
- Rule R_TRIGGER_ORDER [PROJECT_REVIEWED]: Simultaneous triggers resolve in the order their sources entered play; nested consequences finish before siblings
- Rule R_TRIGGER_TIMING [COMMUNITY_RULES]: WHENEVER fires on the event, AFTER once the event has resolved, AT at a turn phase, WHEN (Secrets) before the event resolves

## TIME_216/unconditional_draw

Различающий случай из аудита: Target an enemy 3/3: it dies; the card draws 0, the declaration draws 2.

- Declared status: FULL — representation label, not semantic approval
- abilities[0] TEXT: Deal $5 damage to a minion. If it survives, draw 2 cards. => Cast: choose a chosen minion [zones=PLAY; mode=CHOSEN] as <target>; deal $5 damage to them<target>; then you draw 2 x card
- Strict acceptance=False; complete=False; computed status=FULL
- REVIEW WARNING: abilities[0]: CONDITION_ENTITY: survival/death guard missing or on the wrong entity/branch
- Rule R_AMOUNT_ORDER [UNKNOWN]: Order of additive bonuses (Spell Damage, healing bonus), multipliers (doubling) and replacements (healing becomes damage)
- Rule R_DAMAGE [PROJECT_REVIEWED]: A damage packet: Divine Shield and Immune prevent it, a hero loses Armor first, damage events are dispatched after the step's mutations
- Rule R_DRAW [UNVERIFIED]: A draw takes the top deck card; an empty deck causes fatigue; a full hand destroys the card
- Rule R_PLAY_TARGET [UNVERIFIED]: A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry without one resolves without it
- Rule R_SPELL_DAMAGE [PROJECT_REVIEWED]: A '$' amount adds the controller's Spell Damage once per step (CURRENT_AT_STEP)
- Rule R_STEP_BOUNDARY [PROJECT_REVIEWED]: A sequence step finishes, with the reactions it causes, before the next step is evaluated; deaths are not processed between steps

## JAIL_118/destroy_all

Различающий случай из аудита: Board with a Silver Hand Recruit: the card keeps it (and V'ama), the declaration kills both.

- Declared status: FULL — representation label, not semantic approval
- abilities[0] TEXT: Battlecry: Destroy all non-Paladin minions. => Battlecry: destroy all minions [zones=PLAY; mode=ALL]
- Strict acceptance=False; complete=False; computed status=FULL
- REVIEW WARNING: abilities[0]: EXCLUSION_PREDICATE: exclusion for PALADIN is missing/inverted or in another zone
- Rule R_AREA_SNAPSHOT [PROJECT_REVIEWED]: An ALL selector fixes its members when the step starts (mortally wounded included, new entities excluded)
- Rule R_DEATH_PHASE [PROJECT_REVIEWED]: A destroyed or 0-Health minion stays in play mortally wounded until the outer phase boundary, then dead minions leave in order and their Deathrattles queue
- Rule R_PLAY_TARGET [UNVERIFIED]: A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry without one resolves without it

## JAIL_118/enemy_only

Различающий случай из аудита: A friendly neutral minion survives in the declaration but dies to the card (control).

- Declared status: FULL — representation label, not semantic approval
- abilities[0] TEXT: Battlecry: Destroy all non-Paladin minions. => Battlecry: destroy all enemy minions except all minions card class PALADIN [zones=PLAY; mode=ALL] [zones=PLAY; mode=ALL]
- Strict acceptance=False; complete=False; computed status=FULL
- REVIEW WARNING: abilities[0]: enemy side needs an enemy word
- REVIEW WARNING: abilities[0]: AREA_SIDE: unqualified all minions includes both sides
- Rule R_AREA_SNAPSHOT [PROJECT_REVIEWED]: An ALL selector fixes its members when the step starts (mortally wounded included, new entities excluded)
- Rule R_DEATH_PHASE [PROJECT_REVIEWED]: A destroyed or 0-Health minion stays in play mortally wounded until the outer phase boundary, then dead minions leave in order and their Deathrattles queue
- Rule R_PLAY_TARGET [UNVERIFIED]: A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry without one resolves without it

## JAIL_399/shuffle_not_bottom

Различающий случай из аудита: Next draw after the Deathrattle: the card never draws a Grandmother Imp from a non-empty deck, the declaration may.

- Declared status: FULL_DEP — representation label, not semantic approval
- keywords[0] TEXT: Taunt. => Keyword TAUNT
- abilities[0] TEXT: Deathrattle: Put two 8/8 Demons with Taunt and Lifesteal on the bottom of your deck. => Deathrattle: repeat 2 times: [shuffle Grandmother Imp [JAIL_399t1] (resolved by description_match) into your deck]
- Dependency <token> TOKEN_IDENTITY/DATA: JAIL_399t1 by prefix and stats; source needed: Reviewer-written probe (Claude Opus 5.5); not a gold declaration
- Strict acceptance=False; complete=False; computed status=FULL_DEP
- REVIEW WARNING: abilities[0]: DECK_POSITION: v0.1 shuffle cannot express top/bottom insertion
- Rule R_DEATHRATTLE [PROJECT_REVIEWED]: A Deathrattle resolves after its owner leaves play, from its last position; Silence removes it; Reborn returns the minion after its Deathrattles
- Rule R_DEATH_PHASE [PROJECT_REVIEWED]: A destroyed or 0-Health minion stays in play mortally wounded until the outer phase boundary, then dead minions leave in order and their Deathrattles queue
- Rule R_DECK_POSITION [UNVERIFIED]: Shuffling inserts at a random deck position; 'bottom' inserts last
- Rule R_HIDDEN_ZONE [PROJECT_REVIEWED]: Effects on a hidden zone happen but are not observable to SELF; the IR never fills in the hidden identities

## CORE_SCH_713/this_turn

Различающий случай из аудита: Opponent's 1-mana spell on their next turn: the card makes it cost 2, the declaration 1.

- Declared status: FULL — representation label, not semantic approval
- abilities[0] TEXT: Battlecry: Your opponent's spells cost (1) more next turn. => Battlecry: player effect on OPPONENT: cost reduced by -1; applies-to filters: card type SPELL; duration=this turn; uses=UNSPECIFIED (v0.1 cardinality not resolved); use-unit=unspecified
- Strict acceptance=False; complete=False; computed status=FULL
- REVIEW WARNING: abilities[0]: WINDOW_NEXT: v0.1 duration cannot encode the next player's turn
- Rule R_COST [UNKNOWN]: Current cost = base cost with modifiers, floored at 0; the order of set-to-N and reductions
- Rule R_PLAYER_EFFECT [UNKNOWN]: A player-level effect has a duration and a use counter and applies to the next matching card or effect
- Rule R_PLAY_TARGET [UNVERIFIED]: A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry without one resolves without it

## FIR_953/hero_attack

Различающий случай из аудита: Your hero attacks with a weapon while Magma Hound stays idle: only the declaration fires.

- Declared status: FULL — representation label, not semantic approval
- keywords[0] TEXT: Rush. => Keyword RUSH
- abilities[0] TEXT: After this attacks a minion and survives, deal this minion's Attack damage split among all enemies. => Trigger [no keyword, timing=AFTER, active zone=PLAY (default; weapon EQUIPPED)]; HERO_ATTACK; attacker=hero of SELF; player=SELF; limit=none declared; effect: repeat this's attack [read=CURRENT] times: [deal 1 damage to random 1 enemy character [zones=PLAY; mode=RANDOM]]
- Strict acceptance=False; complete=False; computed status=FULL
- REVIEW WARNING: abilities[0]: CONDITION_ENTITY: survival/death guard missing or on the wrong entity/branch
- REVIEW WARNING: abilities[0]: EVENT_SUBJECT: source minion attack is not HERO_ATTACK
- Rule R_DAMAGE [PROJECT_REVIEWED]: A damage packet: Divine Shield and Immune prevent it, a hero loses Armor first, damage events are dispatched after the step's mutations
- Rule R_LAST_KNOWN [UNVERIFIED]: A value read from an entity that has left play is its last known value
- Rule R_RANDOM_LIVE [COMMUNITY_RULES]: A RANDOM pick considers only live candidates (not mortally wounded, not pending destroy), is re-evaluated for every pick, and an empty candidate set does nothing
- Rule R_TRIGGER_ORDER [PROJECT_REVIEWED]: Simultaneous triggers resolve in the order their sources entered play; nested consequences finish before siblings
- Rule R_TRIGGER_TIMING [COMMUNITY_RULES]: WHENEVER fires on the event, AFTER once the event has resolved, AT at a turn phase, WHEN (Secrets) before the event resolves

## CATA_585/reminder_loophole

Различающий случай из аудита: Any damaged 2-Health target: the card returns Torch(6); the declaration never returns it, and adds Spell Damage the card ignores.

- Declared status: FULL — representation label, not semantic approval
- abilities[0] TEXT: Deal $8 damage to a damaged minion. => Cast: choose a chosen minion damaged [zones=PLAY; mode=CHOSEN] as <target>; deal $8 damage to them<target>
- reminders[0] REMINDER (not executed): Return this to hand with any excess damage.; reason: flavour
- Strict acceptance=False; complete=False; computed status=FULL
- ERROR: REMINDER: /reminders/0 is not a non-operative progress readout
- Rule R_AMOUNT_ORDER [UNKNOWN]: Order of additive bonuses (Spell Damage, healing bonus), multipliers (doubling) and replacements (healing becomes damage)
- Rule R_DAMAGE [PROJECT_REVIEWED]: A damage packet: Divine Shield and Immune prevent it, a hero loses Armor first, damage events are dispatched after the step's mutations
- Rule R_PLAY_TARGET [UNVERIFIED]: A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry without one resolves without it
- Rule R_SPELL_DAMAGE [PROJECT_REVIEWED]: A '$' amount adds the controller's Spell Damage once per step (CURRENT_AT_STEP)

## CORE_RLK_063/reminder_loophole

Различающий случай из аудита: Enemy minions attack next turn in the declaration; the card froze them.

- Declared status: FULL_DEP — representation label, not semantic approval
- abilities[0] TEXT: Deal $5 damage. => Cast: choose a chosen character [zones=PLAY; mode=CHOSEN] as <target>; deal $5 damage to them<target>
- abilities[1] TEXT: Summon a 5/5 Frostwyrm. => Cast: summon 1 x Frostwyrm [RLK_063t] (resolved by name_in_set)
- reminders[0] REMINDER (not executed): Freeze all enemy minions.; reason: reminder
- Dependency <token> TOKEN_IDENTITY/DATA: RLK_063t by name; source needed: Reviewer-written probe (Claude Opus 5.5); not a gold declaration
- Strict acceptance=False; complete=False; computed status=FULL_DEP
- ERROR: REMINDER: /reminders/0 is not a non-operative progress readout
- Rule R_AMOUNT_ORDER [UNKNOWN]: Order of additive bonuses (Spell Damage, healing bonus), multipliers (doubling) and replacements (healing becomes damage)
- Rule R_BOARD_LIMIT [UNVERIFIED]: At most 7 minions per side; extra summons fail and later steps see only those summoned
- Rule R_DAMAGE [PROJECT_REVIEWED]: A damage packet: Divine Shield and Immune prevent it, a hero loses Armor first, damage events are dispatched after the step's mutations
- Rule R_PLAY_TARGET [UNVERIFIED]: A CHOSEN target is fixed when the card is played; a spell needs a legal target, a Battlecry without one resolves without it
- Rule R_SPELL_DAMAGE [PROJECT_REVIEWED]: A '$' amount adds the controller's Spell Damage once per step (CURRENT_AT_STEP)
- Rule R_SUMMON_POSITION [UNVERIFIED]: Battlecry summons enter to the right of the source, Deathrattle summons at its slot, other summons at the right end

## EDR_895/everything_reminder

Различающий случай из аудита: Three own turns later: the card sets all your card costs to 1, the declaration does nothing.

- Declared status: FULL — representation label, not semantic approval
- reminders[0] REMINDER (not executed): Battlecry: Start a three turn lunar cycle. When the Full Moon rises, your cards cost (1) this game.; reason: reminder
- Strict acceptance=False; complete=False; computed status=FULL
- ERROR: REMINDER: /reminders/0 is not a non-operative progress readout

## Известное ложное срабатывание: пояснение Rush

Это допустимое пояснение. Отказ относится к узкому контракту reminders, а не к правилу Rush.

- Declared status: FULL — representation label, not semantic approval
- keywords[0] TEXT: Rush. => Keyword RUSH
- reminders[0] REMINDER (not executed): (Can attack minions immediately.); reason: Explanation of the already declared Rush keyword
- Strict acceptance=False; complete=False; computed status=FULL
- ERROR: REMINDER: /reminders/0 is not a non-operative progress readout
