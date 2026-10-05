# Vulcanos Fire pool review

Date: 2026-10-05. Snapshot: `standard_full_20261001_v1`.

## Result

`fire_spell_standard_20261001_candidate_v1` remains a 33-card **CANDIDATE** (membership SHA-256 `480f5971bdf90a339f08142a9f2e47c7650be1ddd6973241960885b20b3e0e87`, metadata SHA-256 `d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930`). No runtime manifest is admitted and the candidate file is not changed.

The pinned snapshot confirms that the 33 IDs are Standard-legal collectible spells with Fire school. The reviewed metadata slice also finds no Quest or Rune requirement among these candidates and each canonical ID occurs once. These facts establish the predicate subset, not exact runtime membership.

## Evidence and limits

- Blizzard's [Standard random-effects format explanation](https://hearthstone.blizzard.com/en-gb/news/19995505) says random card effects use cards eligible in the active format. This supports the Standard boundary.
- Blizzard's [26.0.4 patch notes](https://hearthstone.blizzard.com/en-gb/news/23935323/26-0-4-patch-notes) explicitly remove all cards with any three-rune requirement from random-generation and Discover pools. No candidate in the 33-card set has such a requirement.
- Blizzard's [26.2.2 patch notes](https://hearthstone.blizzard.com/en-gb/news/23957164/26-2-2-patch-notes) show that some Fire-spell effects have a narrower, class-bound and non-Legendary pool. This is not the same wording as Plume's unrestricted “random Fire spell”.
- The pinned profile and HearthstoneJSON-derived candidate do not provide an exhaustive, patch-specific list of all cards excluded from ordinary random generation. Current official material located for this review does not enumerate every such exception or state that Plume uses the raw collectible-school predicate without further exclusions.

Therefore the `NON_GENERATABLE` exclusion inventory is still `UNRESOLVED`. No selection from the 33-card candidate can be presented as unbiased runtime behavior. There are **33 unresolved membership outcomes** for this package; this count does not say each individual card is known to be ineligible.

## Decision

Keep the candidate manifest as-is, do not create a reviewed runtime manifest, and do not wire Plume's production random Fire selection. Plume damage branches must fail closed before RNG if they request the unresolved pool. Pool dependency closure and training eligibility remain open/false.
