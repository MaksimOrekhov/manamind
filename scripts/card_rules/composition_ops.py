"""Parameterized operations; new card declarations must not require a card-ID branch here."""
TARGETS = {"TARGET": "EntityType::TARGET", "SOURCE": "EntityType::SOURCE", "HERO": "EntityType::HERO", "HEROES": "EntityType::HEROES", "FRIENDS": "EntityType::FRIENDS", "ENEMY_HERO": "EntityType::ENEMY_HERO", "ENEMIES": "EntityType::ENEMIES", "ALL_MINIONS_NOSOURCE": "EntityType::ALL_MINIONS_NOSOURCE", "MINIONS_NOSOURCE": "EntityType::MINIONS_NOSOURCE", "ENEMY_MINIONS": "EntityType::ENEMY_MINIONS"}
TAGS = {"REBORN": "GameTag::REBORN", "DIVINE_SHIELD": "GameTag::DIVINE_SHIELD", "RUSH": "GameTag::RUSH"}

def task_expression(effect: dict) -> str:
    op = effect["op"]
    if op in {"DAMAGE", "BATTLECRY_DAMAGE", "DEATHRATTLE_DAMAGE"}:
        return f'std::make_shared<DamageTask>({TARGETS[effect["target"]]}, {effect["amount"]}, {str(effect["spell_damage"]).lower()})'
    if op == "HEAL":
        return f'std::make_shared<HealTask>({TARGETS[effect["target"]]}, {effect["amount"]})'
    if op == "ENCHANT":
        return f'std::make_shared<AddEnchantmentTask>("{effect["id"]}", {TARGETS[effect["target"]]})'
    if op == "DRAW":
        return f'std::make_shared<DrawTask>({effect["amount"]})'
    if op == "ARMOR":
        return f'std::make_shared<ArmorTask>({effect["amount"]})'
    if op == "SET_TAG":
        return f'std::make_shared<SetGameTagTask>({TARGETS[effect["target"]]}, {TAGS[effect["tag"]]}, {effect["value"]})'
    if op == "SILENCE":
        return 'std::make_shared<SilenceTask>(EntityType::TARGET)'
    if op == "FREEZE":
        return f'std::make_shared<FreezeTask>({TARGETS[effect["target"]]})'
    if op == "SUMMON":
        return f'std::make_shared<SummonTask>("{effect["card_id"]}", {effect["amount"]})'
    if op == "EQUIP":
        return f'std::make_shared<WeaponTask>("{effect["card_id"]}")'
    if op == "ADD_TO_HAND":
        return f'std::make_shared<AddCardTask>(EntityType::HAND, "{effect["card_id"]}", {effect["amount"]})'
    if op == "RANDOM_DAMAGE":
        return (f'std::make_shared<EnqueueTask>(ComplexTask::DamageRandomTargets({TARGETS[effect["target"]]}, '
                f'1, {effect["amount"]}, {str(effect["spell_damage"]).lower()}), {effect["hits"]})')
    if op == "ARMOR_DAMAGE":
        raise ValueError("ARMOR_DAMAGE is not a generic task; use reviewed custom routing")
    raise ValueError(f"Unsupported generic operation: {op}")



GENERIC_OPS = {"DAMAGE", "BATTLECRY_DAMAGE", "DEATHRATTLE_DAMAGE", "HEAL", "ENCHANT", "DRAW", "ARMOR", "SET_TAG", "SILENCE", "FREEZE", "SUMMON", "EQUIP", "ADD_TO_HAND", "RANDOM_DAMAGE"}

def implementation_route(card: dict) -> str:
    if card["card_id"] in CUSTOM_EMITTER_CARD_IDS:
        return "CUSTOM"
    if card["activation"] not in {"BATTLECRY", "DEATHRATTLE", "BATTLECRY_AND_DEATHRATTLE", "SPELL_PLAY", "TURN_END", "AFTER_CAST", "AFTER_CAST_ON_MINION"}:
        return "CUSTOM"
    if any(effect["op"] not in GENERIC_OPS for effect in card["effects"]):
        return "CUSTOM"
    if "REQ_TARGET_WITH_RACE" in card["play_requirements"]:
        return "CUSTOM"
    return "COMPOSABLE"

CUSTOM_EMITTER_CARD_IDS = {'JAIL_387', 'TLC_633', 'CATA_303', 'JAIL_456', 'END_014', 'JAIL_376', 'EDR_816', 'TIME_428', 'JAIL_441', 'CORE_DRG_403', 'CORE_WW_329', 'TLC_621', 'CATA_458', 'CATA_201', 'EDR_572', 'DINO_406', 'END_021', 'EDR_861', 'CATA_305', 'CATA_203', 'CORE_KAR_061', 'CORE_OG_211', 'CORE_GVG_059', 'TLC_EVENT_402', 'EDR_468', 'TLC_606', 'MEND_305', 'CORE_ICC_210', 'TIME_037', 'CORE_ICC_214', 'CORE_GIL_534', 'CATA_467', 'JAIL_377', 'FIR_954', 'TLC_828', 'JAIL_462', 'TLC_623', 'TIME_100', 'EDR_889'}

def generic_tasks(card: dict) -> list[str]:
    """Render parameterized activations without branching on card identity."""
    if implementation_route(card) != "COMPOSABLE":
        raise ValueError("Custom contract cannot enter generic composition")
    activation = card["activation"]
    effects = card["effects"]
    if activation == "DEATHRATTLE":
        return [f'        cardDef.power.AddDeathrattleTask({task_expression(e)});' for e in effects]
    if activation in {"TURN_END", "AFTER_CAST", "AFTER_CAST_ON_MINION"}:
        trigger = "TURN_END" if activation == "TURN_END" else "AFTER_CAST"
        lines = [f'        cardDef.power.AddTrigger(std::make_shared<Trigger>(TriggerType::{trigger}));']
        if trigger == "AFTER_CAST":
            lines.append('        cardDef.power.GetTrigger()->triggerSource = TriggerSource::FRIENDLY;')
        if activation == "AFTER_CAST_ON_MINION":
            lines.append('        cardDef.power.GetTrigger()->conditions = SelfCondList{ std::make_shared<SelfCondition>(SelfCondition::IsSpellTargetingMinion()) };')
        lines.append('        cardDef.power.GetTrigger()->tasks = { ' + ", ".join(task_expression(e) for e in effects) + ' };')
        return lines
    if activation == "BATTLECRY_AND_DEATHRATTLE":
        return ([f'        cardDef.power.AddPowerTask({task_expression(e)});' for e in effects if e["op"] in {"BATTLECRY_DAMAGE", "RANDOM_DAMAGE"}] +
                [f'        cardDef.power.AddDeathrattleTask({task_expression(e)});' for e in effects if e["op"] in {"DEATHRATTLE_DAMAGE", "RANDOM_DAMAGE"}])
    return [f'        cardDef.power.AddPowerTask({task_expression(e)});' for e in effects]
