# Package B completion — `profile_discover_battlecry_minion_v1`

Completed 2026-10-03. Elapsed time: **13m 26s**, measured from proposal creation at 18:43:32 UTC to passing implementation verification at 18:56:59 UTC. This is wall elapsed for the uninterrupted engineering batch; there was no user or external review wait.

## Outcome

- Candidate root: `CORE_GIL_836` Blazing Invocation; **1 declaration-only consumer / 1 consumer (100%)**.
- Shared implementation: typed Discover continuation, declarative pool selector/count/cost delta, full-catalog collectible/Battlecry metadata, card-ID choice descriptors, generated-hand insertion with current cost adjustment, hand-full burn and fail-closed unsupported selection. No card-ID runtime branch.
- `CUSTOM`: 0. Deferred: `CAP_407` Wanted Poster (Prepare rider) and `TLC_464` Mountain Map (history-sensitive second choice).
- Pinned catalog: `standard_full_20261001_v1`, source SHA-256 `d8c6616877b7b0736a59a3b24bee3d6b789a7504382ef68650feec5b8385a930`.
- Complete eligible Shaman/neutral collectible Battlecry-minion pool: **139 candidate IDs**, SHA-256 of sorted IDs joined by LF `495d6d17370400a694d7e2b31283b00d09fca746263de362d4a7abe6ae96260f`. All 139 remain eligible regardless of ManaEngine support state; one currently declared supported candidate is `CORE_SW_072` Rustrot Viper. Unsupported selected definitions invalidate that branch.
- Pool membership reads the actual `mechanics` field, not `referencedTags`, which can merely describe a card's effects on other Battlecry cards.
- Profile delta: one Meta root gained prototype implementation and focused behavioral verification; **0 canonical registry roots**, **0 verified full dependency closures**, **0 training-eligibility change**. The 138 unsupported pool outcomes remain an explicit runtime limitation; this package does not claim full profile closure.
- No trusted Rosetta parity was claimed: the pinned generated Rosetta card definition for `CORE_GIL_836` contains metadata but no Discover behavior implementation. Independent ManaEngine scenarios were used.

## Verification

- Windows Release CMake build: passed (2 build invocations; first after implementation, second after fixing the native fixture's duplicate Viper definition).
- Native suite: **22 scenario groups / 386 assertions**, CTest 1/1 passed.
- Adapter + action/policy pipeline: **22 passed**.
- Focused behavior: real root enters pending choice; 3 distinct `CHOOSE_CARD` descriptors include unsupported candidates; clone preserves the choice; choosing supported Viper adds a discounted generated instance and resumes legal-action generation; choosing an unsupported candidate invalidates only that branch; same-seed real-pool results repeat.
- Correction cycles: **2**, both test setup/expectation corrections; no production semantic correction after passing focused tests.

## Semantics references

- The pinned 2026-10-01 Standard snapshot says “Discover a Battlecry minion. It costs (1) less.” Blizzard's [36.2.2 notes](https://hearthstone.blizzard.com/en-us/news/24293284) confirm that wording was restored after 36.0.3.
- The current class/neutral Discover pool rule and equal per-card weighting are also described in Blizzard's [Discover rules discussion](https://us.forums.blizzard.com/en/hearthstone/t/discover-will-no-longer-favor-class-cards/13796). Runtime casting from another class and fallback behavior remain out of scope.
