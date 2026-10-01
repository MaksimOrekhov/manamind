# Textless vanilla minion pilot — 2026-10-01

Added a strict metadata-only generator for three pinned Standard roots whose catalog records have no rules text or mechanics:

- `Core_CS2_200` — Boulderfist Ogre (6/7)
- `TIME_053` — Sandmaw (7/2)
- `TLC_248` — Ultragigasaur (14/28)

The generator requires exact pinned-catalog fingerprint, explicit allowlisting, collectible MINION type, empty rules text and mechanics, and valid printed cost/attack/health. It emits empty ordinary CardDefs with duplicate-owner checks. Generated C++ is excluded from the registry's independent source-edge scan; declared package dependencies remain sourced from manifests rather than neighboring generated code strings.

## Verification

- Native runtime scenario played all three cards and checked their printed attack/health: 1 case / 18 assertions passed.
- Bridge smoke passed Standard deck validation, session creation, opening-hand visibility, and legal-action enumeration for all three cards.
- Standard registry tests: 10 passed.
- Latest registry: 1,185 roots; 167 direct + 84 generated registrations; 934 text-bearing roots without detected registration; 157 known non-root nodes; 310 heuristic pool signals; zero complete root closures and zero training-eligible roots.

## Limits

The three entries remain `METADATA_ONLY_CANDIDATE` in rules verification. Empty text/mechanics in this pinned metadata is evidence for a vanilla implementation proposal, not proof that the data source contains every rule. Full-profile admission remains blocked.
