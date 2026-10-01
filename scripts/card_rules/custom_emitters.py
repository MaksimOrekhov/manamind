"""Frozen reviewed card-specific emitters retained from the migration pilot.

These emitters are CUSTOM, not reusable capabilities. Extract a parameterized
operation when a second reviewed consumer establishes the shared contract.
"""
from .composition_ops import TARGETS, generic_tasks, implementation_route, task_expression as generic_task_expression

def task_expression(effect: dict) -> str:
    op = effect["op"]
    if op == "DRAW_MINION_MIN_COST":
        return f'std::make_shared<DrawMinionTask>(DrawMinionType::MIN_COST_AT_LEAST, {effect["amount"]}, false, {effect["min_cost"]})'
    if op == "DRAW_SPELL_MIN_COST":
        return f'std::make_shared<DrawSpellTask>(SpellSchool::NONE, DrawSpellType::MIN_COST_AT_LEAST, {effect["amount"]}, false, {effect["min_cost"]})'
    if op == "BUFF_HAND_MINIONS":
        return 'std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::MINIONS_HAND)'
    if op == "RANDOM_SPLIT_DAMAGE":
        return 'std::make_shared<EnqueueTask>(ComplexTask::DamageRandomTargets(EntityType::ENEMIES, 1, 1), 2)'
    return generic_task_expression(effect)

def generated_source(cards: list[dict]) -> str:
    blocks = []
    if any(card["card_id"] == "EDR_468" for card in cards):
        blocks.append('''    if (cards.contains("EDR_468e"))
        throw std::logic_error("duplicate generated CardDef: EDR_468e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackN(4) }));
        cards.emplace("EDR_468e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "IF_TARGET_DIES" and effect["outcome"] == "BUFF_RANDOM_FRIENDLY_3_3" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("END_014e"))
        throw std::logic_error("duplicate generated CardDef: END_014e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(3) }));
        cards.emplace("END_014e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "BUFF_DAMAGED_FRIENDLY_MINIONS" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("JAIL_376e"))
        throw std::logic_error("duplicate generated CardDef: JAIL_376e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackN(1), Effects::HealthN(2) }));
        cards.emplace("JAIL_376e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "DRAW_TWO_DRAGONS_REDUCE_COST" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("EDR_572e"))
        throw std::logic_error("duplicate generated CardDef: EDR_572e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::ReduceCost(1) }));
        cards.emplace("EDR_572e", std::move(enchantDef));
    }''')
    if any(effect["op"] in {"RANDOM_OTHER_FRIENDLY_BUFF", "RANDOM_FRIENDLY_ATTACK_BUFF", "BUFF_HAND_MINIONS"} for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("ICC_210e"))
        throw std::logic_error("duplicate generated CardDef: ICC_210e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(1) }));
        cards.emplace("ICC_210e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "RANDOM_FRIENDLY_ATTACK_BUFF" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("CATA_467e"))
        throw std::logic_error("duplicate generated CardDef: CATA_467e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackN(2) }));
        cards.emplace("CATA_467e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "OPPONENT_HERO_POWER_SET_COST" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("CORE_DRG_403e"))
        throw std::logic_error("duplicate generated CardDef: CORE_DRG_403e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddAura(std::make_shared<Aura>(
            AuraType::ENEMY_HERO_POWER, EffectList{ Effects::SetCost(2) }));
        const auto aura = dynamic_cast<Aura*>(enchantDef.power.GetAura());
        aura->removeTrigger = { TriggerType::INSPIRE, nullptr };
        cards.emplace("CORE_DRG_403e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "INCREASE_SOURCE_HEALTH_IF_UNDAMAGED" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("CATA_305e"))
        throw std::logic_error("duplicate generated CardDef: CATA_305e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::HealthN(3) }));
        cards.emplace("CATA_305e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "BUFF_HAND_TAUNT_MINIONS" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("CORE_WW_329e"))
        throw std::logic_error("duplicate generated CardDef: CORE_WW_329e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(2) }));
        cards.emplace("CORE_WW_329e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "DRAW_MINION_AND_BUFF_HAND_HEALTH" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("TIME_037e"))
        throw std::logic_error("duplicate generated CardDef: TIME_037e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::HealthN(2) }));
        cards.emplace("TIME_037e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "BUFF_HAND_MINIONS_AND_LEGENDARIES" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("JAIL_387e"))
        throw std::logic_error("duplicate generated CardDef: JAIL_387e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackN(2), Effects::HealthN(1) }));
        cards.emplace("JAIL_387e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "BUFF_BEASTS_ALL_ZONES" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("TLC_828e"))
        throw std::logic_error("duplicate generated CardDef: TLC_828e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(2) }));
        cards.emplace("TLC_828e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "BUFF_HAND_MINIONS_AND_WEAPONS_ATTACK" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("END_021e"))
        throw std::logic_error("duplicate generated CardDef: END_021e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackN(2) }));
        cards.emplace("END_021e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "RANDOM_FRIENDLY_BEAST_HAND_BUFF" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("MEND_305e"))
        throw std::logic_error("duplicate generated CardDef: MEND_305e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(2) }));
        cards.emplace("MEND_305e", std::move(enchantDef));
    }''')
    if any(effect.get("id") == "DINO_419e" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("DINO_419e"))
        throw std::logic_error("duplicate generated CardDef: DINO_419e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(2) }));
        cards.emplace("DINO_419e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "RANDOM_OTHER_DAMAGED_FRIENDLY_MINION_BUFF" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("TLC_623e"))
        throw std::logic_error("duplicate generated CardDef: TLC_623e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::AttackHealthN(2) }));
        cards.emplace("TLC_623e", std::move(enchantDef));
    }''')
    if any(effect["op"] == "BUFF_ALL_SPELLS_HAND_DECK_SPELLPOWER" for card in cards for effect in card["effects"]):
        blocks.append('''    if (cards.contains("CATA_458e"))
        throw std::logic_error("duplicate generated CardDef: CATA_458e");
    {
        CardDef enchantDef;
        enchantDef.ClearData();
        enchantDef.power.AddEnchant(std::make_shared<Enchant>(
            std::vector<std::shared_ptr<IEffect>>{ Effects::SpellPowerN(1) }));
        cards.emplace("CATA_458e", std::move(enchantDef));
    }''')
    for card in cards:
        lines = [f'    if (cards.contains("{card["card_id"]}"))',
                 f'        throw std::logic_error("duplicate generated CardDef: {card["card_id"]}");',
                 '    {', '        CardDef cardDef;', '        cardDef.ClearData();']
        if card["card_id"] == "TIME_100":
            lines.append('        cardDef.power.AddPowerTask(nullptr);')
        if implementation_route(card) == "COMPOSABLE":
            lines.extend(generic_tasks(card))
        elif card["activation"] == "DEATHRATTLE" and card["card_id"] == "TLC_EVENT_402":
            lines.append('        cardDef.power.AddDeathrattleTask(std::make_shared<DestroyTask>(EntityType::ALL_MINIONS));')
        elif card["activation"] == "DEATHRATTLE" and card["card_id"] == "EDR_861":
            lines.extend([
                '        cardDef.power.AddDeathrattleTask(std::make_shared<ManaCrystalTask>(1, false));',
                '        cardDef.power.AddDeathrattleTask(std::make_shared<ManaCrystalTask>(1, false, true));'])
        elif card["activation"] == "DEATHRATTLE" and card["card_id"] == "TLC_621":
            lines.append('        cardDef.power.AddDeathrattleTask(std::make_shared<CustomTask>([](Player* player, Entity*, Playable*) { for (int i = 0; i < 3; ++i) { auto* top = player->GetDeckZone()->GetTopCard(); if (!top) break; top->Destroy(); } }));')
        elif card["activation"] == "DEATHRATTLE" and card["card_id"] == "JAIL_376":
            lines.extend([
                '        cardDef.power.AddDeathrattleTask(std::make_shared<IncludeTask>(EntityType::MINIONS));',
                '        cardDef.power.AddDeathrattleTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsDamaged()) }));',
                '        cardDef.power.AddDeathrattleTask(std::make_shared<AddEnchantmentTask>("JAIL_376e", EntityType::STACK));'])
        elif card["activation"] == "DEATHRATTLE" and card["card_id"] == "EDR_572":
            lines.extend([
                '        cardDef.power.AddDeathrattleTask(std::make_shared<DrawRaceMinionTask>(Race::DRAGON, 2, true));',
                '        cardDef.power.AddDeathrattleTask(std::make_shared<AddEnchantmentTask>("EDR_572e", EntityType::STACK));'])
        elif card["activation"] == "DEATHRATTLE" and card["card_id"] == "CORE_ICC_214":
            lines.extend([
                '        cardDef.power.AddDeathrattleTask(std::make_shared<IncludeTask>(EntityType::ENEMY_MINIONS));',
                '        cardDef.power.AddDeathrattleTask(std::make_shared<RandomTask>(EntityType::STACK, 1));',
                '        cardDef.power.AddDeathrattleTask(std::make_shared<DestroyTask>(EntityType::STACK));'])
        elif card["activation"] == "DEATHRATTLE":
            add_method = "AddDeathrattleTask"
            lines.extend(f'        cardDef.power.{add_method}({task_expression(effect)});' for effect in card["effects"])
        elif card["activation"] == "TURN_END":
            lines.append('        cardDef.power.AddTrigger(std::make_shared<Trigger>(TriggerType::TURN_END));')
            if card["card_id"] == "CORE_ICC_210":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS_NOSOURCE), std::make_shared<RandomTask>(EntityType::STACK, 1), std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::STACK) };')
            elif card["card_id"] == "EDR_889":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS_NOSOURCE), std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsRace(Race::DRAGON)) }), std::make_shared<RandomTask>(EntityType::STACK, 1), std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::STACK) };')
            elif card["card_id"] == "EDR_816":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS_NOSOURCE), std::make_shared<AddEnchantmentTask>("EX1_162o", EntityType::STACK) };')
            elif card["card_id"] == "TIME_428":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS_NOSOURCE), std::make_shared<AddEnchantmentTask>("DRG_057e", EntityType::STACK) };')
            elif card["card_id"] == "CATA_305":
                lines.append('        cardDef.power.GetTrigger()->conditions = SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsUndamaged()) };')
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<AddEnchantmentTask>("CATA_305e", EntityType::SOURCE) };')
            elif card["card_id"] == "TLC_623":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS_NOSOURCE), std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsDamaged()) }), std::make_shared<RandomTask>(EntityType::STACK, 1), std::make_shared<AddEnchantmentTask>("TLC_623e", EntityType::STACK) };')
            else:
                lines.append('        cardDef.power.GetTrigger()->tasks = { ' + ", ".join(task_expression(effect) for effect in card["effects"]) + ' };')
        elif card["activation"] == "TURN_START_EACH":
            lines.append('        cardDef.power.AddTrigger(std::make_shared<Trigger>(TriggerType::TURN_START));')
            lines.append('        cardDef.power.GetTrigger()->eitherTurn = true;')
            lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<AddEnchantmentTask>("EX1_162o", EntityType::SOURCE) };')
        elif card["activation"] == "AFTER_HERO_ATTACK":
            lines.append('        cardDef.power.AddTrigger(std::make_shared<Trigger>(TriggerType::AFTER_ATTACK));')
            lines.append('        cardDef.power.GetTrigger()->triggerSource = TriggerSource::HERO;')
            if card["card_id"] == "CORE_GIL_534":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::SOURCE) };')
            elif card["card_id"] == "CATA_467":
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS_NOSOURCE), std::make_shared<RandomTask>(EntityType::STACK, 1), std::make_shared<AddEnchantmentTask>("CATA_467e", EntityType::STACK) };')
            else:
                lines.append('        cardDef.power.GetTrigger()->tasks = { std::make_shared<IncludeTask>(EntityType::MINIONS), std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>([](Playable* playable) { return playable->card->GetCardClass() == CardClass::PALADIN; }) }), std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::STACK), std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::STACK) };')
        elif card["card_id"] == "CORE_OG_211":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<SummonTask>("NEW1_032", 1));',
                '        cardDef.power.AddPowerTask(std::make_shared<SummonTask>("NEW1_033", 1));',
                '        cardDef.power.AddPowerTask(std::make_shared<SummonTask>("NEW1_034", 1));'])
        elif card["card_id"] == "DINO_406":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<DamageTask>(EntityType::TARGET, 4, true));',
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::MINIONS));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsRace(Race::ELEMENTAL)) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::STACK));'])
        elif card["card_id"] == "CATA_201":
            lines.append('        cardDef.power.AddPowerTask(std::make_shared<ReturnHandTask>(EntityType::ENEMY_MINIONS));')
        elif card["card_id"] == "JAIL_441":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<DamageTask>(EntityType::TARGET, 3, true));',
                '        cardDef.power.AddPowerTask(std::make_shared<CustomTask>([](Player* player, Entity*, Playable*) { player->GetHeroPower().SetExhausted(false); }));'])
        elif card["card_id"] == "CATA_203":
            lines.append('        cardDef.power.AddPowerTask(std::make_shared<DestroyTask>(EntityType::TARGET));')
        elif card["card_id"] == "FIR_954":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<DamageTask>(EntityType::TARGET, 5, true));',
                '        cardDef.power.AddPowerTask(std::make_shared<CustomTask>([](Player*, Entity*, Playable* target) { if (target && target->player) Generic::Draw(target->player, nullptr); }));'])
        elif card["card_id"] == "CORE_DRG_403":
            lines.append('        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("CORE_DRG_403e", EntityType::ENEMY_PLAYER));')
        elif card["card_id"] == "CORE_WW_329":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::MINIONS_HAND));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsTagValue(GameTag::TAUNT, 1)) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("CORE_WW_329e", EntityType::STACK));'])
        elif card["card_id"] == "TIME_037":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<DrawMinionTask>(DrawMinionType::DEFAULT, 1, false));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("TIME_037e", EntityType::MINIONS_HAND));'])
        elif card["card_id"] == "JAIL_387":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("ICC_210e", EntityType::MINIONS_HAND));',
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::MINIONS_HAND));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>([](Playable* playable) { return playable->card->GetRarity() == Rarity::LEGENDARY; }) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("JAIL_387e", EntityType::STACK));'])
        elif card["card_id"] == "TLC_828":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::MINIONS_HAND_DECK_FIELD));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsRace(Race::BEAST)) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("TLC_828e", EntityType::STACK));'])
        elif card["card_id"] == "END_021":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::HAND));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>([](Playable* playable) { const auto type = playable->card->GetCardType(); return type == CardType::MINION || type == CardType::WEAPON; }) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("END_021e", EntityType::STACK));'])
        elif card["card_id"] == "MEND_305":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("MEND_305e", EntityType::TARGET));',
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::MINIONS_HAND));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsRace(Race::BEAST)) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<RandomTask>(EntityType::STACK, 1));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("MEND_305e", EntityType::STACK));'])
        elif card["card_id"] == "CATA_458":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::HAND_SPELL));',
                '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::DECK));',
                '        cardDef.power.AddPowerTask(std::make_shared<FilterStackTask>(SelfCondList{ std::make_shared<SelfCondition>([](Playable* playable) { return playable->card->GetCardType() == CardType::SPELL; }) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<AddEnchantmentTask>("CATA_458e", EntityType::STACK));'])
        elif card["card_id"] == "JAIL_377":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<DrawTask>(1, true));',
                '        cardDef.power.AddPowerTask(std::make_shared<ConditionTask>(EntityType::STACK, SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsCost(2, RelaSign::LEQ)) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<FlagTask>(true, TaskList{ std::make_shared<DrawTask>(1) }));'])
        elif card["card_id"] == "JAIL_456":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<ConditionTask>(EntityType::SOURCE, SelfCondList{ std::make_shared<SelfCondition>([](Playable* playable) { return playable->player->GetDeckZone()->GetCount() >= 25; }) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<FlagTask>(true, TaskList{ std::make_shared<DrawTask>(1) }));'])
        elif card["card_id"] in {"CATA_303", "END_014", "TLC_606"}:
            for effect in card["effects"]:
                if effect["op"] == "DAMAGE":
                    lines.append(f'        cardDef.power.AddPowerTask({task_expression(effect)});')
                elif effect["op"] == "IF_TARGET_DIES":
                    lines.append('        cardDef.power.AddPowerTask(std::make_shared<ConditionTask>(EntityType::TARGET, SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsDead()) }));')
                    if effect["outcome"] == "HEAL_ENEMY_HERO_5":
                        task = 'std::make_shared<HealTask>(EntityType::ENEMY_HERO, 5)'
                    elif effect["outcome"] == "GAIN_ARMOR_5":
                        task = 'std::make_shared<ArmorTask>(5)'
                    else:
                        task = 'std::make_shared<IncludeTask>(EntityType::MINIONS), std::make_shared<RandomTask>(EntityType::STACK, 1), std::make_shared<AddEnchantmentTask>("END_014e", EntityType::STACK)'
                    lines.append(f'        cardDef.power.AddPowerTask(std::make_shared<FlagTask>(true, TaskList{{ {task} }}));')
        elif card["card_id"] == "JAIL_462":
            lines.extend([
                '        cardDef.power.AddPowerTask(std::make_shared<DrawTask>(2, true));',
                '        cardDef.power.AddPowerTask(std::make_shared<ConditionTask>(EntityType::SOURCE, SelfCondList{ std::make_shared<SelfCondition>([](Playable* playable) { const auto& drawn = playable->player->game->taskStack.playables; return drawn.size() == 2 && std::all_of(drawn.begin(), drawn.end(), [](Playable* card) { return card && card->card->GetCardType() == CardType::MINION; }); }) }));',
                '        cardDef.power.AddPowerTask(std::make_shared<FlagTask>(true, TaskList{ std::make_shared<SetGameTagTask>(EntityType::SOURCE, GameTag::CHARGE, 1) }));'])
        elif card["activation"] in {"AFTER_CAST", "AFTER_CAST_ON_MINION"}:
            lines.append('        cardDef.power.AddTrigger(std::make_shared<Trigger>(TriggerType::AFTER_CAST));')
            lines.append('        cardDef.power.GetTrigger()->triggerSource = TriggerSource::FRIENDLY;')
            if card["activation"] == "AFTER_CAST_ON_MINION":
                lines.append('        cardDef.power.GetTrigger()->conditions = SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsSpellTargetingMinion()) };')
            lines.append('        cardDef.power.GetTrigger()->tasks = { ' + ", ".join(task_expression(effect) for effect in card["effects"]) + ' };')
        elif card["activation"] == "BATTLECRY_AND_DEATHRATTLE":
            lines.extend(f'        cardDef.power.AddPowerTask({task_expression(effect)});' for effect in card["effects"] if effect["op"] in {"BATTLECRY_DAMAGE", "RANDOM_DAMAGE"})
            lines.extend(f'        cardDef.power.AddDeathrattleTask({task_expression(effect)});' for effect in card["effects"] if effect["op"] in {"DEATHRATTLE_DAMAGE", "RANDOM_DAMAGE"})
        else:
            if card["card_id"] == "CORE_KAR_061":
                lines.extend([
                    '        cardDef.power.AddPowerTask(std::make_shared<DrawRaceMinionTask>(Race::BEAST, 1, false));',
                    '        cardDef.power.AddPowerTask(std::make_shared<DrawRaceMinionTask>(Race::DRAGON, 1, false));',
                    '        cardDef.power.AddPowerTask(std::make_shared<DrawRaceMinionTask>(Race::MURLOC, 1, false));'])
            elif card["card_id"] == "CORE_GVG_059":
                lines.extend([
                    '        cardDef.power.AddPowerTask(std::make_shared<IncludeTask>(EntityType::MINIONS));',
                    '        cardDef.power.AddPowerTask(std::make_shared<RandomTask>(EntityType::STACK, 1));',
                    '        cardDef.power.AddPowerTask(std::make_shared<SetGameTagTask>(EntityType::STACK, GameTag::DIVINE_SHIELD, 1));',
                    '        cardDef.power.AddPowerTask(std::make_shared<SetGameTagTask>(EntityType::STACK, GameTag::TAUNT, 1));'])
            else:
                for effect in card["effects"]:
                    if effect["op"] == "ARMOR_DAMAGE":
                        lines.append('        cardDef.power.AddPowerTask(std::make_shared<GetGameTagTask>(EntityType::HERO, GameTag::ARMOR));')
                        lines.append(f'        cardDef.power.AddPowerTask(std::make_shared<DamageNumberTask>({TARGETS[effect["target"]]}, true));')
                    else:
                        lines.append(f'        cardDef.power.AddPowerTask({task_expression(effect)});')
        if card["play_requirements"]:
            reqs = ", ".join(f'{{ PlayReq::{req}, {"static_cast<int>(Race::ALL)" if req == "REQ_TARGET_WITH_RACE" and card["card_id"] == "TLC_633" else 20 if req == "REQ_TARGET_WITH_RACE" else 0} }}' for req in card["play_requirements"])
            lines.append(f'        cardDef.property.playReqs = PlayReqs{{ {reqs} }};')
        lines.extend([f'        cards.emplace("{card["card_id"]}", std::move(cardDef));', '    }'])
        blocks.append("\n".join(lines))
    return '''// Generated by scripts/generate_effect_composition.py. Do not edit by hand.
#include <Rosetta/PlayMode/CardSets/ManaMindEffectCompositionGen.hpp>
#include <Rosetta/PlayMode/Cards/CardPowers.hpp>
#include <Rosetta/PlayMode/Cards/Card.hpp>
#include <Rosetta/PlayMode/Models/Playable.hpp>
#include <Rosetta/PlayMode/Models/Player.hpp>
#include <Rosetta/PlayMode/Models/HeroPower.hpp>
#include <Rosetta/PlayMode/Zones/DeckZone.hpp>
#include <Rosetta/PlayMode/Conditions/SelfCondition.hpp>
#include <Rosetta/PlayMode/Triggers/Trigger.hpp>

#include <Rosetta/PlayMode/Tasks/ITask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/AddEnchantmentTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/AddCardTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ArmorTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DamageTask.hpp>
#include <Rosetta/PlayMode/Actions/Draw.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/CustomTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DamageNumberTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DrawTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ConditionTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/FlagTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DrawMinionTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DrawSpellTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DrawRaceMinionTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/DestroyTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/FreezeTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/IncludeTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/FilterStackTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/RandomTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ReturnHandTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/HealTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/GetGameTagTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/EnqueueTask.hpp>
#include <Rosetta/PlayMode/Tasks/ComplexTask.hpp>
#include <Rosetta/PlayMode/Enchants/Effects.hpp>
#include <Rosetta/PlayMode/Auras/Aura.hpp>
#include <Rosetta/PlayMode/Enchants/Enchant.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/SetGameTagTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/SilenceTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/SummonTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/WeaponTask.hpp>
#include <Rosetta/PlayMode/Tasks/SimpleTasks/ManaCrystalTask.hpp>

#include <stdexcept>
#include <algorithm>
#include <memory>
#include <utility>

namespace RosettaStone::PlayMode
{
void ManaMindEffectCompositionGen::AddAll(std::map<std::string, CardDef>& cards)
{
using namespace SimpleTasks;

'''+"\n\n".join(blocks)+'''
}
}  // namespace RosettaStone::PlayMode
'''


