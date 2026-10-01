# Static summon and equip pilot — 2026-10-01

## Scope

Added two allowlisted Standard root CardDefs through the bounded effect-composition generator:

- `CORE_TSC_076` Immortalized in Stone summons the three explicit Statue token CardDefs (`TSC_076t3`, `TSC_076t2`, `TSC_076t`) in reverse task order so RosettaStone's insertion behavior produces the printed left-to-right board order (4/8, 2/4, 1/2 Taunt).
- `CORE_GVG_061` Muster for Battle summons three registered `CS2_101t` Silver Hand Recruits, then equips registered `CS2_091` Light's Justice (1/4).

The generator now accepts `SUMMON` and `EQUIP` operations only when each referenced card ID is declared as a dependency, has the expected MINION/WEAPON metadata type, and has a source CardDef when its rules text is nonempty. Dependencies must match the IDs actually referenced by effects. Existing enchantment support remains intact. No arbitrary card IDs or operations are accepted outside the generator's allowlist/schema.

## Verification

- Generator validated all 11 composition declarations.
- Native focused suite: 11 cases / 67 assertions passed, including independent board stats, Taunt, three recruit summons and equipped weapon stats.
- Bridge smoke passed for both cards: Standard deck validation, session creation, opening-hand visibility and legal-action enumeration.
- Registry: 1,185 roots; 167 direct + 80 generated registrations; 157 known non-root nodes; 310 heuristic pool signals; 935 text-bearing roots without detected registration; zero complete root closures and zero training-eligible roots.

## Limits

Both new roots remain `IMPLEMENTED_UNVERIFIED`. Scenarios cover the named static outputs, but do not establish every board-capacity, interaction, match-completion or transitive-root condition. The package does not change full-pool training admission.
